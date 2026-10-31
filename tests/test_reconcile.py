import contextlib
from contextlib import closing
import csv
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.job_config import JobError, load_job
from src.reconcile import main, run_reconciliation

FIXTURE = Path(__file__).resolve().parents[1] / 'samples/reconciliation/filter_mismatch'


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.fixture = self.base / 'fixture'
        shutil.copytree(FIXTURE, self.fixture)
        self.job = self.fixture / 'job.json'
        self.output = self.base / 'run'

    def edit_job(self, change):
        job = json.loads(self.job.read_text())
        change(job)
        self.job.write_text(json.dumps(job))

    def fix_b_filter(self):
        shutil.copyfile(self.fixture / 'sql/b_filter_paid.sql', self.fixture / 'sql/b_filter.sql')

    def transform_b(self, expression, column):
        fields = ['order_item_id', 'order_id', 'product_id', 'order_date', 'status',
                  'province', 'amount', 'currency', 'amount_cents']
        projection = [f'{expression} AS {field}' if field == column else field for field in fields]
        (self.fixture / 'sql/b_enrich.sql').write_text('SELECT ' + ', '.join(projection) + ' FROM b_filtered;')
        self.edit_job(lambda job: job['pipelines']['B'][1].pop('join', None))

    def test_query_and_checkpoint_differences_match_manual_answer_key(self):
        expected = json.loads((self.fixture / 'expected.json').read_text())
        # Runtime must not derive answers from the fixture's acceptance file.
        (self.fixture / 'expected.json').write_text('{}')
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'DIFFERENT')
        self.assertEqual(report['query_result']['status'], 'DIFFERENT')
        self.assertEqual(report['first_raw_divergence'], expected['first_divergent_checkpoint'])
        self.assertEqual(report['first_query_scope_divergence'], 'filtered')
        for checkpoint, answer in zip(report['checkpoints'], expected['checkpoints']):
            for scope in ('raw', 'query_scope'):
                result = checkpoint[scope]
                self.assertEqual(result['A'], answer['A'])
                self.assertEqual(result['B'], answer['B'])
                self.assertEqual(result['difference_cents'], answer['difference_cents'])
                self.assertEqual([row['order_item_id'] for row in result['only_in_b']], ['I003'])
                self.assertEqual(result['only_in_a'], [])
                self.assertEqual(result['value_mismatches'], [])
                self.assertEqual(result['amount_explanation']['explained_difference_cents'], 147900)
                self.assertEqual(result['amount_explanation']['unexplained_difference_cents'], 0)
        groups = report['query_result']['groups']
        self.assertEqual({row['group']['province']: row['difference_cents'] for row in groups},
                         expected['final_province_differences_cents'])
        self.assertEqual(groups[0]['group'], {'province': 'Beijing'})
        self.assertEqual(json.loads((self.output / 'reconciliation.json').read_text())['status'], 'DIFFERENT')
        with (self.output / 'differences/only_in_b.csv').open() as stream:
            self.assertEqual([row['order_item_id'] for row in csv.DictReader(stream)], ['I003'])

    def test_user_filter_can_mask_dataset_difference(self):
        report = run_reconciliation(self.fixture / 'job-paid-query.json', self.output)
        self.assertEqual(report['status'], 'MATCH')
        self.assertEqual(report['query_result']['status'], 'MATCH')
        self.assertEqual(report['detail_status'], 'MATCH')
        self.assertEqual(report['first_raw_divergence'], 'filtered')
        self.assertIsNone(report['first_query_scope_divergence'])
        self.assertEqual(report['checkpoints'][0]['raw']['difference_cents'], 147900)
        self.assertEqual(report['checkpoints'][0]['query_scope']['difference_cents'], 0)

    def test_corrected_pipeline_reconciles_without_query_masking(self):
        self.fix_b_filter()
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'MATCH')
        self.assertIsNone(report['first_raw_divergence'])
        self.assertIsNone(report['first_query_scope_divergence'])

    def test_offsetting_amount_changes_do_not_hide_record_mismatches(self):
        self.fix_b_filter()
        self.edit_job(lambda job: job['query'].update(group_by=[]))
        self.transform_b("amount_cents + CASE WHEN order_item_id='I001' THEN 1000 ELSE -1000 END", 'amount_cents')
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'DIFFERENT')
        self.assertEqual(report['query_result']['status'], 'MATCH')
        self.assertEqual(report['detail_status'], 'DIFFERENT')
        self.assertEqual(report['first_query_scope_divergence'], 'enriched')
        detail = report['checkpoints'][-1]['query_scope']
        self.assertEqual(detail['difference_cents'], 0)
        self.assertEqual(len(detail['value_mismatches']), 2)
        self.assertEqual([row['difference_cents'] for row in detail['value_mismatches']], [1000, -1000])
        self.assertEqual(detail['amount_explanation']['explained_difference_cents'], 0)

    def test_equal_counts_and_totals_do_not_hide_replaced_keys(self):
        self.fix_b_filter()
        self.edit_job(lambda job: job['query'].update(group_by=[]))
        self.transform_b("CASE WHEN order_item_id='I002' THEN 'I900' ELSE order_item_id END", 'order_item_id')
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['query_result']['status'], 'MATCH')
        self.assertEqual(report['status'], 'DIFFERENT')
        detail = report['checkpoints'][-1]['query_scope']
        self.assertEqual([row['order_item_id'] for row in detail['only_in_a']], ['I002'])
        self.assertEqual([row['order_item_id'] for row in detail['only_in_b']], ['I900'])
        self.assertEqual(detail['amount_explanation']['unexplained_difference_cents'], 0)

    def test_duplicate_keys_are_preserved_even_when_both_sides_match(self):
        self.fix_b_filter()
        path = self.fixture / 'products.csv'
        with path.open('a') as stream:
            stream.write('P01,Electronics\n')
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'AMBIGUOUS')
        self.assertEqual(report['query_result']['status'], 'MATCH')
        detail = report['checkpoints'][-1]['query_scope']
        for side in ('A', 'B'):
            duplicate = detail['duplicate_keys'][side][0]
            self.assertEqual(duplicate['key'], {'order_item_id': 'I001'})
            self.assertEqual(duplicate['count'], 2)
            self.assertEqual(len(duplicate['records']), 2)
        self.assertIsNone(detail['amount_explanation'])
        with closing(sqlite3.connect(report['database'])) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM a_enriched').fetchone()[0], 3)

    def test_missing_key_is_ambiguous_and_not_silently_matched(self):
        self.fix_b_filter()
        for index, missing in enumerate(['NULL', "''", "'   '"]):
            with self.subTest(missing=missing):
                self.transform_b(f"CASE WHEN order_item_id='I001' THEN {missing} ELSE order_item_id END", 'order_item_id')
                report = run_reconciliation(self.job, self.base / f'missing-key-{index}')
                self.assertEqual(report['status'], 'AMBIGUOUS')
                self.assertEqual(len(report['checkpoints'][-1]['query_scope']['invalid_keys']['B']), 1)
                self.assertEqual(report['first_query_scope_divergence'], 'enriched')

    def test_empty_query_scope_is_a_valid_match(self):
        self.edit_job(lambda job: job['query'].update(
            filters=[{'column': 'status', 'operator': 'eq', 'value': 'not-present'}], group_by=[]))
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'MATCH')
        self.assertEqual(report['query_result']['groups'][0]['A']['rows'], 0)
        self.assertEqual(report['query_result']['groups'][0]['B']['amount_sum_cents'], 0)
        self.assertIsNone(report['first_query_scope_divergence'])

    def test_money_output_types_fail_explicitly(self):
        for index, value in enumerate(['NULL', '1.5', "'10000'"]):
            with self.subTest(value=value):
                self.transform_b(value, 'amount_cents')
                report = run_reconciliation(self.job, self.base / f'bad-{index}')
                self.assertEqual(report['status'], 'ERROR')
                self.assertIn('integer minor units', report['error']['message'])
                self.assertIn('enriched', report['error']['message'])

    def test_filters_are_parameterized_and_support_ranges_and_membership(self):
        self.edit_job(lambda job: job['query'].update(filters=[
            {'column': 'province', 'operator': 'in', 'value': ['Beijing']},
            {'column': 'amount_cents', 'operator': 'gte', 'value': 10000},
            {'column': 'amount_cents', 'operator': 'lte', 'value': 20000}]))
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'MATCH')
        self.assertEqual(report['checkpoints'][-1]['query_scope']['A']['rows'], 1)
        self.edit_job(lambda job: job['query'].update(filters=[
            {'column': 'province', 'operator': 'eq', 'value': "Beijing' OR 1=1 --"}]))
        report = run_reconciliation(self.job, self.base / 'parameterized')
        self.assertEqual(report['checkpoints'][-1]['query_scope']['B']['rows'], 0)

    def test_invalid_query_definitions_are_rejected(self):
        original = self.job.read_text()
        changes = [
            lambda job: job['query'].update(group_by=['unknown']),
            lambda job: job['query']['filters'][0].update(column='category'),
            lambda job: job['query']['filters'][0].update(operator='eval'),
            lambda job: job['query']['filters'][0].update(value=None),
            lambda job: job['query']['filters'][0].update(operator='in', value=[]),
            lambda job: job['query']['filters'][0].update(column='amount_cents', value='100'),
            lambda job: job['query']['filters'][0].update(column='amount_cents', value=2 ** 63),
            lambda job: job['checkpoints'].pop(),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.job.write_text(original)
                self.edit_job(change)
                with self.assertRaises(JobError):
                    load_job(self.job)

    def test_execution_failure_is_not_reported_as_matching(self):
        (self.fixture / 'sql/b_filter.sql').write_text('SELECT missing FROM orders;')
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'ERROR')
        self.assertEqual((report['error']['pipeline'], report['error']['step']), ('B', 'filter'))
        self.assertTrue((self.output / 'run.sqlite').exists())
        self.assertTrue((self.output / 'execution.json').exists())
        self.assertFalse((self.output / 'differences').exists())

    def test_query_is_optional_for_existing_job_format(self):
        self.edit_job(lambda job: job.pop('query'))
        report = run_reconciliation(self.job, self.output)
        self.assertEqual(report['status'], 'DIFFERENT')
        self.assertEqual(report['query'], {'filters': [], 'group_by': ['province']})

    def test_cli_exit_codes_distinguish_matching_different_and_failed(self):
        for name, job_path, expected in [('different', self.job, 1),
                                         ('matching', self.fixture / 'job-paid-query.json', 0)]:
            with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(job_path), '--output-dir', str(self.base / name)]), expected)
        (self.fixture / 'sql/b_filter.sql').write_text('SELECT missing FROM orders;')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.job), '--output-dir', str(self.base / 'failure')]), 2)


if __name__ == '__main__':
    unittest.main()
