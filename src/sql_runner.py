"""Execute two explicit SQL pipelines and retain sources, stages, and execution evidence."""
import argparse
import csv
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .contracts import ConfigError
    from .job_config import JobError, identifier, load_job
    from .retail_check import InputError, validate
else:
    from contracts import ConfigError
    from job_config import JobError, identifier, load_job
    from retail_check import InputError, validate


class ExecutionError(ValueError):
    pass


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def minor_units(value):
    match = re.fullmatch(r'(-?)([0-9]+)(?:\.([0-9]{1,2}))?', value)
    if not match:
        raise ExecutionError(f'Invalid money value {value!r}; expected an ungrouped decimal with at most 2 fractional digits.')
    sign, whole, fraction = match.groups()
    try:
        result = (int(whole) * 100 + int((fraction or '').ljust(2, '0'))) * (-1 if sign else 1)
    except ValueError as error:
        raise ExecutionError('Money value is too large to parse.') from error
    if not -(2 ** 63) <= result < 2 ** 63:
        raise ExecutionError('Money value exceeds SQLite signed 64-bit integer capacity.')
    return result


def table_details(db, table):
    columns = [row[1] for row in db.execute(f'PRAGMA table_info({quote(table)})')]
    count = db.execute(f'SELECT COUNT(*) FROM {quote(table)}').fetchone()[0]
    return {'table': table, 'rows': count, 'columns': columns}


def load_source(db, source, base, entry):
    csv_path = (base / source['csv']).resolve()
    entry['csv_path'] = str(csv_path)
    if 'contract' in source:
        contract_path = (base / source['contract']).resolve()
        entry['contract_path'] = str(contract_path)
        entry['validation'] = validate(csv_path, config_path=contract_path)
        if entry['validation']['decision'] != 'PASS':
            finding = entry['validation']['findings'][0]
            raise ExecutionError(f'Input contract returned {entry["validation"]["decision"]}: '
                                 f'record {finding["row"]}, {finding["field"]}, {finding["code"]}.')
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames
        if not headers:
            raise InputError('Empty CSV: expected a header.')
        for header in headers:
            identifier(header, 'CSV column')
        if len({header.lower() for header in headers}) != len(headers):
            raise InputError('Duplicate CSV headers are not supported, including case-only duplicates.')
        money = source.get('money')
        if money and (money['field'] not in headers or money['integer_column'].lower() in {h.lower() for h in headers}):
            raise InputError('Money source column is missing or the derived integer column already exists.')
        definitions = [f'{quote(header)} TEXT' for header in headers]
        if money:
            definitions.append(f'{quote(money["integer_column"])} INTEGER')
        db.execute('BEGIN')
        try:
            db.execute(f'CREATE TABLE {quote(source["table"])} ({", ".join(definitions)})')
            placeholders = ','.join('?' for _ in definitions)
            insert = f'INSERT INTO {quote(source["table"])} VALUES ({placeholders})'
            for record, raw in enumerate(reader, start=2):
                if None in raw or any(value is None for value in raw.values()):
                    raise InputError(f'Record {record}: number of values does not match header.')
                values = [raw[header].strip() for header in headers]
                if money:
                    try:
                        values.append(minor_units(raw[money['field']].strip()))
                    except ExecutionError as error:
                        raise ExecutionError(f'Record {record}, {money["field"]}: {error}') from error
                db.execute(insert, values)
            details = table_details(db, source['table'])
            db.commit()
        except Exception:
            db.rollback()
            raise
    entry.update(details)


