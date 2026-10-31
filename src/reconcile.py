"""Reconcile a shared user query, checkpoint records, and configured dimensions."""
import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path

if __package__:
    from .job_config import JobError
    from .join_diagnostics import diagnose_joins
    from .evidence_report import write_evidence_artifacts
    from .sql_runner import now, quote, run_job, write_report
else:
    from job_config import JobError
    from join_diagnostics import diagnose_joins
    from evidence_report import write_evidence_artifacts
    from sql_runner import now, quote, run_job, write_report


class ReconciliationError(ValueError):
    pass


def where_clause(filters):
    clauses, parameters = [], []
    for condition in filters:
        column = quote(condition['column'])
        operator = condition['operator']
        if operator == 'in':
            clauses.append(f'{column} IN ({", ".join("?" for _ in condition["value"])})')
            parameters.extend(condition['value'])
        else:
            sql_operator = {'eq': '=', 'gte': '>=', 'lte': '<='}[operator]
            clauses.append(f'{column} {sql_operator} ?')
            parameters.append(condition['value'])
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), parameters


def read_records(db, table, comparison, filters):
    fields = list(dict.fromkeys(comparison['key'] + comparison['value_columns']
                                + [comparison['amount_column']] + comparison['dimensions']))
    where, parameters = where_clause(filters)
    sql = f'SELECT {", ".join(quote(field) for field in fields)} FROM {quote(table)}{where}'
    records = [dict(row) for row in db.execute(sql, parameters)]
    for row_number, record in enumerate(records, start=1):
        if type(record[comparison['amount_column']]) is not int:
            raise ReconciliationError(f'{table}, result record {row_number}: {comparison["amount_column"]} '
                                      'must contain integer minor units, never NULL, REAL, or TEXT.')
        if any(value is not None and (type(value) not in (str, int, float)
                   or (type(value) is float and not math.isfinite(value))) for value in record.values()):
            raise ReconciliationError(f'{table}, result record {row_number}: unsupported comparison value type.')
    return records, {'sql': sql, 'parameters': parameters}


def key_of(record, fields):
    return tuple(record[field] for field in fields)


def valid_key(key):
    return all(value is not None and not (isinstance(value, str) and not value.strip()) for value in key)


def ordered(values):
    return sorted(values, key=lambda value: json.dumps(value, ensure_ascii=False))


def metrics(records, comparison):
    keys = {key_of(row, comparison['key']) for row in records if valid_key(key_of(row, comparison['key']))}
    return {'rows': len(records), 'unique_keys': len(keys),
            'amount_sum_cents': sum(row[comparison['amount_column']] for row in records)}


def grouped_comparison(a, b, dimensions, comparison):
    def group(records):
        buckets = defaultdict(list)
        if not dimensions:
            buckets[()] = []
        for record in records:
            buckets[key_of(record, dimensions)].append(record)
        return buckets
    groups_a, groups_b = group(a), group(b)
    results = []
    for key in ordered(groups_a.keys() | groups_b.keys()):
        left = metrics(groups_a.get(key, []), comparison)
        right = metrics(groups_b.get(key, []), comparison)
        equal = key in groups_a and key in groups_b and left == right
        results.append({'group': dict(zip(dimensions, key)), 'a_present': key in groups_a,
                        'b_present': key in groups_b, 'A': left, 'B': right,
                        'difference_cents': right['amount_sum_cents'] - left['amount_sum_cents'],
                        'status': 'MATCH' if equal else 'DIFFERENT'})
    results.sort(key=lambda row: -abs(row['difference_cents']))
    return {'status': 'MATCH' if all(group['status'] == 'MATCH' for group in results) else 'DIFFERENT',
            'group_by': dimensions, 'groups': results}


