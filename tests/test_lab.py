"""Offline tests exercise gates, persistence, provider failures, and races."""
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend import db
from backend.ai import InvalidModelResponse, ModelTurn, OllamaProvider, ProviderUnavailable, guard_reply
from backend.ai import RequirementsDraft, grounded_draft
from backend.lab import get_provider
from backend.main import app


class FakeProvider:
    def __init__(self, result=None, error=None, callback=None):
        self.result = result or ModelTurn(reply='What pages do you need?')
        self.error = error
        self.callback = callback
        self.calls = []

    def reply(self, messages, language, draft):
        self.calls.append((messages, language, draft))
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return self.result


class LabTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / 'test.sqlite3'
        self.client = TestClient(app).__enter__()
        self.provider = FakeProvider()
        app.dependency_overrides[get_provider] = lambda: self.provider
        self.lead = self.client.post('/api/leads', json={
            'business_name': 'Fictional Lab Cafe', 'contact_allowed': True,
            'consent_source': 'Consenting fictional test participant',
        }).json()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.__exit__(None, None, None)
        db.DB_PATH = self.previous_db
        self.temp.cleanup()

    def start(self, **overrides):
        body = {'lead_id': self.lead['id'], 'collection_consent': True}
        body.update(overrides)
        return self.client.post('/api/lab/sessions', json=body)

    def send(self, session, text='I need a restaurant menu.', revision=None):
        return self.client.post(f'/api/lab/sessions/{session["id"]}/reply', json={
            'message': text, 'revision': session['revision'] if revision is None else revision,
        })

    def test_permission_and_contact_gates(self):
        self.assertEqual(self.start(collection_consent=False).status_code, 422)
        self.assertEqual(self.start(collection_consent='true').status_code, 422)
        self.assertEqual(self.start(collection_consent=1).status_code, 422)
        self.assertEqual(self.start(language='invalid').status_code, 422)
        self.client.patch(f'/api/leads/{self.lead["id"]}', json={'contact_allowed': False})
        self.assertEqual(self.start().status_code, 403)
        self.assertEqual(self.client.get(f'/api/lab/sessions?lead_id={self.lead["id"]}').json(), [])

    def test_draft_memory_is_persisted_without_crm_changes(self):
        self.provider.result = ModelTurn.model_validate({'reply': 'What is your timeline?',
            'draft': {'requirements': 'Menu and online booking', 'budget': '₹12000', 'pages_and_features': ['Menu']},
            'interest': 'interested'})
        s = self.start(language='te-IN').json()
        first = self.send(s).json()
        self.assertEqual(first['draft']['budget'], '₹12000')
        self.assertFalse(first['real_call_placed'])
        self.assertTrue(first['review_required'])
        self.provider.result = ModelTurn(reply='What is a good callback time?')
        second = self.send(first, 'Next month.').json()
        self.assertEqual(second['draft']['budget'], '₹12000')
        self.assertEqual(len(second['messages']), 5)
        self.assertEqual(self.provider.calls[1][1], 'te-IN')
        self.assertEqual(self.provider.calls[1][2]['budget'], '₹12000')
        self.assertEqual(self.client.get(f'/api/lab/sessions/{s["id"]}').json(), second)
        crm = self.client.get(f'/api/leads/{self.lead["id"]}').json()
        self.assertEqual(crm['status'], 'new')
        self.assertEqual(crm['budget'], '')

    def test_opt_out_bypasses_offline_provider_and_blocks_restart(self):
        self.provider.error = ProviderUnavailable('offline')
        s = self.start().json()
        r = self.send(s, 'Do not call me again')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['state'], 'declined')
        self.assertEqual(self.provider.calls, [])
        lead = self.client.get(f'/api/leads/{self.lead["id"]}').json()
        self.assertTrue(lead['do_not_call'])
        self.assertFalse(lead['contact_allowed'])
        self.assertEqual(self.start().status_code, 403)

    def test_plain_decline_disables_contact(self):
        s = self.start().json()
        result = self.send(s, 'No thanks').json()
        self.assertEqual(result['state'], 'declined')
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.start().status_code, 403)

    def test_manual_not_interested_status_disables_contact(self):
        result = self.client.patch(f'/api/leads/{self.lead["id"]}', json={'status': 'not_interested'})
        self.assertFalse(result.json()['contact_allowed'])
        self.assertEqual(self.start().status_code, 403)

    def test_provider_errors_do_not_save_failed_turn(self):
        s = self.start().json()
        for error, code in ((ProviderUnavailable('offline'), 503), (InvalidModelResponse('bad JSON'), 502)):
            with self.subTest(code=code):
                self.provider.error = error
                self.assertEqual(self.send(s).status_code, code)
                saved = self.client.get(f'/api/lab/sessions/{s["id"]}').json()
                self.assertEqual(saved['revision'], 0)
                self.assertEqual(len(saved['messages']), 1)

    def test_consent_revoked_during_inference_discards_result(self):
        s = self.start().json()
        self.provider.callback = lambda: self.client.patch(
            f'/api/leads/{self.lead["id"]}', json={'contact_allowed': False})
        self.assertEqual(self.send(s).status_code, 403)
        saved = self.client.get(f'/api/lab/sessions/{s["id"]}').json()
        self.assertEqual(saved['revision'], 0)
        self.assertEqual(len(saved['messages']), 1)

    def test_stale_revision_and_end_during_inference(self):
        s = self.start().json()
        self.assertEqual(self.send(s, revision=1).status_code, 409)
        self.assertEqual(self.provider.calls, [])
        self.provider.callback = lambda: self.client.post(f'/api/lab/sessions/{s["id"]}/end')
        self.assertEqual(self.send(s).status_code, 409)
        saved = self.client.get(f'/api/lab/sessions/{s["id"]}').json()
        self.assertEqual(saved['state'], 'completed')
        self.assertEqual(len(saved['messages']), 1)

    def test_finish_limit_and_delete_transcript(self):
        s = self.start().json()
        for _ in range(20):
            response = self.send(s)
            self.assertEqual(response.status_code, 200, response.text)
            s = response.json()
        self.assertEqual(s['state'], 'completed')
        self.assertEqual(self.send(s).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/lab/sessions/{s["id"]}').status_code, 204)
        self.assertEqual(self.client.get(f'/api/lab/sessions/{s["id"]}').status_code, 404)
        with db.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM ai_messages').fetchone()[0], 0)

    def test_blank_inputs_and_consent_evidence_cannot_be_cleared(self):
        self.assertEqual(self.client.post('/api/leads', json={'business_name': '  '}).status_code, 422)
        self.assertEqual(self.client.patch(f'/api/leads/{self.lead["id"]}', json={'consent_source': '  '}).status_code, 422)
        self.assertEqual(self.send(self.start().json(), '  ').status_code, 422)

    def test_scripted_false_interest_and_terminal_state(self):
        url = f'/api/leads/{self.lead["id"]}/demo'
        self.client.post(url+'/start')
        r = self.client.post(url+'/reply', json={'message': 'Yesterday was busy.'}).json()
        self.assertEqual(r['lead']['status'], 'new')
        for _ in range(3):
            r = self.client.post(url+'/reply', json={'message': 'Maybe later.'}).json()
        self.assertTrue(r['ended'])
        self.assertEqual(self.client.post(url+'/reply', json={'message': 'More.'}).status_code, 409)


class OllamaAdapterTests(unittest.TestCase):
    def test_streaming_voice_response_and_midstream_cancellation(self):
        import json
        for interrupt in (False, True):
            with self.subTest(interrupt=interrupt):
                cancelled = [False]
                released = []

                class Tokens(httpx.SyncByteStream):
                    def __iter__(self):
                        yield (json.dumps({'message': {'content': '{"reply":"Hello",'}, 'done': False}) + '\n').encode()
                        if interrupt:
                            cancelled[0] = True
                        yield (json.dumps({'message': {'content': '"draft":{}}'}, 'done': True}) + '\n').encode()

                    def close(self):
                        released.append(True)

                def handler(request):
                    if request.url.path == '/api/tags':
                        return httpx.Response(200, json={'models': [{'name': 'qwen3:1.7b'}]})
                    self.assertTrue(json.loads(request.content)['stream'])
                    return httpx.Response(200, stream=Tokens())

                original_client = httpx.Client
                with patch.dict('os.environ', {'OLLAMA_MODEL': 'qwen3:1.7b'}), patch('backend.ai.httpx.Client', side_effect=lambda **kwargs: original_client(
                        **kwargs, transport=httpx.MockTransport(handler))):
                    provider = OllamaProvider()
                    if interrupt:
                        with self.assertRaises(ProviderUnavailable):
                            provider.reply([{'role': 'customer', 'message': 'Hello'}], 'en-IN', {}, cancelled=lambda: cancelled[0])
                    else:
                        self.assertEqual(provider.reply([{'role': 'customer', 'message': 'Hello'}], 'en-IN', {}, cancelled=lambda: cancelled[0]).reply, 'Hello')
                self.assertTrue(released, 'The streamed HTTP response must close on success or interruption')

    def run_adapter(self, content=None, error=None, cloud=False, model='qwen2.5:1.5b'):
        requests = []

        def handler(request):
            requests.append(request)
            if error:
                raise error
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': model, **({'remote_host': 'ollama.com'} if cloud else {})}]})
            return httpx.Response(200, json={'message': {'content': content}})

        original_client = httpx.Client
        with patch.dict('os.environ', {'OLLAMA_MODEL': model}), patch('backend.ai.httpx.Client', side_effect=lambda **kwargs: original_client(
                **kwargs, transport=httpx.MockTransport(handler))):
            result = OllamaProvider().reply([{'role': 'customer', 'message': 'Hello, my budget is ₹10000.'}], 'en-IN', {})
        return result, requests

    def test_valid_schema_and_request(self):
        turn, requests = self.run_adapter('{"reply":"What pages do you need?","draft":{"budget":"₹10000"}}')
        self.assertEqual(turn.draft.budget, '₹10000')
        import json
        payload = json.loads(requests[-1].content)
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['messages'][-1]['role'], 'user')
        self.assertIn('properties', payload['format'])
        self.assertIn('draft', payload['format']['required'])
        self.assertIn('budget', payload['format']['$defs']['RequirementsDraft']['required'])

    def test_unstated_facts_are_discarded(self):
        turn, _ = self.run_adapter('{"reply":"Hi","draft":{"contact_person":"Akki","callback_time":"next week","budget":"₹10000"}}')
        self.assertIsNone(turn.draft.contact_person)
        self.assertIsNone(turn.draft.callback_time)
        self.assertEqual(turn.draft.budget, '₹10000')

    def test_spoken_thousands_format_supported_without_partial_amounts(self):
        messages = [{'role': 'customer', 'message': 'My budget is 12,000 rupees.'}]
        self.assertEqual(grounded_draft(RequirementsDraft(budget='12000'), messages).budget, '12000')
        self.assertIsNone(grounded_draft(RequirementsDraft(budget='2000'), messages).budget)

    def test_qwen3_thinking_disabled(self):
        import json
        _, requests = self.run_adapter('{"reply":"Hello"}', model='qwen3:1.7b')
        self.assertFalse(json.loads(requests[-1].content)['think'])

    def test_observed_model_assurances_are_replaced(self):
        for message in ("We'll ensure it's scheduled accordingly.", 'Your budget is within our range.', "I'm available tomorrow."):
            with self.subTest(message=message):
                guarded = guard_reply(message, 'en-IN')
                self.assertIn('developer must review', guarded)
                self.assertNotEqual(message, guarded)
        self.assertEqual(guard_reply('What design references do you have?', 'en-IN'), 'What design references do you have?')

    def test_invalid_and_privileged_model_output_rejected(self):
        for content in ('garbage', '{"reply":" "}', '{"reply":"Hi","draft":{"contact_allowed":true}}'):
            with self.subTest(content=content), self.assertRaises(InvalidModelResponse):
                self.run_adapter(content)

    def test_offline_and_remote_models_rejected(self):
        with self.assertRaises(ProviderUnavailable):
            self.run_adapter(error=httpx.ConnectError('offline'))
        with self.assertRaises(ProviderUnavailable):
            self.run_adapter(cloud=True)