def execute_step(db, step, base, available, comparison_fields, is_checkpoint, entry):
    path = (base / step['sql']).resolve()
    entry['sql_path'] = str(path)
    sql = path.read_text(encoding='utf-8-sig').strip()
    if not sql:
        raise ExecutionError('SQL file is empty.')
    entry['sql_text'] = sql
    reads = set()

    def authorize(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_READ and table:
            normalized = table.lower()
            if normalized not in {'sqlite_master', 'sqlite_schema'}:
                if normalized not in available:
                    return sqlite3.SQLITE_DENY
                reads.add(table)
        return sqlite3.SQLITE_OK

    db.execute('BEGIN')
    try:
        db.set_authorizer(authorize)
        try:
            # CREATE TABLE AS accepts a query, not an arbitrary multi-statement script.
            db.execute(f'CREATE TABLE {quote(step["output"])} AS {sql}')
        finally:
            db.set_authorizer(None)
        details = table_details(db, step['output'])
        if is_checkpoint:
            missing = sorted(comparison_fields - set(details['columns']))
            if missing:
                raise ExecutionError('Checkpoint output is missing comparison columns: ' + ', '.join(missing))
        db.commit()
    except Exception:
        db.rollback()
        raise
    entry.update(details)
    entry['read_tables'] = sorted(reads)
    if 'join' in step:
        entry['declared_join'] = step['join']
    available.add(step['output'].lower())


def write_report(path, report):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def run_job(job_path, output_dir=None):
    job_path = Path(job_path).resolve()
    job = load_job(job_path)
    base = job_path.parent
    if output_dir is None:
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output_dir = Path('outputs') / f'{job["name"]}-{timestamp}'
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    database_path = output_dir / 'run.sqlite'
    report_path = output_dir / 'execution.json'
    report = {'schema_version': 1, 'status': 'RUNNING', 'started_at': now(),
              'job_path': str(job_path), 'job': job, 'database': str(database_path),
              'report_path': str(report_path), 'sources': [], 'steps': [],
              'scope': 'Execution only; SUCCESS does not mean datasets reconcile or meet business requirements.'}
    context = {'phase': 'database'}
    db = None
    active_entry = None
    errors = (OSError, UnicodeError, csv.Error, sqlite3.Error, ConfigError, JobError,
              InputError, ExecutionError)
    try:
        db = sqlite3.connect(database_path)
        for source in job['sources']:
            context = {'phase': 'source', 'table': source['table'],
                       'file': str((base / source['csv']).resolve())}
            active_entry = {'table': source['table'], 'status': 'RUNNING'}
            report['sources'].append(active_entry)
            load_source(db, source, base, active_entry)
            active_entry['status'] = 'SUCCESS'
        comparison = job['comparison']
        fields = set(comparison['key'] + comparison['dimensions'] + comparison['value_columns'])
        fields.add(comparison['amount_column'])
        checkpoints = {point[side].lower() for point in job['checkpoints'] for side in ('a', 'b')}
        for pipeline, steps in job['pipelines'].items():
            available = {source['table'].lower() for source in job['sources']}
            for step in steps:
                context = {'phase': 'step', 'pipeline': pipeline, 'step': step['id'],
                           'output': step['output'], 'file': str((base / step['sql']).resolve())}
                active_entry = {'pipeline': pipeline, 'id': step['id'], 'output': step['output'],
                                'status': 'RUNNING', 'started_at': now()}
                report['steps'].append(active_entry)
                execute_step(db, step, base, available, fields, step['output'].lower() in checkpoints, active_entry)
                active_entry.update(status='SUCCESS', finished_at=now())
        report['status'] = 'SUCCESS'
    except errors as error:
        report['status'] = 'FAILED'
        report['error'] = {**context, 'type': type(error).__name__, 'message': str(error)}
        if active_entry is not None:
            active_entry.update(status='FAILED', error=str(error), finished_at=now())
    finally:
        if db is not None:
            db.close()
        report['finished_at'] = now()
        write_report(report_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path, help='Job JSON; source and SQL paths are relative to this file.')
    parser.add_argument('--output-dir', type=Path, help='New run directory; existing directories are never overwritten.')
    args = parser.parse_args(argv)
    try:
        report = run_job(args.job, args.output_dir)
    except (JobError, OSError, sqlite3.Error) as error:
        print(f'EXECUTION ERROR: {error}', file=sys.stderr)
        return 2
    for source in report['sources']:
        if source['status'] == 'SUCCESS':
            print(f'Loaded {source["table"]}: {source["rows"]} rows')
    for step in report['steps']:
        if step['status'] == 'SUCCESS':
            print(f'{step["pipeline"]}/{step["id"]} -> {step["output"]}: {step["rows"]} rows')
    if report['status'] == 'FAILED':
        error = report['error']
        location = (f'pipeline {error["pipeline"]}, step {error["step"]}'
                    if error['phase'] == 'step' else f'{error["phase"]} {error.get("table", "")}')
        print(f'FAILED at {location}: {error["message"]}', file=sys.stderr)
        if 'file' in error:
            print(f'File: {error["file"]}', file=sys.stderr)
    else:
        print('EXECUTION SUCCESS: both pipelines ran; reconciliation is not evaluated.')
    print(f'Database: {report["database"]}')
    print(f'Report: {report["report_path"]}')
    return 0 if report['status'] == 'SUCCESS' else 2


if __name__ == '__main__':
    sys.exit(main())
