"""Build an English report and a referenceable evidence ledger from computed results."""
import json
from pathlib import Path

if __package__:
    from .sql_runner import write_report
else:
    from sql_runner import write_report


def money(value):
    return f'{"-" if value < 0 else ""}{abs(value) // 100}.{abs(value) % 100:02d}'


def compact(value):
    return json.dumps(value, ensure_ascii=False)


def build_evidence(report, execution):
    items = []

    def add(kind, summary, artifact, pointer, data):
        item = {'id': f'E{len(items) + 1:03d}', 'kind': kind, 'summary': summary,
                'source': {'artifact': artifact, 'json_pointer': pointer}, 'data': data}
        items.append(item)

    add('requirement', 'Supplied business requirement', 'execution.json', '/job/business_requirement',
        execution['job']['business_requirement'])
    for index, step in enumerate(execution['steps']):
        add('sql_step', f'{step["pipeline"]}/{step["id"]} execution', 'execution.json', f'/steps/{index}', step)
    if report['status'] == 'ERROR':
        add('error', 'Execution or reconciliation failed', 'reconciliation.json', '/error', report['error'])
        return items
    add('query_request', 'Common user query request', 'reconciliation.json', '/query', report['query'])
    add('query_result', 'Computed final grouped results', 'reconciliation.json', '/query_result', report['query_result'])
    for index, checkpoint in enumerate(report['checkpoints']):
        for scope in ('raw', 'query_scope'):
            prefix = f'/checkpoints/{index}/{scope}'
            detail = checkpoint[scope]
            add('checkpoint', f'{checkpoint["name"]}: {scope}', 'reconciliation.json', prefix, detail)
            for category in ('only_in_a', 'only_in_b', 'value_mismatches'):
                for row_index, row in enumerate(detail[category]):
                    add('record_difference', f'{checkpoint["name"]}: {scope} {category}',
                        'reconciliation.json', f'{prefix}/{category}/{row_index}', row)
            for side in ('A', 'B'):
                for category in ('duplicate_keys', 'invalid_keys'):
                    for row_index, row in enumerate(detail[category][side]):
                        add('grain_issue', f'{checkpoint["name"]}: {scope} {side} {category}',
                            'reconciliation.json', f'{prefix}/{category}/{side}/{row_index}', row)
    for index, diagnosis in enumerate(report['join_diagnostics']):
        add('join_diagnosis', f'{diagnosis["pipeline"]}/{diagnosis["step"]}: {diagnosis["status"]}',
            'reconciliation.json', f'/join_diagnostics/{index}', diagnosis)
    return items


