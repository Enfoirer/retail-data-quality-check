"""Validate declarative JSON contracts. No executable expressions are accepted."""
import json
from pathlib import Path

DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y')
SIGN_RULES = {'positive', 'negative', 'zero', 'nonnegative', 'nonpositive', 'any'}


class ConfigError(ValueError):
    pass


def _fail(message):
    raise ConfigError(message)


def _object(value, label, keys, required=()):
    if not isinstance(value, dict):
        _fail(f'{label} must be an object.')
    unknown = set(value) - set(keys)
    missing = set(required) - set(value)
    if unknown:
        _fail(f'{label}: unknown keys: {", ".join(sorted(unknown))}.')
    if missing:
        _fail(f'{label}: missing keys: {", ".join(sorted(missing))}.')


def _strings(value, label):
    if (not isinstance(value, list) or not value
            or any(not isinstance(item, str) or not item or item != item.strip() for item in value)):
        _fail(f'{label} must be a nonempty list of nonblank, trimmed strings.')
    if len(set(value)) != len(value):
        _fail(f'{label} must not contain duplicates.')


def validate_contract(config):
    _object(config, 'contract',
            ('name', 'required', 'unique_key', 'amount', 'date', 'allowed_values', 'status_amount'),
            ('name', 'required', 'unique_key'))
    if not isinstance(config['name'], str) or not config['name'].strip():
        _fail('name must be a nonblank string.')
    _strings(config['required'], 'required')
    _strings(config['unique_key'], 'unique_key')
    fields = set(config['required'])

    def field(value, label):
        if not isinstance(value, str) or value not in fields:
            _fail(f'{label} must name a field in required.')

    for value in config['unique_key']:
        field(value, 'unique_key')
    if 'amount' in config:
        rule = config['amount']
        _object(rule, 'amount', ('field', 'decimal_places'), ('field', 'decimal_places'))
        field(rule['field'], 'amount.field')
        places = rule['decimal_places']
        if type(places) is not int or not 0 <= places <= 6:
            _fail('amount.decimal_places must be an integer from 0 to 6.')
    if 'date' in config:
        rule = config['date']
        _object(rule, 'date', ('field', 'format', 'review_alternate_formats'), ('field', 'format'))
        field(rule['field'], 'date.field')
        if rule['format'] not in DATE_FORMATS:
            _fail(f'date.format must be one of {DATE_FORMATS}.')
        if type(rule.get('review_alternate_formats', False)) is not bool:
            _fail('date.review_alternate_formats must be a boolean.')
        if rule.get('review_alternate_formats') and rule['format'] != '%Y-%m-%d':
            _fail('Alternate-format review is supported only for an ISO default date format.')
    if 'allowed_values' in config:
        allowed = config['allowed_values']
        if not isinstance(allowed, dict) or not allowed:
            _fail('allowed_values must be a nonempty object.')
        for name, values in allowed.items():
            field(name, 'allowed_values key')
            _strings(values, f'allowed_values.{name}')
    if 'status_amount' in config:
        rule = config['status_amount']
        _object(rule, 'status_amount', ('status_field', 'rules'), ('status_field', 'rules'))
        field(rule['status_field'], 'status_amount.status_field')
        if 'amount' not in config:
            _fail('status_amount requires an amount rule.')
        statuses = config.get('allowed_values', {}).get(rule['status_field'])
        if statuses is None:
            _fail('status_amount.status_field must have an allowed_values list.')
        if not isinstance(rule['rules'], dict) or set(rule['rules']) != set(statuses):
            _fail('status_amount.rules must cover exactly the allowed status values.')
        if any(not isinstance(value, str) or value not in SIGN_RULES for value in rule['rules'].values()):
            _fail(f'status_amount rules must use {sorted(SIGN_RULES)}.')
    return config


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            _fail(f'Duplicate JSON key: {key}.')
        obj[key] = value
    return obj


def load_contract(path):
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
        config = json.loads(text, object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError(f'Cannot read contract {path}: {error}') from error
    return validate_contract(config)
