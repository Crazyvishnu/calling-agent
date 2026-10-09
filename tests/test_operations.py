import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from backend import db
from backend.main import app
from backend.operations import deliver_one
from backend.security import sessions, attempts
from scripts.maintenance import backup, purge

class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / 'leads.sqlite3'
        self.env = patch.dict(os.environ, {'AKKI_ADMIN_KEY': 'k' * 40, 'AKKI_ALLOWED_ORIGINS': 'http://testserver'})
        self.env.start()
        sessions.clear(); attempts.clear()
        self.client = TestClient(app)
        self.client.__enter__()
        self.owner = {'Authorization': 'Bearer ' + 'k' * 40}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        db.DB_PATH = self.previous
        self.temp.cleanup()

    def create(self):
        response = self.client.post('/api/leads', headers=self.owner, json={'business_name': 'Fictional cafe', 'contact_allowed': True, 'consent_source': 'Requested test'})
        self.assertEqual(response.status_code, 201)
        return response.json()['id']

    def test_private_http_and_websocket_require_owner(self):
        self.assertEqual(self.client.get('/api/leads').status_code, 401)
        self.assertEqual(self.client.get('/docs').status_code, 401)
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect) as rejected:
            with self.client.websocket_connect('/api/speech/sessions/unknown/ws', headers={'origin': 'http://localhost:5173'}):
                pass
        self.assertEqual(rejected.exception.code, 4401)

    def test_cookie_login_csrf_logout_and_rate_limit(self):
        headers = {'origin': 'http://testserver', 'X-Akki-Request': '1'}
        self.assertEqual(self.client.post('/api/auth/login', headers={'origin': 'https://evil.example'}, json={'key': 'k' * 40}).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/login', headers=headers, json={'key': 'k' * 40}).status_code, 200)
        self.assertEqual(self.client.get('/api/leads').status_code, 200)
        self.assertEqual(self.client.post('/api/leads', json={'business_name': 'No CSRF header'}).status_code, 401)
        self.assertEqual(self.client.post('/api/leads', headers=headers, json={'business_name': 'Safe'}).status_code, 201)
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/leads').status_code, 401)
        for _ in range(4):
            self.assertEqual(self.client.post('/api/auth/login', headers=headers, json={'key': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', headers=headers, json={'key': 'wrong'}).status_code, 429)

    def test_callback_timezone_and_dnc_recheck(self):
        lead = self.create()
        data = {'lead_id': lead, 'due_at': '2026-10-08T15:00:00'}
        self.assertEqual(self.client.post('/api/operations/followups', headers=self.owner, json=data).status_code, 422)
        data['due_at'] += '+05:30'
        response = self.client.post('/api/operations/followups', headers=self.owner, json=data)
        self.assertEqual(response.status_code, 201)
        self.assertIn('09:30:00+00:00', response.json()['due_at'])
        self.client.patch(f'/api/leads/{lead}', headers=self.owner, json={'do_not_call': True})
        rows = self.client.get('/api/operations/followups', headers=self.owner).json()
        self.assertEqual(rows[0]['contact_eligible'], 0)
        self.assertEqual(self.client.post(f'/api/operations/followups/{rows[0]["id"]}/complete', headers=self.owner).status_code, 200)

    def test_notification_deduplication_and_revocation(self):
        lead = self.create()
        self.client.patch(f'/api/leads/{lead}', headers=self.owner, json={'status': 'interested', 'requirements': 'menu'})
        url = f'/api/operations/notifications/leads/{lead}'
        first = self.client.post(url, headers=self.owner).json()
        self.assertEqual(first['id'], self.client.post(url, headers=self.owner).json()['id'])
        self.client.patch(f'/api/leads/{lead}', headers=self.owner, json={'do_not_call': True})
        with patch.dict(os.environ, {'AKKI_TELEGRAM_ENABLED': '1', 'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': 'fake'}), patch('backend.operations.httpx.AsyncClient') as transport:
            asyncio.run(deliver_one())
            transport.assert_not_called()
        self.assertEqual(self.client.get('/api/operations/notifications', headers=self.owner).json()['items'][0]['state'], 'suppressed')

    def test_notification_disabled_and_ambiguous_timeout_no_retry(self):
        lead = self.create()
        self.client.patch(f'/api/leads/{lead}', headers=self.owner, json={'status': 'interested'})
        self.client.post(f'/api/operations/notifications/leads/{lead}', headers=self.owner)
        with patch.dict(os.environ, {'AKKI_TELEGRAM_ENABLED': '0'}), patch('backend.operations.httpx.AsyncClient') as transport:
            self.assertFalse(asyncio.run(deliver_one()))
            transport.assert_not_called()
        with patch.dict(os.environ, {'AKKI_TELEGRAM_ENABLED': '1', 'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': 'fake'}), patch('backend.operations.httpx.AsyncClient') as transport:
            transport.return_value.__aenter__.return_value.post = AsyncMock(side_effect=TimeoutError)
            self.assertTrue(asyncio.run(deliver_one()))
            self.assertFalse(asyncio.run(deliver_one()))
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(self.client.get('/api/operations/notifications', headers=self.owner).json()['items'][0]['state'], 'uncertain')

    def test_backup_and_retention_preserve_suppression(self):
        lead = self.create()
        self.client.patch(f'/api/leads/{lead}', headers=self.owner, json={'do_not_call': True})
        with db.connect() as connection:
            connection.execute("INSERT INTO conversations(lead_id,role,message,created_at) VALUES (?,'customer','private','2020-01-01')", (lead,))
        destination = Path(self.temp.name) / 'private-backup.sqlite3'
        backup(destination)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError): backup(destination)
        purge(30)
        with db.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM conversations').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT do_not_call FROM leads WHERE id=?', (lead,)).fetchone()[0], 1)

    def test_duplicate_phone_cannot_bypass_dnc(self):
        headers = self.owner
        first = self.client.post('/api/leads', headers=headers, json={'business_name':'Fictional DNC', 'phone':'+91 90000 00000'}).json()
        duplicate = self.client.post('/api/leads', headers=headers, json={'business_name':'Fictional Duplicate', 'phone':'09000000000', 'contact_allowed':True,'consent_source':'Test'}).json()
        self.client.patch(f'/api/leads/{first["id"]}', headers=headers, json={'do_not_call':True})
        blocked = self.client.get(f'/api/leads/{duplicate["id"]}', headers=headers).json()
        self.assertEqual(blocked['do_not_call'], 1)
        self.assertEqual(blocked['contact_allowed'], 0)
        self.assertEqual(self.client.post(f'/api/leads/{duplicate["id"]}/demo/start', headers=headers).status_code, 403)
        later = self.client.post('/api/leads', headers=headers, json={'business_name':'Fictional New Duplicate', 'phone':'9000000000', 'contact_allowed':True,'consent_source':'Test'}).json()
        self.assertEqual(later['do_not_call'], 1)
        self.assertEqual(later['contact_allowed'], 0)
        # Leads with no number remain independent.
        independent = self.client.post('/api/leads', headers=headers, json={'business_name':'No phone','contact_allowed':True,'consent_source':'Test'}).json()
        self.assertEqual(independent['do_not_call'], 0)
