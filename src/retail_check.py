"""CSV preflight driven by a validated JSON contract; standard library only."""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

if __package__:
    from .contracts import ConfigError, DATE_FORMATS, DEFAULT_CONFIG, load_contract
else:
    from contracts import ConfigError, DATE_FORMATS, DEFAULT_CONFIG, load_contract


class InputError(ValueError):
    pass


def sign_matches(amount, rule):
    return {'positive': amount > 0, 'negative': amount < 0, 'zero': amount == 0,
            'nonnegative': amount >= 0, 'nonpositive': amount <= 0, 'any': True}[rule]


def check_date(text, rule, explicit_format=None):
    fmt = explicit_format or rule['format']
    try:
        parsed = datetime.strptime(text, fmt)
        if parsed.strftime(fmt) != text:
            raise ValueError
        return None
    except ValueError:
        if (not explicit_format and rule.get('review_alternate_formats', False)
                and re.fullmatch(r'[0-9]{2}/[0-9]{2}/[0-9]{4}', text)):
            for candidate in DATE_FORMATS[1:]:
                try:
                    datetime.strptime(text, candidate)
                    return ('date_format_review', 'review',
                            'Non-ISO date; day/month interpretation is not declared.',
                            'Confirm source convention and change the contract or use --date-format.')
                except ValueError:
                    pass
        return ('invalid_date', 'error', f'Expected a real date in {fmt} format.',
                'Correct the source date or declare its documented format.')


def validate(path, date_format=None, config_path=DEFAULT_CONFIG):
    contract = load_contract(config_path)
    if date_format is not None:
        if date_format not in DATE_FORMATS:
            raise ConfigError('Unsupported date format override.')
        if 'date' not in contract:
            raise ConfigError('--date-format requires a date rule in the contract.')
    findings = []
    required = contract['required']
    unique_key = contract['unique_key']
    amount_rule = contract.get('amount')

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
        missing = sorted(set(required) - set(headers))
        if missing:
            raise InputError('Missing required columns: ' + ', '.join(missing))
        seen = {}
        count = 0
        for count, raw in enumerate(reader, start=1):
            row = count + 1  # Logical CSV record number, including header.
            if None in raw or any(value is None for value in raw.values()):
                raise InputError(f'Record {row}: number of values does not match header.')
            values = {key: value.strip() for key, value in raw.items()}
            for field in required:
                if not values[field]:
                    add(row, field, 'required', 'Required value is empty.', 'Restore from source; do not guess.')
            key = tuple(values[field] for field in unique_key)
            if all(key):
                signature = tuple(values[field] for field in required)
                if key in seen:
                    previous_row, previous_signature = seen[key]
                    conflict = signature != previous_signature
                    add(row, ','.join(unique_key), 'conflicting_id' if conflict else 'duplicate_id',
                        f'Same configured key as record {previous_row}; ' + ('values differ.' if conflict else 'values match.'),
                        'Check source/replay history before removing or replacing any record.')
                else:
                    seen[key] = (row, signature)
            amount = None
            if amount_rule and values[amount_rule['field']]:
                text = values[amount_rule['field']]
                places = amount_rule['decimal_places']
                pattern = r'-?[0-9]+' + (rf'(?:\.[0-9]{{1,{places}}})?' if places else '')
                try:
                    if not re.fullmatch(pattern, text):
                        raise InvalidOperation
                    amount = Decimal(text)
                except InvalidOperation:
                    add(row, amount_rule['field'], 'invalid_amount',
                        f'Expected a decimal with at most {places} fractional digits.',
                        'Confirm separators/currency upstream; follow the contract format.')
            for field, allowed in contract.get('allowed_values', {}).items():
                if values[field] and values[field] not in allowed:
                    add(row, field, 'invalid_value', f'Value is not allowed by the contract: {values[field]}.',
                        'Confirm source semantics; allowed values: ' + ', '.join(allowed) + '.')
            status_rule = contract.get('status_amount')
            if amount is not None and status_rule:
                status = values[status_rule['status_field']]
                sign_rule = status_rule['rules'].get(status)
                if sign_rule and not sign_matches(amount, sign_rule):
                    add(row, amount_rule['field'], 'status_amount_mismatch',
                        f'Amount must be {sign_rule} for status {status} under this contract.',
                        'Confirm source semantics before changing data or the status/amount rule.')
            if 'date' in contract and values[contract['date']['field']]:
                field = contract['date']['field']
                issue = check_date(values[field], contract['date'], date_format)
                if issue:
                    code, severity, message, suggestion = issue
                    add(row, field, code, message, suggestion, severity)
        if count == 0:
            raise InputError('Header-only file: no data records to validate.')
    counts = Counter(f['severity'] for f in findings)
    return {'schema_version': 2, 'input': str(path), 'contract': contract,
            'date_format_override': date_format, 'records': count,
            'decision': 'BLOCK' if counts['error'] else ('REVIEW' if counts['review'] else 'PASS'),
            'errors': counts['error'], 'reviews': counts['review'], 'findings': findings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='JSON data contract.')
    parser.add_argument('--date-format', choices=DATE_FORMATS)
    parser.add_argument('--output', type=Path, help='Write complete JSON report.')
    args = parser.parse_args(argv)
    if args.output and args.output.resolve() in (args.csv_file.resolve(), args.config.resolve()):
        print('OUTPUT ERROR: report must not overwrite the input CSV or contract.', file=sys.stderr)
        return 2
    try:
        report = validate(args.csv_file, args.date_format, args.config)
    except ConfigError as error:
        print(f'CONFIG ERROR: {error}', file=sys.stderr)
        return 2
    except (OSError, UnicodeError, csv.Error, InputError) as error:
        print(f'INPUT ERROR: {error}', file=sys.stderr)
        return 2
    print(f"Contract: {report['contract']['name']}")
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
