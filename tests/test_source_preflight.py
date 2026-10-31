import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.contracts import load_contract
from src.source_preflight import InputError, validate

FIXTURE = Path(__file__).resolve().parents[1] / 'samples/reconciliation/filter_mismatch'
CONTRACT = FIXTURE / 'orders.contract.json'


class SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.contract = load_contract(CONTRACT)
        self.config = self.base / 'contract.json'
        with (FIXTURE / 'orders.csv').open(newline='') as stream:
            self.rows = list(csv.DictReader(stream))

    def check_rows(self, rows):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=self.contract['required'])
        writer.writeheader()
        writer.writerows(rows)
        return self.check_text(stream.getvalue())

    def check_text(self, text):
        source = self.base / 'input.csv'
        source.write_text(text)
        self.config.write_text(json.dumps(self.contract))
        return validate(source, config_path=self.config)

    def test_valid_snapshot_allows_multiple_items_and_positive_cancelled_amounts(self):
        result = validate(FIXTURE / 'orders.csv', config_path=CONTRACT)
        self.assertEqual((result['decision'], result['records'], result['findings']), ('PASS', 3, []))

    def test_expected_issues_are_localized(self):
        first = self.rows[0]
        missing = dict(self.rows[1], product_id='', amount='not-money')
        invalid = dict(self.rows[2], order_item_id='I004', order_date='2026-02-30', status='paid', amount='-1.00')
        result = self.check_rows([first, first, missing, invalid])
        self.assertEqual({(f['row'], f['code']) for f in result['findings']}, {
            (3, 'duplicate_id'), (4, 'required'), (4, 'invalid_amount'),
            (5, 'invalid_date'), (5, 'status_amount_mismatch')})
        self.assertEqual(result['decision'], 'BLOCK')

    def test_conflict_and_ambiguous_dates_do_not_trigger_silent_repair(self):
        self.contract['date']['review_alternate_formats'] = True
        first = dict(self.rows[0], order_date='03/04/2026')
        conflict = dict(self.rows[0], amount='1200.00')
        formatted = dict(self.rows[1], amount='1,200.00')
        result = self.check_rows([first, conflict, formatted])
        self.assertEqual([f['code'] for f in result['findings']],
                         ['date_format_review', 'conflicting_id', 'invalid_amount'])

    def test_findings_preserve_source_and_contract_bytes(self):
        self.check_rows([self.rows[0], self.rows[0]])
        source = self.base / 'input.csv'
        original_source, original_contract = source.read_bytes(), self.config.read_bytes()
        result = validate(source, config_path=self.config)
        self.assertEqual(result['decision'], 'BLOCK')
        self.assertEqual(source.read_bytes(), original_source)
        self.assertEqual(self.config.read_bytes(), original_contract)

    def test_declared_date_format_resolves_review(self):
        self.contract['date']['review_alternate_formats'] = True
        rows = [dict(self.rows[0], order_date='03/04/2026')]
        self.assertEqual(self.check_rows(rows)['decision'], 'REVIEW')
        self.contract['date'].update(format='%d/%m/%Y', review_alternate_formats=False)
        self.assertEqual(self.check_rows(rows)['decision'], 'PASS')

    def test_malformed_and_empty_inputs(self):
        header = ','.join(self.contract['required'])
        for text in ['', header + '\n', 'order_id,amount\nO1,1\n', header + '\nI1,O1\n',
                     'order_id,order_id\n1,2\n', header + '\n"unclosed\n']:
            with self.subTest(text=text), self.assertRaises((InputError, csv.Error)):
                self.check_text(text)

    def test_missing_columns_have_clear_error(self):
        with self.assertRaisesRegex(InputError, 'Missing required columns'):
            self.check_text('order_id,amount\nO1,100.00\n')

    def test_report_retains_explicit_contract_and_serializable_findings(self):
        result = self.check_rows([dict(self.rows[0], currency='USD')])
        self.assertEqual(result['decision'], 'BLOCK')
        self.assertEqual(result['contract'], self.contract)
        self.assertEqual(result['findings'][0]['code'], 'invalid_value')
        self.assertEqual(json.loads(json.dumps(result)), result)


if __name__ == '__main__':
    unittest.main()
