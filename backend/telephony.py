"""Opt-in localhost-only private SIP call binding; no PSTN or arbitrary dialing."""
import asyncio
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from .ai import OllamaProvider, ProviderUnavailable
from .db import connect
from .lab import get_session
from .media import AudioSocketBridge, wav_to_pcm8
from .speech import checked_session
from .speech_engine import engine

router = APIRouter(prefix='/api/telephony', tags=['Private SIP lab'])
active = {}  # Single-process/single-call development lab.
OPENING = "Hello, I'm Akki, an AI assistant for a website service. You agreed to this private test and local transcript storage. What website do you need?"


def enabled():
    return os.environ.get('AKKI_SIP_LAB') == '1'


def credentials_path():
    return Path(os.environ.get('AKKI_SIP_CREDENTIALS_PATH', str(Path(__file__).resolve().parents[1] / 'telephony/runtime/credentials.json')))


@router.get('/status')
def status():
    return {'enabled': enabled(), 'configured': credentials_path().is_file(), 'active_call_id': next(iter(active), None),
            'dial_extension': '1002', 'pstn_connected': False, 'max_calls': 1,
            'detail': 'Private local AudioSocket lab' if enabled() else 'Private SIP bridge disabled; explicitly set AKKI_SIP_LAB=1 to test.'}


def update(call_id, **fields):
    allowed = {'state', 'stage', 'turns_json', 'timings_json', 'transcript', 'error', 'received_frames', 'sent_frames', 'connected_at', 'ended_at'}
    if not fields.keys() <= allowed:
        raise ValueError('Unexpected call field')
    with connect() as db:
        db.execute('UPDATE sip_calls SET ' + ', '.join(k+'=?' for k in fields) + ' WHERE id=?', (*fields.values(), call_id))


@router.get('/calls/{call_id}')
def call_view(call_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM sip_calls WHERE id=?', (call_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Private call not found')
        result = dict(row)
    result['turn_timings'] = json.loads(result.pop('turns_json'))
    result['timings'] = json.loads(result.pop('timings_json'))
    result['session'] = get_session(result['session_id'])
    result['pstn_connected'] = False
    return result


class BindRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    audio_processing_consent: StrictBool


async def prepare(language):
    def warm():
        provider = OllamaProvider()
        if not provider.status()['ready']:
            raise ProviderUnavailable('Local Ollama model unavailable.')
        import httpx
        with httpx.Client(base_url=provider.base_url, timeout=90, trust_env=False) as client:
            response = client.post('/api/generate', json={'model': provider.model, 'keep_alive': '30m', 'stream': False, 'options': provider.inference_options(), 'think': False})
            response.raise_for_status()
        # Load optional assets before accepting a call. Silence is never persisted.
        engine.transcribe(bytes(16000), language)
        return wav_to_pcm8(engine.synthesize(OPENING, language))
    return await asyncio.to_thread(warm)


@router.post('/sessions/{session_id}/connect', status_code=201)
async def bind(session_id: str, body: BindRequest):
    if not enabled():
        raise HTTPException(403, 'Private SIP bridge disabled.')
    if not body.audio_processing_consent:
        raise HTTPException(422, 'Explicit local audio processing and transcript permission required.')
    snapshot = await asyncio.to_thread(checked_session, session_id)
    if snapshot['language'] != 'en-IN':
        raise HTTPException(422, 'Only English is enabled for the private SIP bridge.')
    if active:
        raise HTTPException(409, 'Only one private call may be reserved at a time.')
    call_id = str(uuid4())
    active[call_id] = {'bridge': None, 'task': None}
    with connect() as db:
        db.execute('INSERT INTO sip_calls (id, session_id, state, stage) VALUES (?, ?, ?, ?)',
                   (call_id, session_id, 'preparing', 'warming-models'))
    bridge = None
    turn_timings = []

    async def emit(event):
        kind = event.get('type')
        if kind == 'connected':
            update(call_id, state='connected', stage='opening', connected_at=time.time())
        elif kind in ('state', 'playback'):
            update(call_id, stage=event['state'])
        elif kind == 'transcript':
            update(call_id, transcript=event['text'])
        elif kind == 'interrupt':
            update(call_id, stage='interrupted')
        elif kind == 'result':
            turn_timings.append(event['timings'])
            update(call_id, timings_json=json.dumps(event['timings']), turns_json=json.dumps(turn_timings), stage='reply-ready')

    async def run():
        state, error = 'ended', ''
        try:
            await bridge.run()
            if not bridge.connected:
                state, error = 'failed', 'No private SIP call connected before the reservation closed.'
        except asyncio.CancelledError:
            state = 'cancelled'
            raise
        except Exception:
            state, error = 'failed', 'Private audio bridge failed; check local model/assets and PBX availability.'
        finally:
            try:
                await bridge.close()
                update(call_id, state=state, error=error, ended_at=time.time(), received_frames=bridge.received_frames, sent_frames=bridge.sent_frames)
            finally:
                active.pop(call_id, None)

    try:
        with credentials_path().open() as file:
            key = json.load(file)['bridge_key']
        opening = await prepare(snapshot['language'])
        await asyncio.to_thread(checked_session, session_id)  # Permission may change during warmup.
        bridge = AudioSocketBridge(session_id, key, opening, emit)
        await bridge.open()
        update(call_id, state='waiting', stage='dial-1002')
        active[call_id].update(bridge=bridge, task=asyncio.create_task(run()))
        return call_view(call_id)
    except BaseException as exc:
        if bridge:
            await bridge.close()
        active.pop(call_id, None)
        update(call_id, state='failed', error='Private lab setup failed; check model/assets and the relay.', ended_at=time.time())
        if isinstance(exc, (HTTPException, asyncio.CancelledError)):
            raise
        raise HTTPException(503, 'Private lab setup failed; check local model, speech assets, generated credentials and Asterisk relay.') from exc


@router.post('/calls/{call_id}/stop')
async def stop(call_id: str):
    call_view(call_id)
    entry = active.get(call_id)
    if entry:
        if not entry['task']:
            raise HTTPException(409, 'Models are preparing; wait for setup to finish.')
        entry['task'].cancel()
        try:
            await entry['task']
        except asyncio.CancelledError:
            pass
        # A task cancelled before its first step does not execute its finally block.
        if call_id in active:
            await entry['bridge'].close()
            update(call_id, state='cancelled', ended_at=time.time())
            active.pop(call_id, None)
    return call_view(call_id)


async def shutdown():
    for call_id in list(active):
        if active[call_id]['task']:
            await stop(call_id)


def recover_calls():
    # A restart never resumes or retries a private call. Relay EOF closes PBX media.
    with connect() as db:
        db.execute("UPDATE sip_calls SET state='cancelled', stage='backend-restarted', error='Local backend restarted; no call resumed.', ended_at=? WHERE state IN ('preparing','waiting','connected')", (time.time(),))
