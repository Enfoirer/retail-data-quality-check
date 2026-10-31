"""Run a synthetic inspect -> human resolution -> recheck example."""
import argparse
import csv
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.retail_check import InputError, validate

ROOT = Path(__file__).resolve().parent


def demo_amount_sum(path):
    """Illustrative sum for this all-paid, single-currency fixture only."""
    with path.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(row['currency'] != 'CNY' or row['status'] != 'paid' for row in rows):
        raise InputError('Demo aggregate requires an all-paid CNY batch.')
    return sum((Decimal(row['amount']) for row in rows), Decimal('0.00'))


def run_demo(output_dir):
    before_path = ROOT / 'samples/batch-before.csv'
    after_path = ROOT / 'samples/batch-resolved.csv'
    before = validate(before_path)
    after = validate(after_path)
    before_amount = demo_amount_sum(before_path)
    after_amount = demo_amount_sum(after_path)
    summary = {
        'data': 'synthetic',
        'resolution': 'manually prepared fixture; see samples/RESOLUTION_NOTES.md',
        'before': {'records': before['records'], 'decision': before['decision'],
                   'errors': before['errors'], 'row_amount_sum_CNY': str(before_amount)},
        'after': {'records': after['records'], 'decision': after['decision'],
                  'errors': after['errors'], 'row_amount_sum_CNY': str(after_amount)},
        'row_amount_difference_CNY': str(before_amount - after_amount),
        'limitation': 'Illustrative sums, not measured savings or automatic source verification.'
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, report in [('before-report', before), ('after-report', after), ('demo-summary', summary)]:
        (output_dir / f'{name}.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('SYNTHETIC DEMO: input files remain unchanged.')
    print(f"1. Inspect: {before['decision']}; {before['records']} records, {before['errors']} errors")
    for finding in before['findings']:
        print(f"   record {finding['row']}: {finding['code']} — {finding['message']}")
        print(f"   Next action: {finding['suggestion']}")
    print('2. Human resolution: use the pre-prepared fixture and supplied synthetic source confirmations.')
    print('   Review samples/RESOLUTION_NOTES.md; no automatic fixes are performed.')
    print(f"3. Recheck: {after['decision']}; {after['records']} records, {after['errors']} errors")
    print(f'4. Illustrative row-amount sum (CNY): {before_amount:.2f} -> {after_amount:.2f}')
    print('   This demonstrates distortion in the fixture; it is not measured business savings.')
    print(f'Reports: {output_dir}')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs/demo')
    args = parser.parse_args()
    try:
        run_demo(args.output_dir)
    except (OSError, UnicodeError, csv.Error, InputError, InvalidOperation) as error:
        print(f'DEMO ERROR: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
