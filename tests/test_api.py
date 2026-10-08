"""Run: python -m unittest discover -s tests -v (after pip install requirements-dev.txt)."""
import os
import tempfile
import unittest
from pathlib import Path

_TEMP = tempfile.TemporaryDirectory()
os.environ['AGENT_DB_PATH'] = str(Path(_TEMP.name) / 'test.sqlite3')

from fastapi.testclient import TestClient
from backend.main import app


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        _TEMP.cleanup()

    def create(self, **overrides):
        data = {'business_name': 'Example Cafe', 'category': 'Restaurant', 'city': 'Hyderabad'}
        data.update(overrides)
        result = self.client.post('/api/leads', json=data)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def test_health_and_crud(self):
        self.assertFalse(self.client.get('/api/health').json()['telephone_connected'])
        lead = self.create()
        self.assertEqual(self.client.get(f'/api/leads/{lead["id"]}').json()['business_name'], 'Example Cafe')
        self.assertTrue(any(x['id'] == lead['id'] for x in self.client.get('/api/leads?q=Example').json()))
        self.assertEqual(self.client.patch(f'/api/leads/{lead["id"]}', json={'status': 'follow_up'}).json()['status'], 'follow_up')

    def test_consent_required_for_simulation(self):
        lead = self.create()
        r = self.client.post(f'/api/leads/{lead["id"]}/demo/start')
        self.assertEqual(r.status_code, 403)
        r = self.client.patch(f'/api/leads/{lead["id"]}', json={'contact_allowed': True})
        self.assertEqual(r.status_code, 422)

    def test_scripted_dialogue_and_extraction(self):
        lead = self.create(contact_allowed=True, consent_source='Requested demonstration during in-person meeting')
        url = f'/api/leads/{lead["id"]}/demo'
        self.assertFalse(self.client.post(url+'/start').json()['real_call_placed'])
        result = self.client.post(url+'/reply', json={'message': 'Yes, I need online booking and a menu for ₹12000 next month'}).json()
        self.assertEqual(result['lead']['status'], 'interested')
        self.assertEqual(result['lead']['budget'], '₹12000')
        self.assertIn('online booking', result['lead']['requirements'])
        self.assertEqual(result['lead']['timeline'], 'next month')
        self.assertEqual(len(self.client.get(url+'/messages').json()), 3)

    def test_do_not_call_stops_demo(self):
        lead = self.create(contact_allowed=True, consent_source='Consent at consultation')
        url = f'/api/leads/{lead["id"]}/demo'
        self.client.post(url+'/start')
        result = self.client.post(url+'/reply', json={'message': 'Do not call me again'}).json()
        self.assertEqual(result['lead']['do_not_call'], 1)
        self.assertEqual(result['lead']['contact_allowed'], 0)
        self.assertEqual(self.client.post(url+'/start').status_code, 403)

    def test_optin_cannot_override_dnc(self):
        lead = self.create()
        self.client.patch(f'/api/leads/{lead["id"]}', json={'do_not_call': True})
        r = self.client.patch(f'/api/leads/{lead["id"]}', json={'contact_allowed': True, 'consent_source': 'Some source'})
        self.assertEqual(r.status_code, 422)
        r = self.client.patch(f'/api/leads/{lead["id"]}', json={'do_not_call': False})
        self.assertEqual(r.status_code, 422)


if __name__ == '__main__':
    unittest.main()
