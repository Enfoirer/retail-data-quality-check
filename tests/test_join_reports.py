import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from demo_reconciliation import run_demo
from src.join_diagnostics import diagnose_one
from src.reconcile import run_reconciliation

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'samples/reconciliation/join_fanout'


class JoinReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.fixture = self.base / 'fixture'
        shutil.copytree(FIXTURE, self.fixture)

    def test_fanout_and_corrected_join_match_independent_manual_expectations(self):
        expected = json.loads((self.fixture / 'expected.json').read_text())
        (self.fixture / 'expected.json').write_text('{}')
        before = run_reconciliation(self.fixture / 'job.json', self.base / 'before')
        after = run_reconciliation(self.fixture / 'job-fixed.json', self.base / 'after')
        for name, report in [('before', before), ('after', after)]:
            answer = expected[name]
            self.assertEqual(report['status'], answer['status'])
            self.assertEqual(report['query_result']['status'], answer['query_status'])
            detail = report['checkpoints'][-1]['query_scope']
            self.assertEqual((detail['A']['rows'], detail['B']['rows']), (answer['A_rows'], answer['B_rows']))
            self.assertEqual((detail['A']['amount_sum_cents'], detail['B']['amount_sum_cents']),
                             (answer['A_amount_cents'], answer['B_amount_cents']))
            self.assertEqual(detail['difference_cents'], answer['difference_cents'])
            diagnosis = next(item for item in report['join_diagnostics'] if item['pipeline'] == 'B')
            self.assertEqual(diagnosis['status'], answer['join_status'])
        self.assertEqual(before['first_raw_divergence'], 'enriched')
        self.assertIsNone(after['first_raw_divergence'])
        diagnosis = next(item for item in before['join_diagnostics'] if item['pipeline'] == 'B')
        candidate = diagnosis['fanout_keys'][0]
        self.assertEqual(candidate['key'], expected['before']['duplicated_key'])
        self.assertEqual(candidate['right_match_count'], 2)
        self.assertEqual(candidate['output_count'], 2)
        self.assertEqual({row['values']['product_version_id'] for row in candidate['right_matches']}, {'V001', 'V002'})
        self.assertTrue(diagnosis['replication_amount_model_matches'])
        self.assertEqual(diagnosis['amount_delta_cents'], 10000)
        with closing(sqlite3.connect(before['database'])) as db_before, closing(sqlite3.connect(after['database'])) as db_after:
            for table in ('orders', 'products'):
                self.assertEqual(db_before.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall(),
                                 db_after.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall())
            self.assertEqual(db_before.execute('SELECT COUNT(*) FROM products').fetchone()[0], 4)
            self.assertEqual(db_after.execute('SELECT COUNT(*) FROM products').fetchone()[0], 4)
            self.assertEqual(db_before.execute("SELECT COUNT(*) FROM b_enriched WHERE order_item_id='I001'").fetchone()[0], 2)
            # Traced physical rows are verified against the retained snapshot.
            for record in candidate['right_matches']:
                actual = db_before.execute('SELECT product_version_id FROM products WHERE rowid=?', (record['sqlite_rowid'],)).fetchone()[0]
                self.assertEqual(actual, record['values']['product_version_id'])

    def test_every_evidence_pointer_resolves_to_the_saved_value(self):
        report = run_reconciliation(self.fixture / 'job.json', self.base / 'run')
        ledger = json.loads(Path(report['evidence_file']).read_text())
        directory = Path(report['report_path']).parent
        ids = set()
        for item in ledger['items']:
            self.assertNotIn(item['id'], ids)
            ids.add(item['id'])
            value = json.loads((directory / item['source']['artifact']).read_text())
            for token in item['source']['json_pointer'].strip('/').split('/'):
                token = token.replace('~1', '/').replace('~0', '~')
                value = value[int(token)] if isinstance(value, list) else value[token]
            self.assertEqual(value, item['data'], item['id'])
        markdown = Path(report['human_report']).read_text()
        self.assertIn('**AMBIGUOUS**', markdown)
        self.assertIn('V001', markdown)
        self.assertIn('V002', markdown)
        self.assertIn('300.00 -> 400.00', markdown)
        self.assertIn('LEFT JOIN products', markdown)
        for evidence_id in ids:
            self.assertIn(evidence_id, markdown)

    def test_failure_also_generates_a_traceable_report(self):
        (self.fixture / 'sql/b_enrich.sql').write_text('SELECT missing_column FROM b_filtered;')
        report = run_reconciliation(self.fixture / 'job.json', self.base / 'failed')
        self.assertEqual(report['status'], 'ERROR')
        self.assertIn('**ERROR**', Path(report['human_report']).read_text())
        ledger = json.loads(Path(report['evidence_file']).read_text())
        error = next(item for item in ledger['items'] if item['kind'] == 'error')
        self.assertEqual(error['data']['pipeline'], 'B')
        self.assertEqual(error['data']['step'], 'enrich')

    def test_demo_verifies_both_corrections_and_source_hashes(self):
        summary = run_demo(self.base / 'demo')
        self.assertTrue(summary['verified'])
        self.assertEqual([case['before']['difference_cents'] for case in summary['cases']], [147900, 10000])
        self.assertEqual([case['after']['difference_cents'] for case in summary['cases']], [0, 0])
        self.assertTrue(all(case['source_files_unchanged'] for case in summary['cases']))


