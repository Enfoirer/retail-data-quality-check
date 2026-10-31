"""Retail CSV preflight. Standard library only; no data leaves this machine."""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

COLUMNS = ('order_item_id', 'order_id', 'product_id', 'order_date', 'amount', 'currency', 'status')
STATUSES = {'paid', 'cancelled', 'refunded'}


class InputError(ValueError):
    pass


def validate(path, date_format=None):
    findings = []

    def add(row, field, code, message, suggestion, severity='error'):
        findings.append(dict(row=row, field=field, code=code, severity=severity,
                             message=message, suggestion=suggestion))

    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames
        if not headers:
            raise InputError('Empty file: expected a CSV header and data rows.')
        if len(headers) != len(set(headers)):
            raise InputError('Duplicate column names are not supported.')
        missing = sorted(set(COLUMNS) - set(headers))
        if missing:
            raise InputError('Missing required columns: ' + ', '.join(missing))
        seen = {}
        count = 0
        for count, raw in enumerate(reader, start=1):
            row = count + 1  # Logical CSV record number, including header.
            if None in raw or any(value is None for value in raw.values()):
                raise InputError(f'Record {row}: number of values does not match header.')
            values = {key: value.strip() for key, value in raw.items()}
            for field in COLUMNS:
                if not values[field]:
                    add(row, field, 'required', 'Required value is empty.', 'Restore from source; do not guess.')
            key = values['order_item_id']
            if key:
                signature = tuple(values[field] for field in COLUMNS)
                if key in seen:
                    previous_row, previous_signature = seen[key]
                    conflict = signature != previous_signature
                    add(row, 'order_item_id', 'conflicting_id' if conflict else 'duplicate_id',
                        f'Same item ID as record {previous_row}; ' + ('values differ.' if conflict else 'values match.'),
                        'Check source/replay history before removing or replacing any record.')
                else:
                    seen[key] = (row, signature)
            amount = None
            if values['amount']:
                text = values['amount']
                try:
                    if not re.fullmatch(r'-?\d+(?:\.\d{1,2})?', text, flags=re.ASCII):
                        raise InvalidOperation
                    amount = Decimal(text)
                except InvalidOperation:
                    add(row, 'amount', 'invalid_amount', 'Expected a decimal with at most two fractional digits.',
                        'Confirm separators/currency upstream; use e.g. 1234.50.')
            if values['currency'] and values['currency'] != 'CNY':
                add(row, 'currency', 'unsupported_currency', 'This prototype supports CNY only.',
                    'Separate currencies; extend the schema before processing others.')
            status = values['status']
            if status and status not in STATUSES:
                add(row, 'status', 'invalid_status', f'Unknown status: {status}.', 'Use paid, cancelled, or refunded.')
            if amount is not None and status in STATUSES:
                if (status == 'paid' and amount <= 0) or (status == 'cancelled' and amount != 0) or (status == 'refunded' and amount >= 0):
                    add(row, 'amount', 'status_amount_mismatch',
                        'Amount conflicts with the declared net-movement convention.',
                        'Confirm source semantics: paid > 0, cancelled = 0, refunded < 0.')
            date = values['order_date']
            if date:
                fmt = date_format or '%Y-%m-%d'
                try:
                    parsed = datetime.strptime(date, fmt)
                    if parsed.strftime(fmt) != date:
                        raise ValueError
                except ValueError:
                    if not date_format and re.fullmatch(r'\d{2}/\d{2}/\d{4}', date):
                        formats = ('%d/%m/%Y', '%m/%d/%Y')
                        possible = []
                        for candidate in formats:
                            try:
                                possible.append(datetime.strptime(date, candidate))
                            except ValueError:
                                pass
                        if possible:
                            add(row, 'order_date', 'date_format_review',
                                'Non-ISO date; day/month interpretation is not declared.',
                                'Confirm source convention and rerun with --date-format.', 'review')
                            continue
                    add(row, 'order_date', 'invalid_date', f'Expected a real date in {fmt} format.',
                        'Correct the source date or declare its documented format.')
        if count == 0:
            raise InputError('Header-only file: no data records to validate.')
    counts = Counter(f['severity'] for f in findings)
    return {'schema_version': 1, 'input': str(path), 'records': count,
            'decision': 'BLOCK' if counts['error'] else ('REVIEW' if counts['review'] else 'PASS'),
            'errors': counts['error'], 'reviews': counts['review'], 'findings': findings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path)
    parser.add_argument('--date-format', choices=['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'])
    parser.add_argument('--output', type=Path, help='Write complete JSON report.')
    args = parser.parse_args(argv)
    if args.output and args.output.resolve() == args.csv_file.resolve():
        print('OUTPUT ERROR: report must not overwrite the input CSV.', file=sys.stderr)
        return 2
    try:
        report = validate(args.csv_file, args.date_format)
    except (OSError, UnicodeError, csv.Error, InputError) as error:
        print(f'INPUT ERROR: {error}', file=sys.stderr)
        return 2
    print(f"{report['decision']}: {report['records']} records; {report['errors']} errors; {report['reviews']} reviews")
    for finding in report['findings']:
        print(f"  record {finding['row']} [{finding['severity']}] {finding['field']}: {finding['code']} — {finding['message']}")
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        except OSError as error:
            print(f'OUTPUT ERROR: {error}', file=sys.stderr)
            return 2
    return 0 if report['decision'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
