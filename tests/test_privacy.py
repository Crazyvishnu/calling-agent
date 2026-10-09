import unittest
from uuid import uuid4
from backend import db
from tests.test_queue import QueueFixture

class PrivacyTests(QueueFixture):
    def test_export_isolated_and_erasure_preserves_suppression(self):
        with db.connect() as connection:
            connection.execute('UPDATE leads SET phone=?,notes=? WHERE id=?', ('+91 98765 43210','Private test note',self.lead['id']))
        other = self.client.post('/api/leads',json={'business_name':'Unrelated private record'}).json()
        result = self.client.get(f'/api/privacy/leads/{self.lead["id"]}/export')
        self.assertEqual(result.status_code,200)
        self.assertIn('attachment',result.headers['content-disposition'])
        self.assertNotIn('Unrelated private record',result.text)
        self.assertNotIn('phone_hmac_key',result.text)
        self.assertEqual(self.client.post(f'/api/privacy/leads/{self.lead["id"]}/erase',json={'reviewed':False}).status_code,422)
        self.enqueue()
        self.assertTrue(self.client.post(f'/api/privacy/leads/{self.lead["id"]}/erase',json={'reviewed':True}).json()['erased'])
        row = self.client.get(f'/api/leads/{self.lead["id"]}').json()
        self.assertEqual(row['phone'],''); self.assertEqual(row['notes'],'')
        self.assertEqual(self.client.get('/api/call-queue').json(),[])
        with db.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM ai_sessions').fetchone()[0],0)
        new = self.client.post('/api/leads',json={'business_name':'Suppressed reimport','phone':'09876543210','contact_allowed':True,'consent_source':'Test'}).json()
        self.assertTrue(new['do_not_call']); self.assertFalse(new['contact_allowed'])
        updated = self.client.patch(f'/api/leads/{new["id"]}',json={'do_not_call':False,'contact_allowed':True,'consent_source':'Test'}).status_code
        self.assertEqual(updated,422)
        self.assertEqual(self.client.get(f'/api/leads/{other["id"]}').json()['business_name'],'Unrelated private record')

    def test_active_call_blocks_erasure(self):
        with db.connect() as connection:
            connection.execute("INSERT INTO sip_calls(id,session_id,state) VALUES (?,?,'waiting')", (str(uuid4()),self.session['id']))
        self.assertEqual(self.client.post(f'/api/privacy/leads/{self.lead["id"]}/erase',json={'reviewed':True}).status_code,409)

    def test_transcript_deletion_does_not_reset_attempt_quota(self):
        from backend.call_queue import quota
        from fastapi import HTTPException
        with db.connect() as connection:
            connection.execute("INSERT INTO sip_calls(id,session_id,state) VALUES (?,?,'failed')", (str(uuid4()),self.session['id']))
            connection.execute('DELETE FROM ai_sessions WHERE id=?',(self.session['id'],))
            lead=connection.execute('SELECT * FROM leads WHERE id=?',(self.lead['id'],)).fetchone()
            with self.assertRaises(HTTPException) as caught:
                quota(connection,lead)
            self.assertEqual(caught.exception.status_code,429)
            self.assertEqual(connection.execute('SELECT count(*) FROM call_attempts').fetchone()[0],1)

    def test_readiness_does_not_claim_production(self):
        response=self.client.get('/api/privacy/readiness').json()
        self.assertTrue(response['database_ok']); self.assertFalse(response['production_ready'])
        self.assertFalse(response['pstn_connected'])
