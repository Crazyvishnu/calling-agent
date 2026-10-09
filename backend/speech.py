"""Local voice transport: bounded PCM, STT, cancellable LLM, Piper and barge-in."""
import asyncio
import base64
import contextlib
from threading import Event
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from .ai import OllamaProvider, ProviderUnavailable
from .db import connect
from .lab import LabReply, commit_turn, eligible, generate_turn, get_provider, load_turn, session_row
from .speech_engine import engine
from .vad import EnergyVAD

router = APIRouter(prefix='/api/speech', tags=['Local speech lab'])
from .security import origins
connections = set()  # Development server: use one Uvicorn worker.


def advance_generation(session_id):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        session_row(db, session_id)
        db.execute('UPDATE ai_sessions SET voice_generation=voice_generation+1 WHERE id=?', (session_id,))
        return session_row(db, session_id)['voice_generation']


def checked_session(session_id):
    with connect() as db:
        row = session_row(db, session_id)
        eligible(db, row['lead_id'])
        if row['state'] != 'active' or not row['collection_consent']:
            raise HTTPException(403, 'An active, collection-consented session is required.')
        return dict(row)


@router.get('/status')
def status(language: str = 'en-IN'):
    return engine.status(language)


class CancellableProvider:
    def __init__(self, provider, cancelled):
        self.provider, self.cancelled = provider, cancelled

    def reply(self, messages, language, draft):
        if isinstance(self.provider, OllamaProvider):
            return self.provider.reply(messages, language, draft, cancelled=self.cancelled.is_set)
        return self.provider.reply(messages, language, draft)


