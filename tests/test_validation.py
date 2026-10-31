import contextlib
import io
import tempfile
import json
import unittest
from pathlib import Path
from src.retail_check import COLUMNS, InputError, main, validate
from demo import run_demo

ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    def test_clean_allows_multiple_items_per_order_and_signed_refunds(self):
        result = validate(ROOT / 'samples/clean.csv')
        self.assertEqual((result['decision'], result['records'], result['findings']), ('PASS', 4, []))

    def test_expected_issues_are_localized(self):
        result = validate(ROOT / 'samples/typical-errors.csv')
        self.assertEqual({(f['row'], f['code']) for f in result['findings']}, {
            (3, 'duplicate_id'), (4, 'required'), (4, 'invalid_amount'),
            (5, 'invalid_date'), (5, 'status_amount_mismatch')})
        self.assertEqual(result['decision'], 'BLOCK')

    def test_conflict_and_ambiguity_do_not_trigger_silent_repair(self):
        result = validate(ROOT / 'samples/difficult-case.csv')
        self.assertEqual([f['code'] for f in result['findings']],
                         ['date_format_review', 'conflicting_id', 'invalid_amount'])

    def test_resolution_demo_preserves_inputs_and_matches_manual_answer_key(self):
        paths = [ROOT / 'samples/batch-before.csv', ROOT / 'samples/batch-resolved.csv']
        originals = [path.read_bytes() for path in paths]
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            result = run_demo(Path(directory))
            self.assertEqual(result['before'], {
                'records': 6, 'decision': 'BLOCK', 'errors': 3, 'row_amount_sum_CNY': '360.50'})
            self.assertEqual(result['after'], {
                'records': 4, 'decision': 'PASS', 'errors': 0, 'row_amount_sum_CNY': '220.50'})
            self.assertEqual(result['row_amount_difference_CNY'], '140.00')
            report = json.loads((Path(directory) / 'before-report.json').read_text())
            self.assertEqual({(f['row'], f['code']) for f in report['findings']}, {
                (3, 'duplicate_id'), (5, 'required'), (7, 'conflicting_id')})
        self.assertEqual([path.read_bytes() for path in paths], originals)

    def check_text(self, text, fmt=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.csv'
            path.write_text(text)
            return validate(path, fmt)

    def test_declared_date_format_resolves_review(self):
        text = ','.join(COLUMNS) + '\nI1,O1,P1,03/04/2026,1.00,CNY,paid\n'
        self.assertEqual(self.check_text(text)['decision'], 'REVIEW')
        self.assertEqual(self.check_text(text, '%d/%m/%Y')['decision'], 'PASS')

    def test_malformed_and_empty_inputs(self):
        for text in ['', ','.join(COLUMNS) + '\n', 'order_id,amount\nO1,1\n',
                     ','.join(COLUMNS) + '\nI1,O1\n', 'order_id,order_id\n1,2\n',
                     ','.join(COLUMNS) + '\n"unclosed\n']:
            with self.subTest(text=text), self.assertRaises((InputError, __import__('csv').Error)):
                self.check_text(text)

    def test_invalid_input_cli_has_clear_exit_code(self):
        with contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(main([str(ROOT / 'samples/invalid-schema.csv')]), 2)
        self.assertIn('Missing required columns', output.getvalue())

    def test_json_report_matches_console_decision(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            output = Path(directory) / 'report.json'
            self.assertEqual(main([str(ROOT / 'samples/clean.csv'), '--output', str(output)]), 0)
            self.assertIn('"decision": "PASS"', output.read_text())


if __name__ == '__main__':
    unittest.main()
