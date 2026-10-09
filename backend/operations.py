"""Owner follow-ups, minimal audit history and optional notification outbox."""
import hashlib
import json
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from .db import connect

router = APIRouter(prefix='/api/operations', tags=['CRM operations'])

def initialize_operations():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            due_at TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE INDEX IF NOT EXISTS idx_followups_due ON followups(completed, due_at);
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY, action TEXT NOT NULL, resource TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            fingerprint TEXT NOT NULL UNIQUE, state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')));
        ''')

        if 'actor' not in {r['name'] for r in db.execute('PRAGMA table_info(audit_events)')}:
            db.execute("ALTER TABLE audit_events ADD COLUMN actor TEXT NOT NULL DEFAULT 'legacy-owner'")

def audit(action, resource):
    with connect() as db:
        from .security import audit_actor
        db.execute('INSERT INTO audit_events(action,resource,actor) VALUES (?,?,?)', (action, resource, audit_actor.get()))

class Followup(BaseModel):
    lead_id: int = Field(gt=0)
    due_at: datetime
    notes: str = Field(default='', max_length=1000)

    @field_validator('due_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Callback time must include its timezone')
        return value.astimezone(timezone.utc)

@router.get('/followups')
def followups():
    with connect() as db:
        return [dict(row) for row in db.execute('''SELECT f.*, l.business_name,
          CASE WHEN l.contact_allowed=1 AND l.do_not_call=0 AND l.status!='not_interested' AND trim(l.consent_source)!='' THEN 1 ELSE 0 END AS contact_eligible
          FROM followups f JOIN leads l ON l.id=f.lead_id ORDER BY f.completed, f.due_at LIMIT 500''')]

@router.post('/followups', status_code=201)
def add_followup(body: Followup):
    with connect() as db:
        if not db.execute('SELECT 1 FROM leads WHERE id=?', (body.lead_id,)).fetchone():
            raise HTTPException(404, 'Lead not found')
        cur = db.execute('INSERT INTO followups(lead_id,due_at,notes) VALUES (?,?,?)', (body.lead_id, body.due_at.isoformat(), body.notes))
        result = dict(db.execute('SELECT * FROM followups WHERE id=?', (cur.lastrowid,)).fetchone())
    audit('followup-created', str(result['id']))
    return result

@router.post('/followups/{followup_id}/complete')
def complete_followup(followup_id: int):
    with connect() as db:
        if not db.execute('UPDATE followups SET completed=1 WHERE id=?', (followup_id,)).rowcount:
            raise HTTPException(404, 'Follow-up not found')
    audit('followup-completed', str(followup_id))
    return {'completed': True}

@router.get('/audit')
def events():
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM audit_events ORDER BY id DESC LIMIT 200')]

@router.get('/reports')
def reports():
    with connect() as db:
        counts = {r['status']: r['count'] for r in db.execute('SELECT status, count(*) AS count FROM leads GROUP BY status')}
        states = {r['state']: r['count'] for r in db.execute('SELECT state, count(*) AS count FROM sip_calls GROUP BY state')}
        due = db.execute('SELECT count(*) FROM followups WHERE completed=0 AND due_at<=?', (datetime.now(timezone.utc).isoformat(),)).fetchone()[0]
        return {'pipeline': counts, 'private_sip_calls': states, 'overdue_followups': due, 'pstn_connected': False}

@router.get('/notifications')
def notifications():
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT n.id,n.lead_id,n.state,n.attempts,n.error,n.created_at,l.business_name FROM notifications n JOIN leads l ON l.id=n.lead_id ORDER BY n.id DESC LIMIT 100')]
    return {'enabled': telegram_enabled(), 'items': rows}

def telegram_enabled():
    return os.environ.get('AKKI_TELEGRAM_ENABLED') == '1' and bool(os.environ.get('TELEGRAM_BOT_TOKEN') and os.environ.get('TELEGRAM_CHAT_ID'))

def queue_notification_in_transaction(db, lead_id):
    lead = db.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise HTTPException(404, 'Lead not found')
    if lead['do_not_call'] or lead['status'] not in ('interested', 'follow_up') or not lead['contact_allowed'] or not lead['consent_source'].strip():
        raise HTTPException(403, 'Only consented qualified leads can be queued')
    fingerprint = hashlib.sha256(json.dumps([lead_id, lead['requirements'], lead['budget'], lead['timeline'], lead['structured_requirements']], ensure_ascii=False).encode()).hexdigest()
    db.execute('INSERT OR IGNORE INTO notifications(lead_id,fingerprint) VALUES (?,?)', (lead_id, fingerprint))
    return dict(db.execute('SELECT id,state FROM notifications WHERE fingerprint=?', (fingerprint,)).fetchone())


@router.post('/notifications/leads/{lead_id}', status_code=201)
def queue_notification(lead_id: int):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        result = queue_notification_in_transaction(db, lead_id)
    audit('notification-queued', str(lead_id))
    return result


async def deliver_one():
    """Explicit worker command only; no sends during imports, startup or API reads."""
    if not telegram_enabled():
        return False
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM notifications WHERE state='pending' AND attempts<3 ORDER BY id LIMIT 1").fetchone()
        if not row:
            return False
        lead = db.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        if not lead['contact_allowed'] or lead['do_not_call'] or not lead['consent_source'].strip() or lead['status'] not in ('interested', 'follow_up'):
            db.execute("UPDATE notifications SET state='suppressed' WHERE id=?", (row['id'],))
            return True
        db.execute("UPDATE notifications SET state='sending', attempts=attempts+1 WHERE id=?", (row['id'],))
    # Minimal personal data: no phone, contact person, transcript or requirements are exported.
    text = f"Akki: qualified lead #{lead['id']} — {lead['business_name'][:160]}. Review details in your private dashboard."
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", json={'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': text})
            if response.status_code != 200 or response.json().get('ok') is not True:
                raise ValueError('Delivery rejected')
        state, error = 'sent', ''
    except Exception:
        # Telegram may have received the message before a timeout: avoid automatic duplicate sends.
        state, error = 'uncertain', 'Delivery unconfirmed; review provider before retrying manually.'
    with connect() as db:
        db.execute('UPDATE notifications SET state=?,error=? WHERE id=?', (state, error, row['id']))
    audit('notification-' + state, str(row['id']))
    return True
