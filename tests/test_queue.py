import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from backend import db
from backend.main import app
from backend.telephony import active
from backend.operations import initialize_operations
from backend.call_queue import initialize_queue

class QueueFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / 'test.sqlite3'
        self.env = patch.dict(os.environ, {'AKKI_SIP_LAB':'1','AKKI_PRIVATE_DAILY_LIMIT':'5'})
        self.env.start()
        self.client = TestClient(app); self.client.__enter__()
        self.lead = self.client.post('/api/leads', json={'business_name':'Fictional approved test', 'contact_allowed':True,'consent_source':'Consenting tester'}).json()
        self.session = self.client.post('/api/lab/sessions', json={'lead_id':self.lead['id'],'collection_consent':True}).json()
    def tearDown(self):
        self.client.__exit__(None,None,None); self.env.stop(); db.DB_PATH=self.previous; self.temp.cleanup()
    def enqueue(self, **changes):
        data={'session_id':self.session['id'],'due_at':datetime.now(timezone.utc).isoformat(),'approval_source':'Consenting participant 1001','private_test_approved':True,'audio_processing_consent':True}; data.update(changes)
        return self.client.post('/api/call-queue',json=data)
class QueueTests(QueueFixture):
    def test_approval_timezone_destination_and_duplicate_gates(self):
        self.assertEqual(self.enqueue(private_test_approved=False).status_code,422)
        self.assertEqual(self.enqueue(due_at='2026-10-09T00:00:00').status_code,422)
        self.assertEqual(self.enqueue(target_extension='919999999999').status_code,422)
        self.assertEqual(self.enqueue().status_code,201)
        self.assertEqual(self.enqueue().status_code,409)
    def test_revoked_consent_blocks_dispatch_without_pbx(self):
        job=self.enqueue().json()
        self.client.patch(f'/api/leads/{self.lead["id"]}',json={'do_not_call':True})
        with patch('backend.telephony.bind',new_callable=AsyncMock) as bind:
            r=self.client.post(f'/api/call-queue/{job["id"]}/dispatch')
            self.assertEqual(r.json()['state'],'blocked'); bind.assert_not_called()
        self.assertEqual(self.client.get('/api/call-queue').json()[0]['state'],'blocked')
    def test_future_time_cancellation_and_no_retry(self):
        job=self.enqueue(due_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()).json()
        self.assertEqual(self.client.post(f'/api/call-queue/{job["id"]}/dispatch').status_code,409)
        self.assertEqual(self.client.post(f'/api/call-queue/{job["id"]}/cancel').json()['state'],'cancelled')
        self.assertEqual(self.client.post(f'/api/call-queue/{job["id"]}/dispatch').status_code,409)
    def test_dispatch_outbound_flag_and_call_status_persistence(self):
        job=self.enqueue().json(); identity=str(uuid4())
        with db.connect() as connection:
            connection.execute("INSERT INTO sip_calls(id,session_id,state) VALUES (?,?,'waiting')",(identity,self.session['id']))
        with patch('backend.call_queue.quota'), patch('backend.telephony.bind',new_callable=AsyncMock) as bind:
            bind.return_value={'id':identity,'state':'waiting','error':''}
            r=self.client.post(f'/api/call-queue/{job["id"]}/dispatch')
            self.assertEqual(r.json()['call_id'],identity)
            self.assertTrue(bind.call_args.args[1].outbound_private)
        with db.connect() as connection:
            connection.execute("UPDATE sip_calls SET state='ended' WHERE id=?",(identity,))
        self.assertEqual(self.client.get('/api/call-queue').json()[0]['state'],'ended')
    def test_failed_attempt_consumes_lead_and_global_quota(self):
        with db.connect() as connection:
            connection.execute("INSERT INTO sip_calls(id,session_id,state) VALUES (?,?,'failed')",(str(uuid4()),self.session['id']))
        job=self.enqueue().json()
        with patch('backend.telephony.bind',new_callable=AsyncMock) as bind:
            self.assertEqual(self.client.post(f'/api/call-queue/{job["id"]}/dispatch').json()['state'],'blocked')
            bind.assert_not_called()
        # Direct reservations share the same restriction and must not leak an active lock.
        self.assertEqual(self.client.post(f'/api/telephony/sessions/{self.session["id"]}/connect',json={'audio_processing_consent':True}).status_code,429)
        self.assertFalse(active)
    def test_restart_does_not_repeat_dispatch(self):
        job=self.enqueue().json()
        with db.connect() as connection:
            connection.execute("UPDATE call_queue SET state='dispatching' WHERE id=?",(job['id'],))
        initialize_queue()
        self.assertEqual(self.client.get('/api/call-queue').json()[0]['state'],'failed')

    def test_global_quota_blocks_unrelated_lead(self):
        with db.connect() as connection:
            connection.execute("INSERT INTO sip_calls(id,session_id,state) VALUES (?,?,'failed')",(str(uuid4()),self.session['id']))
        other=self.client.post('/api/leads',json={'business_name':'Fictional other','contact_allowed':True,'consent_source':'Test'}).json()
        session=self.client.post('/api/lab/sessions',json={'lead_id':other['id'],'collection_consent':True}).json()
        with patch.dict(os.environ,{'AKKI_PRIVATE_DAILY_LIMIT':'1'}),patch('backend.telephony.prepare',new_callable=AsyncMock) as warm:
            self.assertEqual(self.client.post(f'/api/telephony/sessions/{session["id"]}/connect',json={'audio_processing_consent':True}).status_code,429)
            warm.assert_not_called()
            self.assertFalse(active)