def render_markdown(report, execution, evidence):
    def reference(kind, pointer=None):
        return ', '.join(f'[{item["id"]}]' for item in evidence
                         if item['kind'] == kind and (pointer is None or item['source']['json_pointer'] == pointer))

    lines = ['# Reconciliation Evidence Report', '', f'Overall status: **{report["status"]}**.', '',
             'This report is generated deterministically. Runtime AI has not been used.', '',
             f'Business requirement {reference("requirement")}:', '', execution['job']['business_requirement'], '',
             'Artifacts: [execution.json](execution.json), [reconciliation.json](reconciliation.json), '
             '[evidence.json](evidence.json), and the retained run.sqlite database.', '']
    if report['status'] == 'ERROR':
        lines += [f'## Failure {reference("error")}', '', '```json',
                  json.dumps(report['error'], indent=2), '```', '',
                  'Completed source/stage tables are retained where available. No equality conclusion is made.', '']
    else:
        lines += [f'## User Query {reference("query_request")}', '', '```json',
                  json.dumps(report['query'], indent=2), '```', '',
                  f'Query groups: **{report["query_result"]["status"]}**. '
                  f'Scoped detail records: **{report["detail_status"]}**. {reference("query_result")}', '',
                  '| Group | A rows | B rows | A amount | B amount | B minus A |',
                  '|---|---:|---:|---:|---:|---:|']
        for group in report['query_result']['groups']:
            lines.append(f'| {compact(group["group"])} | {group["A"]["rows"]} | {group["B"]["rows"]} '
                         f'| {money(group["A"]["amount_sum_cents"])} | {money(group["B"]["amount_sum_cents"])} '
                         f'| {money(group["difference_cents"])} |')
        lines += ['', 'Amounts are in the declared single currency, with 100 minor units per currency unit.', '',
                  '## Checkpoint Trace', '',
                  f'First raw divergence: **{report["first_raw_divergence"] or "none"}**. '
                  f'First query-scope divergence: **{report["first_query_scope_divergence"] or "none"}**.', '',
                  '| Checkpoint | Scope | Status | A rows | B rows | B minus A | Evidence |',
                  '|---|---|---|---:|---:|---:|---|']
        for index, checkpoint in enumerate(report['checkpoints']):
            for scope in ('raw', 'query_scope'):
                detail = checkpoint[scope]
                ref = reference('checkpoint', f'/checkpoints/{index}/{scope}')
                lines.append(f'| {checkpoint["name"]} | {scope} | {detail["status"]} | {detail["A"]["rows"]} '
                             f'| {detail["B"]["rows"]} | {money(detail["difference_cents"])} | {ref} |')
        lines += ['', '## Record and Grain Evidence', '']
        record_items = [item for item in evidence if item['kind'] in ('record_difference', 'grain_issue')
                        and '/query_scope/' in item['source']['json_pointer']]
        if not record_items:
            lines += ['No scoped record or grain differences were found.', '']
        for item in record_items:
            lines += [f'### {item["summary"]} [{item["id"]}]', '', '```json',
                      json.dumps(item['data'], indent=2, ensure_ascii=False), '```', '']
        lines += ['## Join Diagnostics', '',
                  'Diagnostics inspect raw stages. A warning may involve rows outside the current user query. '
                  'They test a declared equijoin model against retained observations; arbitrary SQL semantics are not inferred.', '']
        for index, diagnosis in enumerate(report['join_diagnostics']):
            ref = reference('join_diagnosis', f'/join_diagnostics/{index}')
            lines += [f'### {diagnosis["pipeline"]}/{diagnosis["step"]}: {diagnosis["status"]} {ref}', '', diagnosis['reason'], '']
            if 'left_rows' in diagnosis:
                lines += [f'Rows: **{diagnosis["left_rows"]} -> {diagnosis["output_rows"]}**. '
                          f'Amount: **{money(diagnosis["left_amount_cents"])} -> {money(diagnosis["output_amount_cents"])}**.', '']
            for candidate in diagnosis.get('fanout_keys', []):
                lines += [f'Business key: `{compact(candidate["key"])}`. '
                          f'Right matches: **{candidate["right_match_count"]}**. Output copies: **{candidate["output_count"]}**.', '',
                          'The following row IDs refer to this run.sqlite snapshot only.', '', '```json',
                          json.dumps({'left_record': candidate['left_record'], 'right_matches': candidate['right_matches'],
                                      'output_records': candidate['output_records']}, indent=2, ensure_ascii=False), '```', '']
            lines += ['Executed SQL:', '', '```sql', diagnosis['sql_text'], '```', '']
        lines += ['## Interpretation Boundaries', '',
                  'MATCH describes the configured comparison and request. AMBIGUOUS preserves duplicate/missing keys '
                  'without arbitrary one-to-one attribution. A first observed divergence is an investigation entry point. '
                  'Business correctness requires the supplied requirement and further verification.', '',
                  'No source rows or duplicate output rows were deleted by the diagnostic engine.', '']
    lines += ['## Evidence Index', '',
              'Evidence IDs are local to this run. Each entry maps to an exact JSON pointer in a saved artifact. '
              'The ledger also includes the evidence data; source SQL is copied into execution.json.', '',
              '| ID | Kind | Source artifact | JSON pointer |', '|---|---|---|---|']
    for item in evidence:
        source = item['source']
        lines.append(f'| {item["id"]} | {item["kind"]} | {source["artifact"]} | `{source["json_pointer"]}` |')
    return '\n'.join(lines) + '\n'


def write_evidence_artifacts(directory, report, execution):
    directory = Path(directory)
    evidence = build_evidence(report, execution)
    report['evidence_file'] = str(directory / 'evidence.json')
    report['human_report'] = str(directory / 'report.md')
    write_report(directory / 'evidence.json', {'schema_version': 1, 'items': evidence})
    (directory / 'report.md').write_text(render_markdown(report, execution, evidence), encoding='utf-8')
