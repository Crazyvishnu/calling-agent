"""Media bounds, pacing, consent and cleanup without optional ML dependencies."""
import asyncio
import struct
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from fastapi.testclient import TestClient
from backend import db
from backend.media import AudioSocketBridge, PCM8To16, packet, read_packet
from backend.main import app
from backend.telephony import active

class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_protocol_and_bounds(self):
        reader = asyncio.StreamReader(); encoded = packet(0x10, bytes(320))
        task = asyncio.create_task(read_packet(reader))
        reader.feed_data(encoded[:2]); await asyncio.sleep(0)
        self.assertFalse(task.done()); reader.feed_data(encoded[2:])
        self.assertEqual(await task, (0x10, bytes(320)))
        for bad in (b'\x10\xff\xff', b'\x01\x00\x01x', b'\x99\x00\x00'):
            reader = asyncio.StreamReader(); reader.feed_data(bad)
            with self.assertRaises(ValueError): await read_packet(reader)

    async def test_identity_mismatch_never_forwards_audio(self):
        bridge = AudioSocketBridge(str(uuid4()), 'key', b'', AsyncMock())
        bridge.reader = asyncio.StreamReader(); bridge.reader.feed_data(packet(1, uuid4().bytes)); bridge.ws = AsyncMock()
        with self.assertRaises(ValueError): await bridge.audio_input()
        self.assertFalse(bridge.connected); bridge.ws.send.assert_not_called()

    async def test_playback_is_paced_and_cancellable(self):
        class Writer:
            def __init__(self): self.packets=[]; self.closed=False
            def write(self,data): self.packets.append(data)
            async def drain(self): pass
            def close(self): self.closed=True
            def is_closing(self): return self.closed
            async def wait_closed(self): pass
        bridge = AudioSocketBridge(str(uuid4()), 'key', b'', AsyncMock())
        bridge.writer=Writer(); bridge.ws=AsyncMock(); bridge.connected=True
        bridge.player=asyncio.create_task(bridge.play(bytes(320*100)))
        await asyncio.sleep(.025); await bridge.stop_playback()
        self.assertGreaterEqual(bridge.sent_frames,1); self.assertLess(bridge.sent_frames,5)
        before=bridge.sent_frames; await asyncio.sleep(.04); self.assertEqual(bridge.sent_frames,before)
        await bridge.close(); self.assertEqual(bridge.writer.packets[-1],packet(0)); self.assertTrue(bridge.writer.closed)
        bridge.ws.close.assert_awaited()

    def test_narrowband_reframing_preserves_boundaries(self):
        pcm=struct.pack('<320h',*range(320)); split,whole=PCM8To16(),PCM8To16()
        self.assertEqual(split.frames(pcm[:100])+split.frames(pcm[100:]),whole.frames(pcm))
        with self.assertRaises(ValueError): split.frames(b'odd')

class SIPGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.old_path=db.DB_PATH; db.DB_PATH=Path(self.temp.name)/'test.sqlite3'
        self.client=TestClient(app).__enter__()
        self.lead=self.client.post('/api/leads',json={'business_name':'Fictional SIP','contact_allowed':True,'consent_source':'Consenting test'}).json()
        self.session=self.client.post('/api/lab/sessions',json={'lead_id':self.lead['id'],'collection_consent':True}).json()
        self.url=f'/api/telephony/sessions/{self.session["id"]}/connect'
    def tearDown(self):
        active.clear(); self.client.__exit__(None,None,None); db.DB_PATH=self.old_path; self.temp.cleanup()
    def test_disabled_audio_permission_and_arbitrary_destination_gates(self):
        with patch.dict('os.environ',{'AKKI_SIP_LAB':'0'}):
            self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':True}).status_code,403)
        with patch.dict('os.environ',{'AKKI_SIP_LAB':'1'}):
            self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':False}).status_code,422)
            self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':'yes'}).status_code,422)
            self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':True,'number':'919999999999'}).status_code,422)
        self.assertFalse(self.client.get('/api/telephony/status').json()['pstn_connected'])
    def test_revoked_consent_and_one_call_limit(self):
        with patch.dict('os.environ',{'AKKI_SIP_LAB':'1'}):
            active['other']={}; self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':True}).status_code,409)
            active.clear(); self.client.patch(f'/api/leads/{self.lead["id"]}',json={'do_not_call':True})
            self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':True}).status_code,403)
    def test_sip_history_is_distinguished_from_pstn_and_restart_never_retries(self):
        from backend.telephony import recover_calls
        with db.connect() as conn:
            conn.execute('INSERT INTO sip_calls (id,session_id,state,connected_at) VALUES (?,?,?,?)',('recovery',self.session['id'],'connected',1.0))
        session=self.client.get('/api/lab/sessions/'+self.session['id']).json()
        self.assertTrue(session['real_call_placed']);self.assertTrue(session['private_sip_call_connected'])
        self.assertFalse(session['pstn_call_placed'])
        recover_calls();call=self.client.get('/api/telephony/calls/recovery').json()
        self.assertEqual(call['state'],'cancelled');self.assertEqual(call['stage'],'backend-restarted')
        self.assertIsNotNone(call['ended_at']);self.assertFalse(active)

    def test_failed_setup_releases_reservation_and_deletion_removes_call_history(self):
        with patch.dict('os.environ',{'AKKI_SIP_LAB':'1','AKKI_SIP_CREDENTIALS_PATH':'/missing/credentials'}):
            self.assertEqual(self.client.post(self.url,json={'audio_processing_consent':True}).status_code,503)
        self.assertFalse(active)
        with db.connect() as conn: row=dict(conn.execute('SELECT * FROM sip_calls').fetchone())
        self.assertEqual(row['state'],'failed'); self.assertIsNotNone(row['ended_at'])
        self.client.delete('/api/lab/sessions/'+self.session['id'])
        self.assertEqual(self.client.get('/api/telephony/calls/'+row['id']).status_code,404)

class EarlyCancelTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_before_worker_starts_closes_reserved_media(self):
        from backend.telephony import stop
        from types import SimpleNamespace
        temp=TemporaryDirectory(); old=db.DB_PATH; db.DB_PATH=Path(temp.name)/'early.sqlite3'
        try:
            db.initialize(); identity=str(uuid4())
            with db.connect() as conn:
                conn.execute("INSERT INTO leads (business_name) VALUES ('Fictional Early Cancel')")
                conn.execute('INSERT INTO ai_sessions (id,lead_id,language,collection_consent) VALUES (?,1,?,1)',(identity,'en-IN'))
                conn.execute('INSERT INTO sip_calls (id,session_id,state) VALUES (?,?,?)',('early',identity,'waiting'))
            bridge=SimpleNamespace(close=AsyncMock())
            active['early']={'bridge':bridge,'task':asyncio.create_task(asyncio.sleep(60))}
            result=await stop('early')
            self.assertEqual(result['state'],'cancelled'); self.assertNotIn('early',active)
            bridge.close.assert_awaited_once()
        finally:
            active.clear();db.DB_PATH=old;temp.cleanup()
