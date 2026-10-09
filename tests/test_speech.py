"""Offline voice transport and cancellation tests; live model checks are separate."""
import base64
import io
from pathlib import Path
import struct
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
import wave

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import db
from backend.ai import ModelTurn, ProviderUnavailable
from backend.lab import get_provider
from backend.main import app
from backend.vad import EnergyVAD

VOICE = struct.pack('<320h', *([5000, -5000] * 160))
SILENCE = bytes(640)


class FakeSpeech:
    text = 'I need a menu. My budget is INR 12000.'
    fail_tts = False

    def status(self, language='en-IN'):
        return {'ready': True}

    def transcribe(self, pcm, language):
        return self.text

    def synthesize(self, text, language):
        if self.fail_tts:
            raise ProviderUnavailable('tts unavailable')
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(bytes(3200))
        return output.getvalue()


class FakeProvider:
    def __init__(self):
        self.entered, self.release = Event(), Event()
        self.block = False

    def reply(self, messages, language, draft):
        self.entered.set()
        if self.block:
            self.release.wait(5)
        return ModelTurn(reply='What timeline do you prefer?', draft={'budget': 'INR 12000'})


class VADTests(unittest.TestCase):
    def test_onset_silence_endpoint_and_format(self):
        vad = EnergyVAD()
        self.assertFalse(vad.feed(SILENCE)[0])
        self.assertFalse(vad.feed(VOICE)[0])
        self.assertFalse(vad.feed(VOICE)[0])
        self.assertTrue(vad.feed(VOICE)[0])
        for _ in range(17):
            self.assertIsNone(vad.feed(VOICE)[1])
        for _ in range(29):
            self.assertIsNone(vad.feed(SILENCE)[1])
        self.assertIsNotNone(vad.feed(SILENCE)[1])
        with self.assertRaises(ValueError):
            vad.feed(b'wrong format')

    def test_maximum_utterance_is_bounded(self):
        vad = EnergyVAD(); utterance = None
        for _ in range(750):
            _, output = vad.feed(VOICE)
            utterance = output or utterance
        self.assertIsNotNone(utterance)
        self.assertLessEqual(len(utterance), 480000)


class VoiceSocketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_db = db.DB_PATH; db.DB_PATH = Path(self.temp.name) / 'test.sqlite3'
        self.speech = FakeSpeech(); self.provider = FakeProvider()
        self.mock = patch('backend.speech.engine', self.speech); self.mock.start()
        app.dependency_overrides[get_provider] = lambda: self.provider
        self.client = TestClient(app).__enter__()
        lead = self.client.post('/api/leads', json={'business_name': 'Fictional Voice Lab',
            'contact_allowed': True, 'consent_source': 'Consenting synthetic test participant'}).json()
        self.lead = lead['id']
        self.session = self.client.post('/api/lab/sessions', json={'lead_id': self.lead, 'collection_consent': True}).json()
        self.url = f'/api/speech/sessions/{self.session["id"]}/ws'

    def tearDown(self):
        self.provider.release.set()
        self.client.__exit__(None, None, None)
        from backend.speech import connections
        self.assertNotIn(self.session['id'], connections, 'Socket cancellation must release voice ownership')
        app.dependency_overrides.clear(); self.mock.stop()
        db.DB_PATH = self.previous_db; self.temp.cleanup()

    def socket(self):
        return self.client.websocket_connect(self.url, headers={'origin': 'http://localhost:5173'})

    def handshake(self, ws):
        ws.send_json({'type': 'start', 'audio_processing_consent': True})
        self.assertEqual(ws.receive_json()['type'], 'ready')

    def utterance(self, ws):
        for _ in range(20): ws.send_bytes(VOICE)
        for _ in range(30): ws.send_bytes(SILENCE)

    def receive(self, ws, kind):
        for _ in range(30):
            event = ws.receive_json()
            if event['type'] == kind: return event
            if event['type'] == 'error': self.fail(str(event))
        self.fail('Expected event not received: ' + kind)

    def saved(self):
        return self.client.get(f'/api/lab/sessions/{self.session["id"]}').json()

    def test_voice_turn_persists_text_draft_and_returns_wav(self):
        with self.socket() as ws:
            self.handshake(ws); self.utterance(ws)
            event = self.receive(ws, 'result')
            self.assertEqual(event['session']['revision'], 1)
            self.assertEqual(event['session']['draft']['budget'], 'INR 12000')
            self.assertTrue(base64.b64decode(event['audio']).startswith(b'RIFF'))
            self.assertIn('total_ms', event['timings'])
            ws.send_json({'type': 'stop'})
        self.assertEqual(len(self.saved()['messages']), 3)

    def test_barge_in_discards_pending_model_turn(self):
        self.provider.block = True
        with self.socket() as ws:
            self.handshake(ws); self.utterance(ws)
            self.receive(ws, 'transcript')
            self.assertTrue(self.provider.entered.wait(2))
            # Actual speech onset while inference is blocked invalidates that turn.
            for _ in range(3): ws.send_bytes(VOICE)
            self.receive(ws, 'interrupt')
            self.provider.release.set()
            ws.send_json({'type': 'stop'})
        self.assertEqual(self.saved()['revision'], 0)
        self.assertEqual(len(self.saved()['messages']), 1)

    def test_manual_interrupt_and_disconnect_discard_pending_turn(self):
        self.provider.block = True
        with self.socket() as ws:
            self.handshake(ws); self.utterance(ws)
            self.receive(ws, 'transcript')
            self.assertTrue(self.provider.entered.wait(2))
            ws.send_json({'type': 'interrupt'})
            # The initial onset interrupt has already been consumed by receive().
            self.receive(ws, 'interrupt')
            self.provider.release.set()
            ws.send_json({'type': 'stop'})
        self.assertEqual(self.saved()['revision'], 0)

    def test_collection_and_origin_gates(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(self.url, headers={'origin': 'https://untrusted.invalid'}): pass
        with self.socket() as ws:
            ws.send_json({'type': 'start', 'audio_processing_consent': False})
            self.assertEqual(ws.receive_json()['type'], 'error')
        self.assertEqual(self.saved()['revision'], 0)

    def test_opt_out_is_saved_even_when_synthesis_fails(self):
        self.speech.text = 'Do not call me again'; self.speech.fail_tts = True
        with self.socket() as ws:
            self.handshake(ws); self.utterance(ws)
            event = self.receive(ws, 'result')
            self.assertEqual(event['session']['state'], 'declined')
            self.assertEqual(event['audio'], '')
            ws.send_json({'type': 'stop'})
        lead = self.client.get(f'/api/leads/{self.lead}').json()
        self.assertTrue(lead['do_not_call']); self.assertFalse(lead['contact_allowed'])

    def test_microphone_blocks_erasure_and_logout_revokes_socket(self):
        import os
        with patch.dict(os.environ, {'AKKI_ADMIN_KEY':'k' * 40}):
            headers={'origin':'http://localhost:5173','X-Akki-Request':'1'}
            self.assertEqual(self.client.post('/api/auth/login',headers=headers,json={'key':'k' * 40}).status_code,200)
            with self.socket() as ws:
                self.handshake(ws)
                self.assertEqual(self.client.post(f'/api/privacy/leads/{self.lead}/erase', headers=headers,json={'reviewed':True}).status_code,409)
                self.assertEqual(self.client.post('/api/auth/logout',headers=headers).status_code,200)
                ws.send_json({'type':'ping'})
                error=ws.receive_json()
                self.assertEqual(error['type'],'error')
                self.assertIn('expired',error['detail'])
            response=self.client.get(f'/api/lab/sessions/{self.session["id"]}',headers={'Authorization':'Bearer '+'k' * 40})
            self.assertEqual(response.json()['revision'],0)
