import json
import os
from unittest.mock import patch
from starlette.websockets import WebSocketDisconnect
from tests.test_queue import QueueFixture
from backend.security import sessions, attempts, credentials

class RoleTests(QueueFixture):
    def setUp(self):
        super().setUp()
        self.keys = {'reviewer':{'role':'viewer','key':'v' * 40},'staff':{'role':'operator','key':'o' * 40}}
        self.auth = patch.dict(os.environ,{'AKKI_ADMIN_KEY':'k' * 40,'AKKI_TEAM_KEYS':json.dumps(self.keys)})
        self.auth.start(); sessions.clear(); attempts.clear()
        self.owner = {'Authorization':'Bearer '+'k' * 40}
        self.operator = {'Authorization':'Bearer '+'o' * 40}
        self.viewer = {'Authorization':'Bearer '+'v' * 40}
    def tearDown(self):
        self.auth.stop(); super().tearDown()

    def test_viewer_reads_but_cannot_write_export_or_use_microphone(self):
        self.assertEqual(self.client.get('/api/leads',headers=self.viewer).status_code,200)
        self.assertEqual(self.client.get(f'/api/privacy/leads/{self.lead["id"]}/export',headers=self.viewer).status_code,403)
        self.assertEqual(self.client.patch(f'/api/leads/{self.lead["id"]}',headers=self.viewer,json={'notes':'not allowed'}).status_code,403)
        with self.assertRaises(WebSocketDisconnect) as failure:
            with self.client.websocket_connect(f'/api/speech/sessions/{self.session["id"]}/ws',headers={**self.viewer,'origin':'http://localhost:5173'}): pass
        self.assertEqual(failure.exception.code,4403)

    def test_operator_notes_suppression_and_owner_consent_call_boundaries(self):
        endpoint=f'/api/leads/{self.lead["id"]}'
        self.assertEqual(self.client.patch(endpoint,headers=self.operator,json={'notes':'Reviewed by staff'}).status_code,200)
        self.assertEqual(self.client.patch(endpoint,headers=self.operator,json={'contact_allowed':True,'consent_source':'forged grant'}).status_code,403)
        self.assertEqual(self.client.post('/api/leads',headers=self.operator,json={'business_name':'Unauthorized consent','contact_allowed':True,'consent_source':'forged'}).status_code,403)
        self.assertEqual(self.client.post('/api/call-queue',headers=self.operator,json={}).status_code,403)
        self.assertEqual(self.client.post(f'/api/telephony/sessions/{self.session["id"]}/connect',headers=self.operator,json={'audio_processing_consent':True}).status_code,403)
        self.assertEqual(self.client.post(f'/api/privacy/leads/{self.lead["id"]}/erase',headers=self.operator,json={'reviewed':True}).status_code,403)
        self.assertEqual(self.client.patch(endpoint,headers=self.operator,json={'do_not_call':True}).status_code,200)
        events=self.client.get('/api/operations/audit',headers=self.owner).json()
        self.assertTrue(any(e['actor']=='staff' and e['action']=='http-patch-200' for e in events))
        self.assertNotIn('Reviewed by staff',json.dumps(events))

    def test_team_cookie_login_csrf_rotation_and_role_change(self):
        headers={'origin':'http://localhost:5173','X-Akki-Request':'1'}
        login=self.client.post('/api/auth/login',headers=headers,json={'key':'o' * 40})
        self.assertEqual(login.json()['role'],'operator')
        self.assertEqual(self.client.get('/api/auth/status').json()['account'],'staff')
        endpoint=f'/api/leads/{self.lead["id"]}'
        self.assertEqual(self.client.patch(endpoint,json={'notes':'Missing marker'}).status_code,401)
        self.keys['staff']['role']='viewer'
        with patch.dict(os.environ,{'AKKI_TEAM_KEYS':json.dumps(self.keys)}):
            self.assertEqual(self.client.get('/api/auth/status').json()['role'],'viewer')
            self.assertEqual(self.client.patch(endpoint,headers=headers,json={'notes':'Downgraded'}).status_code,403)
        self.keys['staff']['key']='r' * 40
        with patch.dict(os.environ,{'AKKI_TEAM_KEYS':json.dumps(self.keys)}):
            self.assertEqual(self.client.get('/api/leads').status_code,401)
        self.assertEqual(self.client.post('/api/auth/logout',headers=headers).status_code,200)

    def test_invalid_team_configuration_is_rejected(self):
        for data in ({'staff':{'role':'owner','key':'x' * 40}}, {'staff':{'role':'viewer','key':'short'}}, {'staff':{'role':'viewer','key':'k' * 40}}):
            with patch.dict(os.environ,{'AKKI_TEAM_KEYS':json.dumps(data)}):
                with self.assertRaises(ValueError): credentials()
