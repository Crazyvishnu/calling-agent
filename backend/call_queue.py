"""Manually approved private SIP jobs. No telephone-number dialing or automatic retries."""
import asyncio
from datetime import datetime, timezone
import os
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from .db import connect
from .lab import eligible, session_row

router = APIRouter(prefix='/api/call-queue', tags=['Approved private SIP queue'])


def initialize_queue():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS call_queue (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
          state TEXT NOT NULL DEFAULT 'queued', due_at TEXT NOT NULL, approval_source TEXT NOT NULL,
          call_id TEXT REFERENCES sip_calls(id), error TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_session ON call_queue(session_id) WHERE state IN ('queued','dispatching','waiting','connected');
        CREATE TRIGGER IF NOT EXISTS queue_call_state AFTER UPDATE OF state ON sip_calls
        BEGIN UPDATE call_queue SET state=NEW.state,error=NEW.error WHERE call_id=NEW.id; END;
        ''')
        db.execute("UPDATE call_queue SET state='failed',error='Backend restarted; review before scheduling a new job.' WHERE state='dispatching'")
        db.execute("UPDATE call_queue SET state=(SELECT state FROM sip_calls WHERE id=call_queue.call_id),error=(SELECT error FROM sip_calls WHERE id=call_queue.call_id) WHERE call_id IS NOT NULL")


def quota(db, lead):
    """Failed reservations also consume a slot, preventing repeat attempts."""
    maximum = max(1, min(10, int(os.environ.get('AKKI_PRIVATE_DAILY_LIMIT', '5'))))
    count = db.execute("SELECT count(*) FROM call_attempts WHERE created_at>=datetime('now','-1 day')").fetchone()[0]
    if count >= maximum:
        raise HTTPException(429, 'Private lab rolling 24-hour call quota reached')
    number = db.execute('SELECT akki_phone_fingerprint(?)', (lead['phone'],)).fetchone()[0]
    count = db.execute("""SELECT count(*) FROM call_attempts
      WHERE created_at>=datetime('now','-1 day')
      AND (lead_id=? OR (?!='' AND contact_hash=?))""", (lead['id'], number, number)).fetchone()[0]
    if count:
        raise HTTPException(429, 'This lead or phone already has a private call attempt in the last 24 hours')


class QueueRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    session_id: str = Field(min_length=1, max_length=64)
    due_at: datetime
    approval_source: str = Field(min_length=1, max_length=300)
    private_test_approved: StrictBool
    audio_processing_consent: StrictBool

    @field_validator('due_at')
    @classmethod
    def utc_time(cls, value):
        if value.tzinfo is None:
            raise ValueError('Include a timezone')
        return value.astimezone(timezone.utc)


def job_view(db, job_id):
    row = db.execute('SELECT q.*,s.lead_id,l.business_name FROM call_queue q JOIN ai_sessions s ON s.id=q.session_id JOIN leads l ON l.id=s.lead_id WHERE q.id=?', (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Queue job not found')
    result = dict(row)
    result.update(target_extension='1001', pstn_connected=False, automatic_retries=False)
    return result


@router.get('')
def jobs():
    with connect() as db:
        ids = [r['id'] for r in db.execute('SELECT id FROM call_queue ORDER BY due_at DESC LIMIT 100')]
        return [job_view(db, identity) for identity in ids]


@router.post('', status_code=201)
def enqueue(body: QueueRequest):
    if not body.private_test_approved or not body.audio_processing_consent:
        raise HTTPException(422, 'Private test approval and audio/transcript permission are required')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        session = session_row(db, body.session_id)
        eligible(db, session['lead_id'])
        if session['state'] != 'active' or session['language'] != 'en-IN':
            raise HTTPException(409, 'An active English session is required')
        if db.execute("SELECT count(*) FROM call_queue WHERE state IN ('queued','dispatching','waiting','connected')").fetchone()[0] >= 20:
            raise HTTPException(429, 'Private queue is full')
        if db.execute("SELECT 1 FROM call_queue WHERE session_id=? AND state IN ('queued','dispatching','waiting','connected')", (body.session_id,)).fetchone():
            raise HTTPException(409, 'This session already has a pending job')
        identity = str(uuid4())
        db.execute('INSERT INTO call_queue(id,session_id,due_at,approval_source) VALUES (?,?,?,?)', (identity, body.session_id, body.due_at.isoformat(), body.approval_source))
        return job_view(db, identity)


@router.post('/{job_id}/dispatch')
async def dispatch(job_id: str):
    from .telephony import bind, BindRequest, enabled
    if not enabled():
        raise HTTPException(403, 'Private SIP lab disabled')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        job = job_view(db, job_id)
        if job['state'] != 'queued':
            raise HTTPException(409, 'Only queued jobs can be dispatched; no automatic retries')
        if datetime.fromisoformat(job['due_at']) > datetime.now(timezone.utc):
            raise HTTPException(409, 'This approved callback time has not arrived')
        try:
            session = session_row(db, job['session_id'])
            lead = eligible(db, session['lead_id'])
            if session['state'] != 'active':
                raise HTTPException(403, 'Session ended')
            quota(db, lead)
        except HTTPException as exc:
            db.execute("UPDATE call_queue SET state='blocked',error=? WHERE id=?", (exc.detail, job_id))
            # Return the persisted blocked job instead of rolling back the transaction.
            return job_view(db, job_id)
        db.execute("UPDATE call_queue SET state='dispatching' WHERE id=?", (job_id,))
    try:
        call = await bind(job['session_id'], BindRequest(audio_processing_consent=True, outbound_private=True))
        with connect() as db:
            db.execute('UPDATE call_queue SET call_id=?,state=?,error=? WHERE id=?', (call['id'], call['state'], call['error'], job_id))
            return job_view(db, job_id)
    except BaseException as exc:
        with connect() as db:
            db.execute("UPDATE call_queue SET state=?,error=? WHERE id=?", ('cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed', 'Private dispatch failed; review before a new approved attempt.', job_id))
        raise


@router.post('/{job_id}/cancel')
async def cancel(job_id: str):
    from .telephony import stop
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        job = job_view(db, job_id)
        if job['state'] == 'dispatching':
            raise HTTPException(409, 'Preparation is in progress; wait for reservation before cancelling')
        if job['state'] == 'queued':
            db.execute("UPDATE call_queue SET state='cancelled' WHERE id=?", (job_id,))
        elif job['state'] not in ('waiting', 'connected'):
            return job
    if job['call_id'] and job['state'] in ('waiting', 'connected'):
        await stop(job['call_id'])
    with connect() as db:
        return job_view(db, job_id)
