import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import ai_analysis as ai
from src.reconcile import main as reconcile_main, run_reconciliation

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'samples/reconciliation/join_fanout/job.json'


def completed_response(request, change=None):
    """Explicit offline stub; never used by the runtime provider."""
    query = next(item for item in request['packet']['evidence'] if item['kind'] == 'query_result')
    content = {
        'reported_status': request['packet']['deterministic_status'],
        'observations': [{'statement': 'The grouped query has the supplied status.', 'anchors': [
            {'evidence_id': query['id'], 'pointer': '/data/status', 'value_json': json.dumps(query['data']['status'])}]}],
        'hypotheses': [{'statement': 'An enrichment difference may explain the discrepancy.',
                        'evidence_ids': [query['id']], 'verification': 'Inspect the retained join rows and SQL.'}],
        'recommended_checks': [{'action': 'Compare the retained stage outputs.', 'evidence_ids': [query['id']],
                                'expected_result': 'Check whether row counts differ at enrichment.'}],
        'open_questions': [],
        'limitations': ['This is an explicitly mocked response for an offline boundary test.']}
    if change:
        change(content, request)
    return {'status': 'completed', 'output_text': json.dumps(content), 'model': 'offline-test-model',
            'response_id': 'offline-test-response', 'usage': None}


class AIAnalysisTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.report = run_reconciliation(FIXTURE, self.base / 'run')
        self.path = Path(self.report['report_path'])

    def analyze(self, provider=completed_response, name='ai'):
        return ai.analyze_run(self.path, output_dir=self.base / name, provider=provider)

    def test_success_preserves_computed_artifacts_and_saves_provenance(self):
        tracked = [Path(self.report[key]) for key in ('database', 'evidence_file', 'human_report', 'execution_report')]
        before = {path: path.read_bytes() for path in tracked}
        result = self.analyze()
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['provider'], 'injected_test_provider')
        self.assertEqual(result['validation']['anchors_checked'], 1)
        self.assertEqual(result['content']['reported_status'], 'AMBIGUOUS')
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved.pop('ai_analysis')['status'], 'SUCCESS')
        self.assertEqual(saved, self.report)
        request = json.loads((self.base / 'ai/request.json').read_text())
        self.assertEqual(request['evidence_sha256'], hashlib.sha256(before[Path(self.report['evidence_file'])]).hexdigest())
        self.assertNotIn('api_key', request)
        self.assertTrue((self.base / 'ai/response.json').exists())
        self.assertIn('Not Established Causes', Path(result['human_report']).read_text())
        self.assertIn('Human review is required', Path(result['human_report']).read_text())

    def test_rejects_unknown_citations_false_values_and_changed_status(self):
        changes = {
            'unknown_id': lambda c, r: c['observations'][0]['anchors'][0].update(evidence_id='E9999'),
            'wrong_value': lambda c, r: c['observations'][0]['anchors'][0].update(value_json='"MATCH"'),
            'missing_pointer': lambda c, r: c['observations'][0]['anchors'][0].update(pointer='/data/does_not_exist'),
            'status_changed': lambda c, r: c.update(reported_status='MATCH'),
            'extra_field': lambda c, r: c.update(automatic_fix='DELETE duplicated rows'),
            'uncited_hypothesis': lambda c, r: c['hypotheses'][0].update(evidence_ids=[]),
            'invented_check_citation': lambda c, r: c['recommended_checks'][0].update(evidence_ids=['E9999']),
            'no_observations': lambda c, r: c.update(observations=[]),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                result = self.analyze(lambda request: completed_response(request, change), name)
                self.assertEqual(result['status'], 'REJECTED')
                self.assertNotIn('content', result)
                self.assertTrue((self.base / name / 'response.json').exists())
                self.assertEqual(json.loads(self.path.read_text())['status'], 'AMBIGUOUS')

    def test_pointer_must_reference_a_field_actually_supplied_to_the_model(self):
        packet, originals, _ = ai.build_packet(self.path)
        sql = next(item for item in packet['evidence'] if item['kind'] == 'sql_step')
        self.assertIn('sql_path', originals[sql['id']]['data'])
        self.assertNotIn('sql_path', sql['data'])

        def change(content, request):
            content['observations'][0]['anchors'] = [{'evidence_id': sql['id'], 'pointer': '/data/sql_path',
                'value_json': json.dumps(originals[sql['id']]['data']['sql_path'])}]
        self.assertEqual(self.analyze(lambda request: completed_response(request, change))['status'], 'REJECTED')

    def test_bool_int_and_float_are_not_interchangeable_anchor_values(self):
        packet, _, _ = ai.build_packet(self.path)
        query = next(item for item in packet['evidence'] if item['kind'] == 'query_result')
        for name, pointer, value in [('bool', '/data/groups/0/a_present', '1'),
                                     ('float', '/data/groups/0/difference_cents', '10000.0')]:
            def change(content, request):
                content['observations'][0]['anchors'] = [{'evidence_id': query['id'],
                                                          'pointer': pointer, 'value_json': value}]
            with self.subTest(name=name):
                self.assertEqual(self.analyze(lambda request: completed_response(request, change), name)['status'], 'REJECTED')

    def test_tampered_ledger_is_rejected_before_provider_is_called(self):
        path = Path(self.report['evidence_file'])
        ledger = json.loads(path.read_text())
        ledger['items'][0]['data'] = 'An altered business requirement.'
        path.write_text(json.dumps(ledger))
        with patch.object(ai, 'openai_provider') as provider:
            result = self.analyze(provider)
        self.assertEqual(result['status'], 'REJECTED')
        self.assertIn('no longer matches', result['message'])
        provider.assert_not_called()

    def test_oversized_packet_is_rejected_without_silent_truncation(self):
        with patch.object(ai, 'MAX_PACKET_CHARS', 100), patch.object(ai, 'openai_provider') as provider:
            result = self.analyze(provider)
        self.assertEqual(result['status'], 'REJECTED')
        self.assertIn('no truncated analysis', result['message'])
        provider.assert_not_called()

    def test_missing_api_key_is_unavailable_without_network_or_fabricated_text(self):
        with patch.dict(os.environ, {}, clear=True):
            result = ai.analyze_run(self.path)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIn('OPENAI_API_KEY', result['message'])
        self.assertNotIn('content', result)
        self.assertIn('No substitute model explanation', Path(result['human_report']).read_text())
        self.assertEqual(json.loads(self.path.read_text())['status'], 'AMBIGUOUS')

    def test_refusal_and_incomplete_output_do_not_replace_deterministic_result(self):
        responses = [{'status': 'incomplete', 'output_text': '{"unfinished":'},
                     {'status': 'completed', 'output_text': ''}]
        for index, response in enumerate(responses):
            with self.subTest(index=index):
                result = self.analyze(lambda request: response, f'ai-{index}')
                self.assertEqual(result['status'], 'UNAVAILABLE')
                self.assertEqual(json.loads(self.path.read_text())['status'], 'AMBIGUOUS')

    def test_malformed_or_duplicate_key_json_is_rejected_and_retained(self):
        for index, value in enumerate(['not JSON', '{"reported_status":"MATCH","reported_status":"AMBIGUOUS"}']):
            with self.subTest(index=index):
                result = self.analyze(lambda request: {'status': 'completed', 'output_text': value}, f'ai-{index}')
                self.assertEqual(result['status'], 'REJECTED')
                self.assertEqual(json.loads((self.base / f'ai-{index}/response.json').read_text())['output_text'], value)

    def test_existing_analysis_is_not_overwritten_and_retry_uses_new_directory(self):
        self.analyze()
        saved = (self.base / 'ai/analysis.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.analyze()
        self.assertEqual((self.base / 'ai/analysis.json').read_bytes(), saved)
        self.assertEqual(self.analyze(name='retry')['status'], 'SUCCESS')

    def test_ai_failure_keeps_cli_exit_code_for_computed_reconciliation(self):
        fixture = ROOT / 'samples/reconciliation/filter_mismatch/job.json'
        with patch.object(ai, 'openai_provider', side_effect=ai.AIUnavailable('Offline test timeout.')), redirect_stdout(io.StringIO()) as output:
            code = reconcile_main([str(fixture), '--ai', '--output-dir', str(self.base / 'integrated')])
        self.assertEqual(code, 1)
        self.assertIn('RECONCILIATION: DIFFERENT', output.getvalue())
        self.assertIn('AI analysis: UNAVAILABLE', output.getvalue())
        saved = json.loads((self.base / 'integrated/reconciliation.json').read_text())
        self.assertEqual(saved['status'], 'DIFFERENT')
        self.assertEqual(saved['ai_analysis']['status'], 'UNAVAILABLE')

    def test_default_workflow_does_not_invoke_ai(self):
        with patch.object(ai, 'openai_provider') as provider:
            report = run_reconciliation(FIXTURE, self.base / 'no-ai')
        provider.assert_not_called()
        self.assertNotIn('ai_analysis', report)

    def test_correct_anchor_does_not_prove_natural_language_entailment(self):
        def change(content, request):
            content['observations'][0]['statement'] = 'Unsupported wording deliberately demonstrates the semantic review boundary.'
        result = self.analyze(lambda request: completed_response(request, change))
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertIn('Not automatically verified', result['validation']['semantic_entailment'])


class ProviderAndPointerTests(unittest.TestCase):
    def test_rfc6901_escaping_and_invalid_paths(self):
        data = {'a/b': {'~key': [False, 10000]}}
        self.assertEqual(ai.pointer_value(data, '/a~1b/~0key/1'), 10000)
        self.assertIs(ai.pointer_value(data, ''), data)
        for pointer in ('a', '/a~2b', '/a~1b/~0key/-1', '/a~1b/~0key/01', '/a~1b/~0key/9', '/a~1b/~0key/0/nested'):
            with self.subTest(pointer=pointer), self.assertRaises(ai.AIError):
                ai.pointer_value(data, pointer)

    def test_json_rejects_nonfinite_numbers_and_duplicate_fields(self):
        for value in ('NaN', 'Infinity', '1e999', '{"a":1,"a":2}'):
            with self.subTest(value=value), self.assertRaises(ai.AIError):
                ai.strict_json(value)

    def test_missing_optional_sdk_has_actionable_error(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-test-placeholder'}), patch.dict(sys.modules, {'openai': None}):
            with self.assertRaisesRegex(ai.AIUnavailable, 'requirements-ai.txt'):
                ai.openai_provider({})

    def test_provider_uses_strict_json_and_does_not_expose_exception_body(self):
        captured = {}

        class FakeClient:
            def __init__(self, **kwargs):
                captured['client'] = kwargs
                self.responses = self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def create(self, **kwargs):
                captured['request'] = copy.deepcopy(kwargs)
                raise RuntimeError('secret-placeholder-not-to-be-persisted')

        fake_sdk = types.SimpleNamespace(OpenAI=FakeClient)
        request = {'model': 'gpt-5-mini', 'instructions': 'Test prompt.', 'packet': {'synthetic': True},
                   'schema': ai.output_schema(['E001'])}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'offline-test-placeholder'}), patch.dict(sys.modules, {'openai': fake_sdk}):
            with self.assertRaises(ai.AIUnavailable) as raised:
                ai.openai_provider(request)
        self.assertNotIn('secret-placeholder', str(raised.exception))
        self.assertEqual(captured['client'], {'timeout': 45, 'max_retries': 0})
        self.assertFalse(captured['request']['store'])
        self.assertTrue(captured['request']['text']['format']['strict'])
        self.assertEqual(captured['request']['max_output_tokens'], 4500)


if __name__ == '__main__':
    unittest.main()
