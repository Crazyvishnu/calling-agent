from tests.test_queue import QueueFixture
from unittest.mock import patch
import json
from backend import db
from backend.lab import get_provider
from backend.main import app

class HandoffTests(QueueFixture):
    # Shared fixture, without repeating queue tests.
    def test_customer_handoff_works_without_model(self):
        provider=type('Unavailable',(),{'reply':lambda *args: (_ for _ in ()).throw(AssertionError('Model must not run'))})()
        app.dependency_overrides[get_provider]=lambda:provider
        try:
            r=self.client.post(f'/api/lab/sessions/{self.session["id"]}/reply',json={'message':'I want to speak to a human','revision':0})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['state'],'completed')
            self.assertEqual(r.json()['handoff_requested'],1)
            self.assertEqual(self.client.get(f'/api/leads/{self.lead["id"]}').json()['status'],'follow_up')
        finally: app.dependency_overrides.clear()
    def test_review_requires_current_revision_and_keeps_structured_fields(self):
        draft={'requirements':'menu','pages_and_features':['menu'],'budget':'INR 12000','callback_time':'Friday at 4 pm','design_references':'simple design'}
        with db.connect() as connection:
            connection.execute('UPDATE ai_sessions SET draft_json=?,revision=1 WHERE id=?',(json.dumps(draft),self.session['id']))
        url=f'/api/lab/sessions/{self.session["id"]}/review'
        self.assertEqual(self.client.post(url,json={'reviewed':False,'revision':1}).status_code,422)
        self.assertEqual(self.client.post(url,json={'reviewed':True,'revision':0}).status_code,409)
        self.assertEqual(self.client.post(url,json={'reviewed':True,'revision':1}).status_code,200)
        self.assertEqual(self.client.post(url,json={'reviewed':True,'revision':1}).status_code,200)
        lead=self.client.get(f'/api/leads/{self.lead["id"]}').json()
        self.assertEqual(json.loads(lead['structured_requirements']),draft)
        self.assertEqual(lead['budget'],'INR 12000')
        self.assertEqual(lead['status'],'interested')
        self.assertEqual(len(self.client.get('/api/operations/notifications').json()['items']),1)
        self.client.patch(f'/api/leads/{self.lead["id"]}',json={'do_not_call':True})
        self.assertEqual(self.client.post(url,json={'reviewed':True,'revision':1}).status_code,403)
    def test_owner_handoff_closes_session_and_creates_followup_stage(self):
        r=self.client.post(f'/api/lab/sessions/{self.session["id"]}/handoff')
        self.assertEqual(r.json()['state'],'completed')
        self.assertEqual(self.client.get(f'/api/leads/{self.lead["id"]}').json()['status'],'follow_up')