class JoinModelTests(unittest.TestCase):
    def diagnose(self, left, right, sql, change=None):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE left_data (order_item_id TEXT, product_id TEXT, amount_cents INTEGER)')
            db.execute('CREATE TABLE right_data (product_id TEXT, version_id TEXT)')
            db.executemany('INSERT INTO left_data VALUES (?, ?, ?)', left)
            db.executemany('INSERT INTO right_data VALUES (?, ?)', right)
            db.execute('CREATE TABLE output AS ' + sql)
            step = {'pipeline': 'B', 'id': 'enrich', 'output': 'output', 'sql_text': sql,
                    'sql_path': 'synthetic-test.sql', 'read_tables': ['left_data', 'right_data'],
                    'declared_join': {'left': 'left_data', 'right': 'right_data',
                                      'left_on': ['product_id'], 'right_on': ['product_id'], 'expected': 'many_to_one'}}
            if change:
                change(step)
            return diagnose_one(db, step, {'key': ['order_item_id'], 'amount_column': 'amount_cents'})

    def test_null_join_values_do_not_match_each_other(self):
        result = self.diagnose([('I1', None, 10000)], [(None, 'v1'), (None, 'v2')],
                               'SELECT l.*, r.version_id FROM left_data l LEFT JOIN right_data r ON l.product_id=r.product_id')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['unmatched_left_rows'], 1)
        self.assertEqual(result['observations'][0]['right_match_count'], 0)
        self.assertEqual(result['output_rows'], 1)

    def test_unused_right_duplicates_do_not_prove_observed_fanout(self):
        result = self.diagnose([('I1', 'P1', 10000)], [('P1', 'v1'), ('P99', 'v1'), ('P99', 'v2')],
                               'SELECT l.*, r.version_id FROM left_data l LEFT JOIN right_data r ON l.product_id=r.product_id')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['matched_multirow_left_records'], 0)

    def test_output_filter_can_prevent_a_potential_multiplicity(self):
        result = self.diagnose([('I1', 'P1', 10000)], [('P1', 'v1'), ('P1', 'v2')],
                               "SELECT l.*, r.version_id FROM left_data l LEFT JOIN right_data r ON l.product_id=r.product_id AND r.version_id='v2'")
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertEqual(result['fanout_keys'], [])
        self.assertFalse(result['row_model_matches'])
        self.assertEqual(result['observations'][0]['output_count'], 1)

    def test_fanout_can_exist_even_without_net_row_growth(self):
        result = self.diagnose([('I1', 'P1', 10000), ('I2', 'P2', 20000)], [('P1', 'v1'), ('P1', 'v2')],
                               'SELECT l.*, r.version_id FROM left_data l JOIN right_data r ON l.product_id=r.product_id')
        self.assertEqual(result['status'], 'FANOUT')
        self.assertEqual(result['row_delta'], 0)
        self.assertEqual(result['fanout_keys'][0]['key'], {'order_item_id': 'I1'})
        self.assertFalse(result['row_model_matches'])
        self.assertFalse(result['replication_amount_model_matches'])

    def test_existing_left_duplicates_are_not_attributed_to_the_join(self):
        result = self.diagnose([('I1', 'P1', 10000), ('I1', 'P1', 10000)], [('P1', 'v1')],
                               'SELECT l.*, r.version_id FROM left_data l LEFT JOIN right_data r ON l.product_id=r.product_id')
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertIn('already duplicated', result['reason'])

    def test_non_json_trace_values_are_explicitly_inconclusive(self):
        result = self.diagnose([('I1', 'P1', 10000)], [('P1', b'\x01')],
                               'SELECT l.*, r.version_id FROM left_data l LEFT JOIN right_data r ON l.product_id=r.product_id')
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertIn('unsupported non-JSON', result['reason'])
        json.dumps(result)

    def test_declared_inputs_must_agree_with_observed_read_dependencies(self):
        result = self.diagnose([('I1', 'P1', 10000)], [('P1', 'v1')],
                               'SELECT * FROM left_data', lambda step: step.update(read_tables=['left_data']))
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertIn('read dependencies', result['reason'])


if __name__ == '__main__':
    unittest.main()