def compare_records(a, b, comparison):
    keys = comparison['key']
    amount = comparison['amount_column']
    fields = list(dict.fromkeys(comparison['value_columns'] + [amount] + comparison['dimensions']))
    buckets = {}
    invalid = {}
    duplicates = {}
    for side, rows in [('A', a), ('B', b)]:
        buckets[side] = defaultdict(list)
        invalid[side] = []
        for record in rows:
            key = key_of(record, keys)
            if valid_key(key):
                buckets[side][key].append(record)
            else:
                invalid[side].append(record)
        duplicates[side] = [{'key': dict(zip(keys, key)), 'count': len(buckets[side][key]),
                             'records': buckets[side][key]}
                            for key in ordered(buckets[side]) if len(buckets[side][key]) > 1]
    left, right = buckets['A'], buckets['B']
    only_a = [record for key in ordered(left.keys() - right.keys()) for record in left[key]]
    only_b = [record for key in ordered(right.keys() - left.keys()) for record in right[key]]
    mismatches = []
    for key in ordered(left.keys() & right.keys()):
        if len(left[key]) != 1 or len(right[key]) != 1:
            continue
        row_a, row_b = left[key][0], right[key][0]
        changed = [field for field in fields if row_a[field] != row_b[field]]
        if changed:
            mismatches.append({'key': dict(zip(keys, key)), 'changed_fields': changed,
                               'A': row_a, 'B': row_b,
                               'difference_cents': row_b[amount] - row_a[amount]})
    ambiguous = any(duplicates.values()) or any(invalid.values())
    status = ('AMBIGUOUS' if ambiguous else
              ('DIFFERENT' if only_a or only_b or mismatches else 'MATCH'))
    a_metrics, b_metrics = metrics(a, comparison), metrics(b, comparison)
    difference = b_metrics['amount_sum_cents'] - a_metrics['amount_sum_cents']
    explanation = None
    if not ambiguous:
        explanation = {
            'only_in_a_contribution_cents': -sum(row[amount] for row in only_a),
            'only_in_b_contribution_cents': sum(row[amount] for row in only_b),
            'shared_key_value_contribution_cents': sum(row['difference_cents'] for row in mismatches)}
        explanation['explained_difference_cents'] = sum(explanation.values())
        explanation['unexplained_difference_cents'] = difference - explanation['explained_difference_cents']
    return {'status': status, 'A': a_metrics, 'B': b_metrics, 'difference_cents': difference,
            'only_in_a': only_a, 'only_in_b': only_b, 'value_mismatches': mismatches,
            'duplicate_keys': duplicates, 'invalid_keys': invalid, 'amount_explanation': explanation,
            'dimensions': {field: grouped_comparison(a, b, [field], comparison)
                           for field in comparison['dimensions']}}


def analyze_execution(execution):
    if execution['status'] != 'SUCCESS':
        raise ReconciliationError('Cannot reconcile an unsuccessful execution.')
    job = execution['job']
    comparison = job['comparison']
    query = job.get('query', {'filters': [], 'group_by': comparison['dimensions']})
    report = {'schema_version': 1, 'status': 'RUNNING', 'started_at': now(),
              'difference_direction': 'B_minus_A', 'job_name': job['name'],
              'business_requirement': job['business_requirement'], 'query': query,
              'database': execution['database'], 'execution_report': execution['report_path'],
              'checkpoints': [], 'first_raw_divergence': None, 'first_query_scope_divergence': None,
              'limitation': 'Explicit aligned checkpoints and a common query request; observed divergence does not establish business root cause.'}
    database = Path(execution['database']).resolve()
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        for checkpoint in job['checkpoints']:
            entry = {'name': checkpoint['name'], 'a_table': checkpoint['a'], 'b_table': checkpoint['b']}
            try:
                a, _ = read_records(db, checkpoint['a'], comparison, [])
                b, _ = read_records(db, checkpoint['b'], comparison, [])
                entry['raw'] = compare_records(a, b, comparison)
                scoped_a, sql_a = read_records(db, checkpoint['a'], comparison, query['filters'])
                scoped_b, sql_b = read_records(db, checkpoint['b'], comparison, query['filters'])
                entry['query_scope'] = compare_records(scoped_a, scoped_b, comparison)
                entry['filter_execution'] = {'A': sql_a, 'B': sql_b}
            except (sqlite3.Error, ReconciliationError) as error:
                raise ReconciliationError(f'Checkpoint {checkpoint["name"]}: {error}') from error
            report['checkpoints'].append(entry)
            if entry['raw']['status'] != 'MATCH' and report['first_raw_divergence'] is None:
                report['first_raw_divergence'] = checkpoint['name']
            if entry['query_scope']['status'] != 'MATCH' and report['first_query_scope_divergence'] is None:
                report['first_query_scope_divergence'] = checkpoint['name']
        final = report['checkpoints'][-1]
        report['query_result'] = grouped_comparison(scoped_a, scoped_b, query['group_by'], comparison)
        report['detail_status'] = final['query_scope']['status']
        report['status'] = ('AMBIGUOUS' if report['detail_status'] == 'AMBIGUOUS' else
                            ('DIFFERENT' if report['detail_status'] != 'MATCH'
                             or report['query_result']['status'] != 'MATCH' else 'MATCH'))
        report['final_checkpoint'] = final['name']
        report['join_diagnostics'] = diagnose_joins(db, execution)
    report['finished_at'] = now()
    return report