@router.websocket('/sessions/{session_id}/ws')
async def voice_socket(ws: WebSocket, session_id: str, provider=Depends(get_provider)):
    if ws.headers.get('origin') not in origins():
        await ws.close(code=4403)
        return
    if session_id in connections:
        await ws.close(code=4429)
        return
    connections.add(session_id)
    await ws.accept()
    active = None
    active_cancel = None
    pending = None
    closed = False
    terminal = False
    send_lock = asyncio.Lock()
    vad = EnergyVAD()

    async def send(data):
        async with send_lock:
            if not closed:
                await ws.send_json(data)

    async def interrupt():
        nonlocal pending
        pending = None
        if active_cancel:
            active_cancel.set()
        generation = await asyncio.to_thread(advance_generation, session_id)
        await send({'type': 'interrupt', 'generation': generation})
        return generation

    async def run_turn(pcm, generation, cancelled):
        nonlocal active, active_cancel, pending, terminal
        started = time.perf_counter()
        try:
            snapshot = await asyncio.to_thread(checked_session, session_id)
            await send({'type': 'state', 'state': 'recognizing'})
            text = await asyncio.to_thread(engine.transcribe, pcm, snapshot['language'])
            if cancelled.is_set():
                return
            if not text:
                await send({'type': 'state', 'state': 'listening', 'detail': 'No speech recognized.'})
                return
            stt_ms = round((time.perf_counter() - started) * 1000)
            body = LabReply(message=text, revision=snapshot['revision'])
            snapshot, messages, draft = await asyncio.to_thread(load_turn, session_id, body.revision, generation)
            await send({'type': 'transcript', 'text': text})
            await send({'type': 'state', 'state': 'thinking'})
            model_started = time.perf_counter()
            candidate = await asyncio.to_thread(generate_turn, snapshot, messages, draft, body,
                                                CancellableProvider(provider, cancelled))
            if cancelled.is_set():
                return
            await asyncio.to_thread(load_turn, session_id, body.revision, generation)
            llm_ms = round((time.perf_counter() - model_started) * 1000)
            # Suppression must survive TTS failures: commit opt-out before synthesis.
            result = None
            if candidate['changes']:
                result = await asyncio.to_thread(commit_turn, session_id, body, candidate, generation)
                terminal = result['state'] != 'active'
            await send({'type': 'state', 'state': 'synthesizing'})
            tts_started = time.perf_counter()
            try:
                wav = await asyncio.to_thread(engine.synthesize, candidate['answer'], snapshot['language'])
            except ProviderUnavailable:
                if result is None:
                    raise
                wav = b''
            if cancelled.is_set():
                return
            if result is None:
                result = await asyncio.to_thread(commit_turn, session_id, body, candidate, generation)
                terminal = result['state'] != 'active'
            timings = {'stt_ms': stt_ms, 'llm_ms': llm_ms,
                       'tts_ms': round((time.perf_counter() - tts_started) * 1000),
                       'total_ms': round((time.perf_counter() - started) * 1000)}
            await send({'type': 'result', 'session': result, 'generation': generation,
                        'timings': timings, 'audio': base64.b64encode(wav).decode(), 'mime': 'audio/wav'})
        except HTTPException as exc:
            if not cancelled.is_set():
                await send({'type': 'error', 'detail': exc.detail, 'code': exc.status_code})
        except (ProviderUnavailable, ValueError) as exc:
            if not cancelled.is_set():
                await send({'type': 'error', 'detail': str(exc)})
        finally:
            active = None
            active_cancel = None
            if pending and not closed:
                audio, next_generation = pending
                pending = None
                active_cancel = Event()
                active = asyncio.create_task(run_turn(audio, next_generation, active_cancel))

    try:
        snapshot = await asyncio.to_thread(checked_session, session_id)
        if not engine.status(snapshot['language'])['ready']:
            raise HTTPException(503, 'Local speech assets unavailable for this language; see speech setup.')
        hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
        if not isinstance(hello, dict) or hello.get('type') != 'start' or hello.get('audio_processing_consent') is not True:
            raise HTTPException(403, 'Explicit microphone processing permission required; no audio recordings are stored.')
        generation = await asyncio.to_thread(advance_generation, session_id)
        await send({'type': 'ready', 'generation': generation, 'state': 'listening'})
        last_check = time.monotonic()
        window_start, frame_count = time.monotonic(), 0
        while True:
            packet = await asyncio.wait_for(ws.receive(), timeout=30)
            if packet['type'] == 'websocket.disconnect':
                break
            if not terminal and time.monotonic() - last_check > 1:
                await asyncio.to_thread(checked_session, session_id)
                last_check = time.monotonic()
            if packet.get('bytes') is not None:
                if terminal:
                    continue
                # Reject bursts above three times real-time, not ordinary scheduling jitter.
                now = time.monotonic()
                if now - window_start >= 1:
                    window_start, frame_count = now, 0
                frame_count += 1
                if frame_count > 150:
                    raise HTTPException(429, 'Audio exceeded the local real-time frame limit.')
                began, utterance = vad.feed(packet['bytes'])
                if began:
                    generation = await interrupt()
                    await send({'type': 'state', 'state': 'hearing'})
                if utterance:
                    if active and not active.done():
                        pending = (utterance, generation)
                        await send({'type': 'state', 'state': 'waiting-for-cancelled-turn'})
                    else:
                        active_cancel = Event()
                        active = asyncio.create_task(run_turn(utterance, generation, active_cancel))
            elif packet.get('text') is not None:
                import json
                control = json.loads(packet['text'])
                if not isinstance(control, dict):
                    raise ValueError('Voice controls must be JSON objects.')
                if control.get('type') == 'interrupt':
                    generation = await interrupt()
                    vad.reset()
                    await send({'type': 'state', 'state': 'listening'})
                elif control.get('type') == 'stop':
                    break
                elif control.get('type') == 'ping':
                    await send({'type': 'pong'})
                else:
                    raise ValueError('Unknown voice control message.')
    except (HTTPException, ProviderUnavailable, ValueError, asyncio.TimeoutError) as exc:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await send({'type': 'error', 'detail': exc.detail if isinstance(exc, HTTPException) else str(exc) or 'Voice connection timed out.'})
    except WebSocketDisconnect:
        pass
    finally:
        closed = True
        if active_cancel:
            active_cancel.set()
        with contextlib.suppress(HTTPException):
            await asyncio.to_thread(advance_generation, session_id)
        if active:
            active.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active
        connections.discard(session_id)
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close()
