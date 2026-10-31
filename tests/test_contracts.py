import json
import tempfile
import unittest
from pathlib import Path

from src.contracts import ConfigError, load_contract
from src.source_preflight import validate

FIXTURE = Path(__file__).resolve().parents[1] / 'samples/reconciliation/filter_mismatch'
CONTRACT = FIXTURE / 'orders.contract.json'


class ContractTests(unittest.TestCase):
    def with_contract(self, contract, content=None):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'contract.json'
            config.write_text(json.dumps(contract))
            source = FIXTURE / 'orders.csv'
            if content is not None:
                source = Path(directory) / 'data.csv'
                source.write_text(content)
            return validate(source, config_path=config)

    def test_snapshot_contract_accepts_positive_cancelled_original_amount(self):
        result = validate(FIXTURE / 'orders.csv', config_path=CONTRACT)
        self.assertEqual((result['decision'], result['records'], result['findings']), ('PASS', 3, []))
        self.assertEqual(result['contract'], load_contract(CONTRACT))
        # A declared business convention changes findings without changing Python.
        contract = load_contract(CONTRACT)
        contract['status_amount']['rules']['cancelled'] = 'zero'
        changed = self.with_contract(contract)
        self.assertEqual([(f['row'], f['code']) for f in changed['findings']],
                         [(4, 'status_amount_mismatch')])

    def test_changing_key_and_decimal_precision_changes_validation(self):
        contract = load_contract(CONTRACT)
        contract['unique_key'] = ['order_id']
        contract['amount']['decimal_places'] = 0
        result = self.with_contract(contract)
        self.assertEqual(sum(f['code'] == 'conflicting_id' for f in result['findings']), 1)
        self.assertEqual(sum(f['code'] == 'invalid_amount' for f in result['findings']), 3)

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
                contract = load_contract(CONTRACT)
                change(contract)
                with self.assertRaises(ConfigError):
                    self.with_contract(contract)

    def test_invalid_json_duplicate_keys_and_missing_configs_are_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            for text in ['{bad', '{"name":"a","name":"b"}', 'null', '[]']:
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ConfigError):
                        validate(Path(directory) / 'not-read.csv', config_path=path)
            with self.assertRaises(ConfigError):
                load_contract(Path(directory) / 'missing.json')

    def test_missing_contract_fails_closed_without_changing_source(self):
        source = FIXTURE / 'orders.csv'
        original = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigError):
                validate(source, config_path=Path(directory) / 'missing.json')
        self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
