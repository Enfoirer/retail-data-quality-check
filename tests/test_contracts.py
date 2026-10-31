import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from src.contracts import ConfigError, load_contract
from src.retail_check import main, validate

ROOT = Path(__file__).resolve().parents[1]
SOURCE_B = ROOT / 'configs/source-b-snapshots.json'


class ContractTests(unittest.TestCase):
    def with_contract(self, contract, source=None, content=None):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'contract.json'
            config.write_text(json.dumps(contract))
            if content is not None:
                source = Path(directory) / 'data.csv'
                source.write_text(content)
            return validate(source or ROOT / 'samples/source-b.csv', config_path=config)

    def test_second_source_uses_composite_key_explicit_dates_and_original_refund_amount(self):
        result = validate(ROOT / 'samples/source-b.csv', config_path=SOURCE_B)
        self.assertEqual((result['decision'], result['records'], result['findings']), ('PASS', 4, []))
        self.assertEqual(result['contract'], load_contract(SOURCE_B))
        # A business convention change must change the result without editing Python.
        contract = load_contract(SOURCE_B)
        contract['status_amount']['rules']['refunded'] = 'negative'
        changed = self.with_contract(contract)
        self.assertEqual([(f['row'], f['code']) for f in changed['findings']],
                         [(4, 'status_amount_mismatch')])

    def test_changing_key_and_decimal_precision_changes_validation(self):
        contract = load_contract(SOURCE_B)
        contract['unique_key'] = ['order_ref']
        contract['amount']['decimal_places'] = 0
        result = self.with_contract(contract)
        self.assertEqual(sum(f['code'] == 'conflicting_id' for f in result['findings']), 1)
        self.assertEqual(sum(f['code'] == 'invalid_amount' for f in result['findings']), 4)

    def test_minimal_contract_and_composite_key_collisions(self):
        contract = {'name': 'pair-key', 'required': ['a', 'b', 'value'], 'unique_key': ['a', 'b']}
        result = self.with_contract(contract, content='a,b,value\nab,c,1\na,bc,2\nab,c,1\n')
        self.assertEqual([(f['row'], f['code']) for f in result['findings']], [(4, 'duplicate_id')])

    def test_bad_configs_fail_before_data_validation(self):
        changes = [
            lambda c: c.update(unknown_rule=True),
            lambda c: c.update(unique_key=['missing']),
            lambda c: c['amount'].update(decimal_places=True),
            lambda c: c['date'].update(format='%m-%d-%y'),
            lambda c: c['status_amount']['rules'].pop('paid'),
            lambda c: c['status_amount']['rules'].update(paid='eval(amount)'),
            lambda c: c['allowed_values'].update(currency=[]),
            lambda c: c['date'].update(review_alternate_formats='yes'),
        ]
        for change in changes:
            with self.subTest(change=change):
                contract = load_contract()
                change(contract)
                with self.assertRaises(ConfigError):
                    self.with_contract(contract)

    def test_invalid_json_duplicate_keys_and_missing_configs_are_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            for text in ['{bad', '{"name":"a","name":"b"}', 'null', '[]']:
                with self.subTest(text=text):
                    path.write_text(text)
                    with contextlib.redirect_stderr(io.StringIO()) as errors:
                        self.assertEqual(main([str(ROOT / 'samples/clean.csv'), '--config', str(path)]), 2)
                    self.assertIn('CONFIG ERROR', errors.getvalue())
            with self.assertRaises(ConfigError):
                load_contract(Path(directory) / 'missing.json')

    def test_output_cannot_overwrite_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'contract.json'
            original = json.dumps(load_contract())
            path.write_text(original)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(ROOT / 'samples/clean.csv'), '--config', str(path),
                                       '--output', str(path)]), 2)
            self.assertEqual(path.read_text(), original)


if __name__ == '__main__':
    unittest.main()
