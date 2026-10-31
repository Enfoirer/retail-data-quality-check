"""Inspect declared equijoins against retained rows; preserve all evidence."""
from collections import Counter
import math

if __package__:
    from .sql_runner import quote
else:
    from sql_runner import quote


def columns(db, table):
    return [row[1] for row in db.execute(f'PRAGMA table_info({quote(table)})')]


def rowid_name(fields):
    names = {field.lower() for field in fields}
    for candidate in ('_rowid_', 'rowid', 'oid'):
        if candidate not in names:
            return candidate
    raise ValueError('No unshadowed SQLite rowid is available for tracing.')


def snapshots(db, table):
    fields = columns(db, table)
    rid = rowid_name(fields)
    return [{'sqlite_rowid': row[0], 'values': dict(zip(fields, tuple(row)[1:]))}
            for row in db.execute(f'SELECT {quote(rid)}, * FROM {quote(table)} ORDER BY {quote(rid)}')]


def traceable(rows):
    return all(value is None or type(value) in (str, int)
               or (type(value) is float and math.isfinite(value))
               for row in rows for value in row['values'].values())


def business_key(row, fields):
    return tuple(row['values'][field] for field in fields)


def usable(key):
    return all(value is not None and not (isinstance(value, str) and not value.strip()) for value in key)


def diagnose_one(db, step, comparison):
    join = step['declared_join']
    left, right, output = join['left'], join['right'], step['output']
    result = {'pipeline': step['pipeline'], 'step': step['id'], 'output': output,
              'declared_join': join, 'sql_path': step['sql_path'], 'sql_text': step['sql_text'],
              'read_tables': step['read_tables'], 'status': 'INCONCLUSIVE',
              'scope': 'Raw stage; declared equality keys and retained output observations. SQL predicate equivalence is not inferred.'}
    if not {left.lower(), right.lower()} <= {name.lower() for name in step['read_tables']}:
        result['reason'] = 'Declared left/right tables are not both observed SQL read dependencies.'
        return result
    key_fields, amount = comparison['key'], comparison['amount_column']
    left_fields, right_fields, output_fields = columns(db, left), columns(db, right), columns(db, output)
    requirements = [(left, left_fields, key_fields + [amount] + join['left_on']),
                    (right, right_fields, join['right_on']),
                    (output, output_fields, key_fields + [amount])]
    for table, actual, required in requirements:
        missing = sorted(set(required) - set(actual))
        if missing:
            result['reason'] = f'Declared diagnostic columns missing from {table}: {missing}.'
            return result
    before, after = snapshots(db, left), snapshots(db, output)
    if any(type(row['values'][amount]) is not int for row in before + after):
        result['reason'] = 'Join amount diagnostics require integer minor units before and after.'
        return result
    result.update(left_table=left, right_table=right, left_rows=len(before), output_rows=len(after),
                  row_delta=len(after) - len(before),
                  left_amount_cents=sum(row['values'][amount] for row in before),
                  output_amount_cents=sum(row['values'][amount] for row in after))
    result['amount_delta_cents'] = result['output_amount_cents'] - result['left_amount_cents']
    if not traceable(before + after):
        result['reason'] = 'Full-row trace contains unsupported non-JSON scalar values; inspect the retained database.'
        return result
    counts = Counter(business_key(row, key_fields) for row in before)
    if any(not usable(key) or count != 1 for key, count in counts.items()):
        result['reason'] = 'Left business keys are missing or already duplicated; per-record attribution is ambiguous.'
        return result
    output_by_key = {}
    for row in after:
        output_by_key.setdefault(business_key(row, key_fields), []).append(row)
    left_rid, right_rid = rowid_name(left_fields), rowid_name(right_fields)
    predicates = ' AND '.join(f'l.{quote(a)} = r.{quote(b)}' for a, b in zip(join['left_on'], join['right_on']))
    match_sql = (f'SELECT r.{quote(right_rid)}, r.* FROM {quote(left)} AS l '
                 f'JOIN {quote(right)} AS r ON {predicates} WHERE l.{quote(left_rid)} = ? '
                 f'ORDER BY r.{quote(right_rid)}')
    result['right_match_sql'] = match_sql
    observations = []
    for row in before:
        key = business_key(row, key_fields)
        matches = [{'sqlite_rowid': match[0], 'values': dict(zip(right_fields, tuple(match)[1:]))}
                   for match in db.execute(match_sql, (row['sqlite_rowid'],))]
        if not traceable(matches):
            result['reason'] = 'Right-match trace contains unsupported non-JSON scalar values; inspect the retained database.'
            return result
        produced = output_by_key.get(key, [])
        copied_amount = all(item['values'][amount] == row['values'][amount] for item in produced)
        observations.append({'key': dict(zip(key_fields, key)), 'left_record': row,
                             'right_match_count': len(matches), 'right_matches': matches,
                             'output_count': len(produced), 'output_records': produced,
                             'amount_preserved_per_copy': copied_amount,
                             'observed_amount_delta_cents': sum(item['values'][amount] for item in produced) - row['values'][amount],
                             'fanout_supported': len(matches) > 1 and len(produced) == len(matches)})
    expected_rows = sum(max(row['right_match_count'], 1) for row in observations)
    expected_amount = sum(row['left_record']['values'][amount] * max(row['right_match_count'], 1) for row in observations)
    new_keys = set(output_by_key) - set(counts)
    model_matches = not new_keys and all(row['output_count'] == max(row['right_match_count'], 1) for row in observations)
    fanout = [row for row in observations if row['fanout_supported']]
    result.update(observations=observations, fanout_keys=fanout,
                  unmatched_left_rows=sum(row['right_match_count'] == 0 for row in observations),
                  matched_multirow_left_records=sum(row['right_match_count'] > 1 for row in observations),
                  declared_left_join_predicted_rows=expected_rows,
                  declared_left_join_predicted_amount_cents=expected_amount,
                  row_model_matches=model_matches,
                  replication_amount_model_matches=model_matches and all(row['amount_preserved_per_copy'] for row in observations)
                  and expected_amount == result['output_amount_cents'])
    if fanout:
        result['status'] = 'FANOUT'
        result['reason'] = 'Observed output expansion at business keys that have multiple declared right-side matches.'
    elif model_matches and not result['matched_multirow_left_records']:
        result['status'] = 'PASS'
        result['reason'] = 'No observed many-to-one cardinality violation for the matched left records.'
    else:
        result['reason'] = 'Observed SQL output does not establish the declared simple left-join multiplicity model.'
    return result


def diagnose_joins(db, execution):
    results = []
    for step in execution['steps']:
        if step.get('status') == 'SUCCESS' and 'declared_join' in step:
            try:
                result = diagnose_one(db, step, execution['job']['comparison'])
            except ValueError as error:
                result = {'pipeline': step['pipeline'], 'step': step['id'], 'output': step['output'],
                          'status': 'INCONCLUSIVE', 'reason': str(error),
                          'sql_path': step['sql_path'], 'sql_text': step['sql_text']}
            results.append(result)
    return results
