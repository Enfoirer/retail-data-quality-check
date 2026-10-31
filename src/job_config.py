"""Validate the explicit two-pipeline job format before execution."""
import json
import re
from pathlib import Path

IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


class JobError(ValueError):
    pass


def object_fields(value, label, required, optional=()):
    if not isinstance(value, dict):
        raise JobError(f'{label} must be an object.')
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise JobError(f'{label}: missing keys {sorted(missing)}; unknown keys {sorted(extra)}.')


def text(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise JobError(f'{label} must be a nonblank, trimmed string.')


def identifier(value, label):
    text(value, label)
    if not IDENTIFIER.fullmatch(value) or value.lower().startswith('sqlite_'):
        raise JobError(f'{label} must be an ASCII SQL identifier without the sqlite_ prefix.')


def names(value, label, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise JobError(f'{label} must be a {"possibly empty" if allow_empty else "nonempty"} list.')
    for item in value:
        identifier(item, label)
    if len({item.lower() for item in value}) != len(value):
        raise JobError(f'{label} contains duplicate names.')


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JobError(f'Duplicate JSON key: {key}.')
        result[key] = value
    return result


def load_job(path):
    path = Path(path).resolve()
    try:
        job = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_json)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobError(f'Cannot read job {path}: {error}') from error
    object_fields(job, 'job', ('schema_version', 'name', 'business_requirement', 'sources',
                              'pipelines', 'checkpoints', 'comparison'), ('query',))
    if type(job['schema_version']) is not int or job['schema_version'] != 1:
        raise JobError('Only job schema_version 1 is supported.')
    identifier(job['name'], 'name')
    text(job['business_requirement'], 'business_requirement')
    if not isinstance(job['sources'], list) or not job['sources']:
        raise JobError('sources must be a nonempty list.')
    tables = set()
    source_names = set()
    for source in job['sources']:
        object_fields(source, 'source', ('table', 'csv'), ('contract', 'money'))
        identifier(source['table'], 'source.table')
        table = source['table'].lower()
        if table in tables:
            raise JobError(f'Duplicate table name: {source["table"]}.')
        tables.add(table)
        source_names.add(table)
        text(source['csv'], 'source.csv')
        if 'contract' in source:
            text(source['contract'], 'source.contract')
        if 'money' in source:
            money = source['money']
            object_fields(money, 'source.money', ('field', 'integer_column'))
            identifier(money['field'], 'money.field')
            identifier(money['integer_column'], 'money.integer_column')
            if money['field'].lower() == money['integer_column'].lower():
                raise JobError('money.integer_column must differ from the original amount column.')
    object_fields(job['pipelines'], 'pipelines', ('A', 'B'))
    outputs = {}
    positions = {}
    for pipeline, steps in job['pipelines'].items():
        if not isinstance(steps, list) or not steps:
            raise JobError(f'Pipeline {pipeline} must have at least one step.')
        available = set(source_names)
        ids = set()
        outputs[pipeline] = set()
        positions[pipeline] = {}
        for index, step in enumerate(steps):
            object_fields(step, f'Pipeline {pipeline} step', ('id', 'output', 'sql'), ('join',))
            identifier(step['id'], 'step.id')
            identifier(step['output'], 'step.output')
            text(step['sql'], 'step.sql')
            if step['id'].lower() in ids:
                raise JobError(f'Pipeline {pipeline}: duplicate step id {step["id"]}.')
            ids.add(step['id'].lower())
            output = step['output'].lower()
            if output in tables:
                raise JobError(f'Duplicate table/output name: {step["output"]}.')
            if 'join' in step:
                join = step['join']
                object_fields(join, 'step.join', ('left', 'right', 'left_on', 'right_on', 'expected'))
                for side in ('left', 'right'):
                    identifier(join[side], f'join.{side}')
                    if join[side].lower() not in available:
                        raise JobError(f'Pipeline {pipeline}/{step["id"]}: join.{side} must reference an available table.')
                    names(join[f'{side}_on'], f'join.{side}_on')
                if len(join['left_on']) != len(join['right_on']):
                    raise JobError('Join key lists must have the same length.')
                if join['expected'] != 'many_to_one':
                    raise JobError('Only expected many_to_one joins are supported.')
            tables.add(output)
            available.add(output)
            outputs[pipeline].add(output)
            positions[pipeline][output] = index
    comparison = job['comparison']
    object_fields(comparison, 'comparison', ('key', 'amount_column', 'dimensions', 'value_columns'))
    names(comparison['key'], 'comparison.key')
    identifier(comparison['amount_column'], 'comparison.amount_column')
    names(comparison['dimensions'], 'comparison.dimensions', allow_empty=True)
    names(comparison['value_columns'], 'comparison.value_columns', allow_empty=True)
    if 'query' in job:
        query = job['query']
        object_fields(query, 'query', ('filters', 'group_by'))
        names(query['group_by'], 'query.group_by', allow_empty=True)
        if not set(query['group_by']) <= set(comparison['dimensions']):
            raise JobError('query.group_by must use configured comparison dimensions.')
        if not isinstance(query['filters'], list):
            raise JobError('query.filters must be a list.')
        available_fields = set(comparison['key'] + comparison['value_columns'] + comparison['dimensions'])
        available_fields.add(comparison['amount_column'])
        for condition in query['filters']:
            object_fields(condition, 'query filter', ('column', 'operator', 'value'))
            if not isinstance(condition['column'], str) or condition['column'] not in available_fields:
                raise JobError('Query filters must reference fields available at all comparison checkpoints.')
            if condition['operator'] not in ('eq', 'in', 'gte', 'lte'):
                raise JobError('Query filter operator must be eq, in, gte, or lte.')
            values = condition['value'] if condition['operator'] == 'in' else [condition['value']]
            if not isinstance(values, list) or not values or any(type(value) not in (str, int) for value in values):
                raise JobError('Query values must be strings or integers; in requires a nonempty list.')
            if any(type(value) is int and not -(2 ** 63) <= value < 2 ** 63 for value in values):
                raise JobError('Query integer values must fit SQLite signed 64-bit capacity.')
            if condition['column'] == comparison['amount_column'] and any(type(value) is not int for value in values):
                raise JobError('Money filters must use integer minor units.')
    if not isinstance(job['checkpoints'], list) or not job['checkpoints']:
        raise JobError('checkpoints must be a nonempty list.')
    checkpoint_names = set()
    previous = {'A': -1, 'B': -1}
    for checkpoint in job['checkpoints']:
        object_fields(checkpoint, 'checkpoint', ('name', 'a', 'b'))
        identifier(checkpoint['name'], 'checkpoint.name')
        if checkpoint['name'].lower() in checkpoint_names:
            raise JobError('Checkpoint names must be unique.')
        checkpoint_names.add(checkpoint['name'].lower())
        for pipeline, side in [('A', 'a'), ('B', 'b')]:
            identifier(checkpoint[side], f'checkpoint.{side}')
            output = checkpoint[side].lower()
            if output not in outputs[pipeline]:
                raise JobError(f'checkpoint.{side} must reference an output of pipeline {pipeline}.')
            position = positions[pipeline][output]
            if position <= previous[pipeline]:
                raise JobError('Checkpoints must follow pipeline execution order without repeating outputs.')
            previous[pipeline] = position
    if any(job['checkpoints'][-1][side].lower() != job['pipelines'][pipeline][-1]['output'].lower()
           for pipeline, side in [('A', 'a'), ('B', 'b')]):
        raise JobError('The last checkpoint must reference both final pipeline outputs.')
    return job