def csv_value(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def export_csv(output_dir, report, comparison):
    directory = output_dir / 'differences'
    directory.mkdir()
    final = report['checkpoints'][-1]['query_scope']
    fields = list(dict.fromkeys(comparison['key'] + comparison['value_columns']
                                + [comparison['amount_column']] + comparison['dimensions']))
    for name in ('only_in_a', 'only_in_b'):
        write_csv(directory / f'{name}.csv', fields, final[name])
    write_csv(directory / 'value_mismatch.csv', ['key', 'changed_fields', 'A', 'B', 'difference_cents'],
              final['value_mismatches'])
    grain = []
    for side in ('A', 'B'):
        grain.extend({'side': side, 'issue': 'duplicate_key', **row} for row in final['duplicate_keys'][side])
        grain.extend({'side': side, 'issue': 'invalid_key', 'key': None, 'count': 1, 'records': [row]}
                     for row in final['invalid_keys'][side])
    write_csv(directory / 'grain_issues.csv', ['side', 'issue', 'key', 'count', 'records'], grain)
    write_csv(directory / 'query_groups.csv', ['group', 'a_present', 'b_present', 'A', 'B', 'difference_cents', 'status'],
              report['query_result']['groups'])
    summary = []
    for checkpoint in report['checkpoints']:
        for scope in ('raw', 'query_scope'):
            detail = checkpoint[scope]
            summary.append({'checkpoint': checkpoint['name'], 'scope': scope, 'status': detail['status'],
                            'A': detail['A'], 'B': detail['B'], 'difference_cents': detail['difference_cents']})
    write_csv(directory / 'checkpoints.csv', ['checkpoint', 'scope', 'status', 'A', 'B', 'difference_cents'], summary)
    return str(directory)


def run_reconciliation(job_path, output_dir=None):
    execution = run_job(job_path, output_dir)
    directory = Path(execution['report_path']).parent
    path = directory / 'reconciliation.json'
    if execution['status'] != 'SUCCESS':
        report = {'schema_version': 1, 'status': 'ERROR', 'error': execution['error'],
                  'execution_report': execution['report_path'], 'database': execution['database']}
    else:
        try:
            report = analyze_execution(execution)
            report['csv_directory'] = export_csv(directory, report, execution['job']['comparison'])
        except (OSError, sqlite3.Error, ReconciliationError) as error:
            report = {'schema_version': 1, 'status': 'ERROR',
                      'error': {'phase': 'reconciliation', 'message': str(error)},
                      'execution_report': execution['report_path'], 'database': execution['database']}
    report['report_path'] = str(path)
    write_evidence_artifacts(directory, report, execution)
    write_report(path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('--output-dir', type=Path, help='New run directory; existing directories are not overwritten.')
    args = parser.parse_args(argv)
    try:
        report = run_reconciliation(args.job, args.output_dir)
    except (JobError, OSError, sqlite3.Error) as error:
        print(f'RECONCILIATION ERROR: {error}', file=sys.stderr)
        return 2
    print(f'RECONCILIATION: {report["status"]}')
    if report['status'] == 'ERROR':
        print(json.dumps(report['error'], ensure_ascii=False), file=sys.stderr)
    else:
        print(f'Final query groups: {report["query_result"]["status"]}; scoped details: {report["detail_status"]}')
        print(f'First raw divergence: {report["first_raw_divergence"] or "none"}')
        print(f'First query-scope divergence: {report["first_query_scope_divergence"] or "none"}')
        for checkpoint in report['checkpoints']:
            detail = checkpoint['query_scope']
            print(f'{checkpoint["name"]}: {detail["status"]}; A={detail["A"]["amount_sum_cents"]} cents; '
                  f'B={detail["B"]["amount_sum_cents"]} cents; B-A={detail["difference_cents"]} cents')
        print(f'CSV differences: {report["csv_directory"]}')
    print(f'Report: {report["report_path"]}')
    print(f'Human report: {report["human_report"]}')
    return {'MATCH': 0, 'DIFFERENT': 1}.get(report['status'], 2)


if __name__ == '__main__':
    sys.exit(main())
