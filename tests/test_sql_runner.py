import contextlib
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.job_config import JobError, load_job
from src.sql_runner import ExecutionError, main, minor_units, run_job

FIXTURE = Path(__file__).resolve().parents[1] / 'samples/reconciliation/filter_mismatch'


class SqlRunnerTests(unittest.TestCase):
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

    def test_shared_sources_and_all_stages_are_retained_with_exact_money(self):
        # A wrong answer key must not influence execution.
        (self.fixture / 'expected.json').write_text('{"incorrect": true}')
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'SUCCESS')
        self.assertEqual([step['rows'] for step in report['steps']], [2, 2, 3, 3])
        self.assertEqual([step['read_tables'] for step in report['steps']],
                         [['orders'], ['a_filtered', 'products'], ['orders'], ['b_filtered', 'products']])
        with sqlite3.connect(report['database']) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {'orders', 'products', 'a_filtered', 'a_enriched', 'b_filtered', 'b_enriched'})
            self.assertEqual(db.execute('SELECT SUM(amount_cents) FROM a_enriched').fetchone()[0], 30000)
            self.assertEqual(db.execute('SELECT SUM(amount_cents) FROM b_enriched').fetchone()[0], 177900)
            self.assertEqual(db.execute("SELECT amount, amount_cents, typeof(amount_cents) FROM orders WHERE order_item_id='I003'").fetchone(),
                             ('1479.00', 147900, 'integer'))
        stored = json.loads(Path(report['report_path']).read_text())
        self.assertEqual(stored['steps'][0]['sql_text'], (self.fixture / 'sql/a_filter.sql').read_text().strip())
        self.assertEqual(stored['status'], 'SUCCESS')

    def test_sql_failure_identifies_step_and_keeps_committed_tables(self):
        (self.fixture / 'sql/b_enrich.sql').write_text('SELECT missing_field FROM b_filtered;')
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual((report['error']['pipeline'], report['error']['step']), ('B', 'enrich'))
        self.assertTrue(report['error']['file'].endswith('sql/b_enrich.sql'))
        self.assertIn('missing_field', report['error']['message'])
        self.assertEqual([step['status'] for step in report['steps']], ['SUCCESS'] * 3 + ['FAILED'])
        with sqlite3.connect(report['database']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM b_filtered').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM a_enriched').fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='b_enriched'").fetchall(), [])
        self.assertEqual(json.loads((self.output / 'execution.json').read_text())['status'], 'FAILED')

    def test_missing_sql_file_has_step_context(self):
        (self.fixture / 'sql/b_filter.sql').unlink()
        report = run_job(self.job, self.output)
        self.assertEqual((report['error']['phase'], report['error']['pipeline'], report['error']['step']),
                         ('step', 'B', 'filter'))
        self.assertEqual(len(report['steps']), 3)

    def test_pipelines_cannot_read_each_others_intermediate_results(self):
        (self.fixture / 'sql/b_filter.sql').write_text('SELECT * FROM a_filtered;')
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual((report['error']['pipeline'], report['error']['step']), ('B', 'filter'))
        self.assertIn('prohibited', report['error']['message'])

    def test_queries_cannot_mutate_sources_or_execute_multiple_statements(self):
        for sql in ["DELETE FROM orders;", "SELECT * FROM orders; DROP TABLE products;"]:
            with self.subTest(sql=sql):
                (self.fixture / 'sql/a_filter.sql').write_text(sql)
                report = run_job(self.job, self.base / f'failure-{len(list(self.base.glob("failure-*")))}')
                self.assertEqual(report['status'], 'FAILED')
                with sqlite3.connect(report['database']) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 3)
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0], 3)

    def test_checkpoint_columns_must_be_present(self):
        (self.fixture / 'sql/a_filter.sql').write_text('SELECT order_item_id FROM orders;')
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['error']['step'], 'filter')
        self.assertIn('missing comparison columns', report['error']['message'])
        with sqlite3.connect(report['database']) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='a_filtered'").fetchall(), [])

    def test_contract_failure_stops_before_loading_invalid_source(self):
        path = self.fixture / 'orders.csv'
        path.write_text(path.read_text().replace('100.00', 'not-money'))
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['error']['table'], 'orders')
        self.assertIn('invalid_amount', report['error']['message'])
        self.assertEqual(report['steps'], [])
        self.assertEqual(report['sources'][0]['validation']['decision'], 'BLOCK')
        with sqlite3.connect(report['database']) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])

    def test_malformed_uncontracted_csv_is_rejected(self):
        (self.fixture / 'products.csv').write_text('product_id,category\nP01,Home,extra\n')
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['error']['table'], 'products')
        with sqlite3.connect(report['database']) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='products'").fetchall(), [])

    def test_money_is_exact_and_rejects_fractional_cents_and_overflow(self):
        self.assertEqual(minor_units('0.10'), 10)
        self.assertEqual(minor_units('-0.01'), -1)
        self.assertEqual(minor_units('92233720368547758.07'), 2 ** 63 - 1)
        for text in ['1.001', '1,000.00', 'NaN', '1e2', '92233720368547758.08']:
            with self.subTest(text=text), self.assertRaises(ExecutionError):
                minor_units(text)

    def test_invalid_money_without_contract_is_still_rejected_with_record(self):
        self.edit_job(lambda job: job['sources'][0].pop('contract'))
        path = self.fixture / 'orders.csv'
        path.write_text(path.read_text().replace('100.00', '1.001'))
        report = run_job(self.job, self.output)
        self.assertEqual(report['status'], 'FAILED')
        self.assertIn('Record 2', report['error']['message'])
        self.assertEqual(report['error']['table'], 'orders')

    def test_invalid_jobs_are_rejected_before_output_creation(self):
        original = self.job.read_text()
        changes = [
            lambda job: job.update(unknown=True),
            lambda job: job['sources'].append({'table': 'ORDERS', 'csv': 'orders.csv'}),
            lambda job: job['pipelines']['A'][0].update(output='orders'),
            lambda job: job['pipelines']['B'][0].update(id='bad-name'),
            lambda job: job['pipelines']['B'][1]['join'].update(right='a_filtered'),
            lambda job: job['checkpoints'][0].update(b='a_filtered'),
            lambda job: job['checkpoints'].reverse(),
            lambda job: job['comparison'].update(key=[]),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.job.write_text(original)
                self.edit_job(change)
                with self.assertRaises(JobError):
                    run_job(self.job, self.output)
                self.assertFalse(self.output.exists())
        self.job.write_text('{"name":"a","name":"b"}')
        with self.assertRaisesRegex(JobError, 'Duplicate JSON key'):
            load_job(self.job)

    def test_existing_run_is_not_overwritten_and_cli_failure_is_clear(self):
        run_job(self.job, self.output)
        original = (self.output / 'run.sqlite').read_bytes()
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main([str(self.job), '--output-dir', str(self.output)]), 2)
        self.assertEqual((self.output / 'run.sqlite').read_bytes(), original)
        self.assertIn('EXECUTION ERROR', errors.getvalue())
        (self.fixture / 'sql/b_filter.sql').write_text('SELECT bad_column FROM orders;')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main([str(self.job), '--output-dir', str(self.base / 'failed-run')]), 2)
        self.assertIn('pipeline B, step filter', errors.getvalue())
        self.assertIn('b_filter.sql', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
