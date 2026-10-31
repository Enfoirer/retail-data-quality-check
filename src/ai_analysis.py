"""Optional evidence-grounded analysis with strict local citation/value validation."""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

if __package__:
    from .sql_runner import now, write_report
else:
    from sql_runner import now, write_report

DEFAULT_MODEL = 'gpt-5-mini'
PROMPT_PATH = Path(__file__).resolve().parents[1] / 'prompts/reconciliation_analysis.txt'
MAX_PACKET_CHARS = 60000


class AIError(ValueError):
    pass


class AIUnavailable(AIError):
    pass


def strict_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise AIError(f'Duplicate JSON key in model output: {key}.')
            result[key] = value
        return result

    def reject_constant(value):
        raise AIError(f'Non-finite JSON constant: {value}.')

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise AIError('Non-finite JSON number.')
        return parsed
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant, parse_float=finite_float)
    except json.JSONDecodeError as error:
        raise AIError('Model output is not valid JSON.') from error


def pointer_value(data, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise AIError('Evidence pointer must be empty or begin with /.')
    if not pointer:
        return data
    current = data
    try:
        for token in pointer[1:].split('/'):
            if re.search(r'~(?![01])', token):
                raise AIError('Invalid JSON pointer escape.')
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(current, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', token):
                    raise AIError('Invalid JSON pointer array index.')
                current = current[int(token)]
            elif isinstance(current, dict):
                current = current[token]
            else:
                raise AIError('Evidence pointer traverses a scalar.')
    except (KeyError, IndexError, ValueError) as error:
        raise AIError(f'Evidence pointer does not resolve: {pointer}.') from error
    return current


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def project_item(item):
    data = item['data']
    if item['kind'] == 'sql_step':
        fields = ('pipeline', 'id', 'output', 'status', 'sql_text', 'read_tables', 'rows', 'declared_join', 'error')
    elif item['kind'] == 'checkpoint':
        fields = ('status', 'A', 'B', 'difference_cents', 'amount_explanation')
    elif item['kind'] == 'join_diagnosis':
        fields = ('pipeline', 'step', 'status', 'reason', 'declared_join', 'left_table', 'right_table',
                  'left_rows', 'output_rows', 'row_delta', 'left_amount_cents', 'output_amount_cents',
                  'amount_delta_cents', 'matched_multirow_left_records', 'row_model_matches',
                  'replication_amount_model_matches', 'fanout_keys')
    else:
        return {'id': item['id'], 'kind': item['kind'], 'summary': item['summary'], 'data': data}
    return {'id': item['id'], 'kind': item['kind'], 'summary': item['summary'],
            'data': {key: data[key] for key in fields if key in data}}


def build_packet(report_path):
    report_path = Path(report_path).resolve()
    report = strict_json(report_path.read_text(encoding='utf-8'))
    ledger_path = Path(report['evidence_file'])
    ledger_text = ledger_path.read_text(encoding='utf-8')
    ledger = strict_json(ledger_text)
    if not isinstance(ledger.get('items'), list) or not ledger['items']:
        raise AIError('The evidence ledger is empty or invalid.')
    # Check the ledger against saved artifacts before trusting or sending it.
    originals = {}
    for item in ledger['items']:
        evidence_id = item['id']
        if evidence_id in originals or not re.fullmatch(r'E[0-9]+', evidence_id):
            raise AIError('Evidence IDs must be unique E-number strings.')
        source = item['source']
        if source['artifact'] not in ('execution.json', 'reconciliation.json'):
            raise AIError('Evidence must reference an expected local artifact.')
        saved = strict_json((report_path.parent / source['artifact']).read_text(encoding='utf-8'))
        actual = pointer_value(saved, source['json_pointer'])
        if canonical(actual) != canonical(item['data']):
            raise AIError(f'Evidence {evidence_id} no longer matches the saved artifact.')
        originals[evidence_id] = item
    packet = {'deterministic_status': report['status'], 'evidence': [project_item(item) for item in ledger['items']],
              'evidence_projection': 'Only supplied data fields can be cited. Paths start at an evidence item: /data or /data/field.'}
    if len(canonical(packet)) > MAX_PACKET_CHARS:
        raise AIError('Evidence exceeds the small-demo context limit; no truncated analysis is sent.')
    return packet, originals, hashlib.sha256(ledger_text.encode()).hexdigest()


def output_schema(ids):
    def obj(properties):
        return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}
    string = {'type': 'string'}
    references = {'type': 'array', 'items': {'type': 'string', 'enum': ids}}
    anchor = obj({'evidence_id': {'type': 'string', 'enum': ids},
                  'pointer': {'type': 'string', 'description': 'RFC 6901 path within the evidence item. Use /data for a scalar requirement, /data/status for a status, /data/sql_text for SQL.'},
                  'value_json': string})
    return obj({
        'reported_status': {'type': 'string', 'enum': ['MATCH', 'DIFFERENT', 'AMBIGUOUS', 'ERROR']},
        'observations': {'type': 'array', 'items': obj({'statement': string, 'anchors': {'type': 'array', 'items': anchor}})},
        'hypotheses': {'type': 'array', 'items': obj({'statement': string, 'evidence_ids': references, 'verification': string})},
        'recommended_checks': {'type': 'array', 'items': obj({'action': string, 'evidence_ids': references, 'expected_result': string})},
        'open_questions': {'type': 'array', 'items': string},
        'limitations': {'type': 'array', 'items': string}})


def validate_analysis(content, packet, originals):
    def shape(value, keys):
        if not isinstance(value, dict) or set(value) != set(keys):
            raise AIError('Model response has missing or unsupported fields.')

    def nonblank(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise AIError('Model text must be a nonblank string of at most 4000 characters.')

    sent = {item['id']: item for item in packet['evidence']}
    shape(content, ('reported_status', 'observations', 'hypotheses', 'recommended_checks', 'open_questions', 'limitations'))
    if content['reported_status'] != packet['deterministic_status']:
        raise AIError('Model attempted to change the deterministic status.')
    limits = {'observations': (1, 4), 'hypotheses': (0, 3), 'recommended_checks': (0, 4),
              'open_questions': (0, 8), 'limitations': (1, 8)}
    for name, (minimum, maximum) in limits.items():
        if not isinstance(content[name], list) or not minimum <= len(content[name]) <= maximum:
            raise AIError(f'Invalid number of {name}.')
    anchor_count = 0
    for observation in content['observations']:
        shape(observation, ('statement', 'anchors'))
        nonblank(observation['statement'])
        if not isinstance(observation['anchors'], list) or not 1 <= len(observation['anchors']) <= 10:
            raise AIError('Each observation requires 1–10 exact evidence anchors.')
        for anchor in observation['anchors']:
            shape(anchor, ('evidence_id', 'pointer', 'value_json'))
            evidence_id = anchor['evidence_id']
            if not isinstance(evidence_id, str) or evidence_id not in sent:
                raise AIError('Model cited an unknown evidence ID.')
            pointer = anchor['pointer']
            if not isinstance(pointer, str) or (pointer != '/data' and not pointer.startswith('/data/')):
                raise AIError('Model anchors must point to /data or its supplied fields.')
            nonblank(anchor['value_json'])
            quoted = strict_json(anchor['value_json'])
            supplied = pointer_value(sent[evidence_id], pointer)
            original = pointer_value(originals[evidence_id], pointer)
            if canonical(quoted) != canonical(supplied) or canonical(quoted) != canonical(original):
                raise AIError(f'Model anchor value does not match evidence {evidence_id}.')
            anchor_count += 1
    for name, text_fields in [('hypotheses', ('statement', 'verification')),
                              ('recommended_checks', ('action', 'expected_result'))]:
        for entry in content[name]:
            shape(entry, (*text_fields, 'evidence_ids'))
            for field in text_fields:
                nonblank(entry[field])
            refs = entry['evidence_ids']
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in sent for ref in refs):
                raise AIError('Hypotheses and checks must cite supplied evidence IDs.')
    for name in ('open_questions', 'limitations'):
        for value in content[name]:
            nonblank(value)
    return {'evidence_ids_valid': True, 'anchor_values_valid': True, 'anchors_checked': anchor_count,
            'deterministic_status_preserved': True,
            'semantic_entailment': 'Not automatically verified; correct references do not prove the wording is justified.'}


def openai_provider(request):
    if not os.environ.get('OPENAI_API_KEY'):
        raise AIUnavailable('OPENAI_API_KEY is not set; deterministic artifacts remain available.')
    try:
        from openai import OpenAI
    except ImportError as error:
        raise AIUnavailable('Optional dependency missing; install requirements-ai.txt.') from error
    kwargs = {'model': request['model'], 'instructions': request['instructions'],
              'input': canonical(request['packet']), 'store': False, 'max_output_tokens': 4500,
              'text': {'format': {'type': 'json_schema', 'name': 'reconciliation_analysis',
                                  'strict': True, 'schema': request['schema']}}}
    if request['model'].startswith('gpt-5'):
        kwargs['reasoning'] = {'effort': 'low'}
    try:
        with OpenAI(timeout=45, max_retries=0) as client:
            response = client.responses.create(**kwargs)
    except Exception as error:
        # Do not persist provider exception bodies, which can contain request details.
        status = getattr(error, 'status_code', None)
        raise AIUnavailable(f'Provider request failed ({type(error).__name__}, HTTP {status}); no result fabricated.') from error
    return {'output_text': response.output_text, 'response_id': response.id, 'model': response.model,
            'status': response.status, 'usage': response.usage.model_dump() if response.usage else None}


def render_analysis(result):
    lines = ['# AI Reconciliation Analysis', '', f'Analysis status: **{result["status"]}**.', '',
             'This is an optional model interpretation. The deterministic report and database remain authoritative.', '']
    if result['status'] != 'SUCCESS':
        return '\n'.join(lines + [result['message'], '', 'No substitute model explanation was generated.', ''])
    content = result['content']
    lines += [f'Model: {result["model"]}. Deterministic outcome: **{content["reported_status"]}**.', '',
              '## Observations with Verified Evidence Anchors', '']
    for observation in content['observations']:
        lines += ['- ' + observation['statement']]
        for anchor in observation['anchors']:
            lines += [f'  - [{anchor["evidence_id"]}] `{anchor["pointer"] or "(root)"}` = `{anchor["value_json"]}`']
    lines += ['', '## Hypotheses — Not Established Causes', '']
    for hypothesis in content['hypotheses']:
        refs = ', '.join(f'[{ref}]' for ref in hypothesis['evidence_ids'])
        lines += [f'- {hypothesis["statement"]} {refs}', f'  - Verification: {hypothesis["verification"]}']
    if not content['hypotheses']:
        lines += ['No additional cause hypothesis was proposed.']
    lines += ['', '## Recommended Checks — No Actions Executed', '']
    for check in content['recommended_checks']:
        refs = ', '.join(f'[{ref}]' for ref in check['evidence_ids'])
        lines += [f'- {check["action"]} {refs}', f'  - Expected observation: {check["expected_result"]}']
    if not content['recommended_checks']:
        lines += ['No additional investigation check was proposed.']
    lines += ['', '## Open Questions', ''] + ['- ' + value for value in content['open_questions']]
    if not content['open_questions']:
        lines += ['No additional question was proposed.']
    lines += ['', '## Limitations', ''] + ['- ' + value for value in content['limitations']]
    lines += ['', 'Local validation checks IDs, exact pointer values, structure, and unchanged deterministic status. '
              'It does not establish that every natural-language statement follows from its evidence. Human review is required.', '',
              'Evidence IDs refer to the parent run\'s evidence.json and its saved-artifact pointers. '
              'request.json records the supplied projection; response.json preserves model output, including rejected output.', '']
    return '\n'.join(lines)


def analyze_run(report_path, model=None, output_dir=None, provider=None):
    report_path = Path(report_path).resolve()
    directory = Path(output_dir).resolve() if output_dir else report_path.parent / 'ai'
    directory.mkdir(parents=True, exist_ok=False)
    model = model or os.environ.get('OPENAI_MODEL') or DEFAULT_MODEL
    result = {'schema_version': 1, 'status': 'RUNNING', 'started_at': now(), 'model': model,
              'provider': 'openai' if provider is None else 'injected_test_provider',
              'source_report': str(report_path)}
    response = None
    try:
        packet, originals, fingerprint = build_packet(report_path)
        request = {'model': model, 'instructions': PROMPT_PATH.read_text(encoding='utf-8'),
                   'packet': packet, 'schema': output_schema([item['id'] for item in packet['evidence']]),
                   'evidence_sha256': fingerprint}
        write_report(directory / 'request.json', request)
        response = (provider or openai_provider)(request)
        write_report(directory / 'response.json', response)
        if response.get('status') != 'completed' or not response.get('output_text'):
            raise AIUnavailable('Model returned no completed usable JSON response (incomplete output or refusal).')
        content = strict_json(response['output_text'])
        result['validation'] = validate_analysis(content, packet, originals)
        result.update(status='SUCCESS', content=content, response_id=response.get('response_id'),
                      resolved_model=response.get('model'), usage=response.get('usage'))
    except AIUnavailable as error:
        result.update(status='UNAVAILABLE', message=str(error))
    except (AIError, OSError, KeyError, TypeError) as error:
        result.update(status='REJECTED', message=str(error))
    result.update(finished_at=now(), report_path=str(directory / 'analysis.json'),
                  human_report=str(directory / 'analysis.md'))
    write_report(directory / 'analysis.json', result)
    (directory / 'analysis.md').write_text(render_analysis(result), encoding='utf-8')
    # Only add optional-analysis metadata; computed values and evidence pointers stay intact.
    original_report = strict_json(report_path.read_text(encoding='utf-8'))
    original_report['ai_analysis'] = {key: result[key] for key in ('status', 'model', 'report_path', 'human_report')}
    write_report(report_path, original_report)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, help='Existing reconciliation.json from a completed local run.')
    parser.add_argument('--model', default=None)
    parser.add_argument('--output-dir', type=Path, help='New optional-analysis directory.')
    args = parser.parse_args(argv)
    try:
        result = analyze_run(args.report, args.model, args.output_dir)
    except (OSError, AIError) as error:
        print(f'AI ANALYSIS ERROR: {error}', file=sys.stderr)
        return 2
    print(f'AI ANALYSIS: {result["status"]}')
    if result['status'] != 'SUCCESS':
        print(result['message'])
    print(f'Analysis report: {result["human_report"]}')
    return 0 if result['status'] == 'SUCCESS' else 2


if __name__ == '__main__':
    sys.exit(main())
