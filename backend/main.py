"""Akki Voice Agent — consent-first local prototype API."""
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .security import AccessMiddleware, router as auth_router
from .operations import router as operations_router, initialize_operations, audit
from .call_queue import router as queue_router, initialize_queue
from .conversation import HELLO, respond
from .db import connect, initialize
from .lab import router as lab_router
from .discovery import router as discovery_router
from .speech import router as speech_router
from .telephony import router as telephony_router, shutdown as shutdown_telephony, recover_calls

Status = Literal['new', 'interested', 'follow_up', 'not_interested']


class LeadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    business_name: str = Field(min_length=1, max_length=160)
    category: str = Field(default='Other', max_length=70)
    city: str = Field(default='', max_length=100)
    phone: str = Field(default='', max_length=30)
    website: str = Field(default='', max_length=300)
    contact_name: str = Field(default='', max_length=120)
    contact_allowed: bool = False
    consent_source: str = Field(default='', max_length=300)
    notes: str = Field(default='', max_length=1000)


class LeadUpdate(BaseModel):
    status: Status | None = None
    requirements: str | None = Field(default=None, max_length=1500)
    budget: str | None = Field(default=None, max_length=100)
    timeline: str | None = Field(default=None, max_length=150)
    contact_allowed: bool | None = None
    consent_source: str | None = Field(default=None, max_length=300)
    do_not_call: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class Message(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    if os.environ.get('AKKI_REQUIRE_AUTH') == '1' and not os.environ.get('AKKI_ADMIN_KEY'):
        raise RuntimeError('Owner authentication is required for this deployment')
    if os.environ.get('AKKI_ADMIN_KEY') and len(os.environ['AKKI_ADMIN_KEY']) < 32:
        raise RuntimeError('AKKI_ADMIN_KEY must contain at least 32 characters')
    initialize()
    initialize_operations()
    recover_calls()
    initialize_queue()
    try:
        yield
    finally:
        await shutdown_telephony()


app = FastAPI(title='Akki Voice Agent', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])
app.add_middleware(AccessMiddleware)
app.include_router(auth_router)
app.include_router(queue_router)
app.include_router(operations_router)
app.include_router(discovery_router)
app.include_router(lab_router)
app.include_router(speech_router)
app.include_router(telephony_router)


def lead_from_db(db, lead_id: int):
    row = db.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Lead not found')
    return dict(row)


def get_lead(lead_id: int):
    with connect() as db:
        return lead_from_db(db, lead_id)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'telephone_connected': False, 'mode': 'local-demo'}


@app.get('/api/leads')
def list_leads(q: str = '', status: str = '', category: str = ''):
    sql = 'SELECT * FROM leads WHERE 1=1'
    params: list[str] = []
    if q:
        sql += ' AND (business_name LIKE ? OR city LIKE ? OR category LIKE ?)'
        params += ['%' + q + '%'] * 3
    if status:
        sql += ' AND status=?'
        params.append(status)
    if category:
        sql += ' AND category=?'
        params.append(category)
    sql += ' ORDER BY updated_at DESC, id DESC LIMIT 500'
    with connect() as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]


@app.post('/api/leads', status_code=201)
def create_lead(lead: LeadCreate):
    if lead.contact_allowed and not lead.consent_source.strip():
        raise HTTPException(status_code=422, detail='A consent source is required to mark contact as allowed')
    data = lead.model_dump()
    data['contact_allowed'] = int(data['contact_allowed'])
    cols = ', '.join(data)
    placeholders = ', '.join('?' for _ in data)
    with connect() as db:
        cur = db.execute(f'INSERT INTO leads ({cols}) VALUES ({placeholders})', tuple(data.values()))
        lead_id = cur.lastrowid
    audit('lead-saved', str(lead_id))
    return get_lead(lead_id)


@app.get('/api/leads/{lead_id}')
def lead_detail(lead_id: int):
    return get_lead(lead_id)


@app.patch('/api/leads/{lead_id}')
def update_lead(lead_id: int, update: LeadUpdate):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old = lead_from_db(db, lead_id)
        data = update.model_dump(exclude_unset=True, exclude_none=True)
        if old['do_not_call'] and data.get('do_not_call') is False:
            raise HTTPException(status_code=422, detail='Do-not-call suppression cannot be removed in this prototype')
        if data.get('status') == 'not_interested':
            data['contact_allowed'] = False
        if data.get('do_not_call'):
            data['contact_allowed'] = False
        if data.get('contact_allowed') is True and (old['do_not_call'] or data.get('do_not_call')):
            raise HTTPException(status_code=422, detail='Do-not-call leads cannot be contacted')
        if data.get('contact_allowed', old['contact_allowed']) and not data.get('consent_source', old['consent_source']).strip():
            raise HTTPException(status_code=422, detail='Consent source is required')
        if not data:
            return old
        for key in ('contact_allowed', 'do_not_call'):
            if key in data:
                data[key] = int(data[key])
        fields = ', '.join(f'{key}=?' for key in data)
        db.execute(f"UPDATE leads SET {fields}, updated_at=datetime('now') WHERE id=?", (*data.values(), lead_id))
    audit('lead-saved', str(lead_id))
    return get_lead(lead_id)


@app.get('/api/stats')
def stats():
    with connect() as db:
        total = db.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
        interested = db.execute("SELECT COUNT(*) FROM leads WHERE status='interested'").fetchone()[0]
        follow_up = db.execute("SELECT COUNT(*) FROM leads WHERE status='follow_up'").fetchone()[0]
        opted_in = db.execute('SELECT COUNT(*) FROM leads WHERE contact_allowed=1 AND do_not_call=0').fetchone()[0]
    return {'total': total, 'interested': interested, 'follow_up': follow_up, 'opted_in': opted_in}


@app.post('/api/leads/{lead_id}/demo/start')
def start_demo(lead_id: int):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        lead = lead_from_db(db, lead_id)
        # The demo never places a call, but we keep the contact-consent gate to avoid confusing it with a dialer.
        if lead['do_not_call'] or not lead['contact_allowed'] or not lead['consent_source'].strip() or lead['status'] == 'not_interested':
            raise HTTPException(status_code=403, detail='Consent required. This lead is not approved for outreach.')
        db.execute('DELETE FROM conversations WHERE lead_id=?', (lead_id,))
        db.execute('INSERT OR REPLACE INTO demo_states (lead_id, closed) VALUES (?, 0)', (lead_id,))
        db.execute('INSERT INTO conversations (lead_id, role, message) VALUES (?, ?, ?)', (lead_id, 'agent', HELLO))
    return {'reply': HELLO, 'mode': 'simulation-only', 'real_call_placed': False}


@app.get('/api/leads/{lead_id}/demo/messages')
def demo_messages(lead_id: int):
    get_lead(lead_id)
    with connect() as db:
        rows = db.execute('SELECT role, message, created_at FROM conversations WHERE lead_id=? ORDER BY id', (lead_id,)).fetchall()
    return [dict(row) for row in rows]


@app.post('/api/leads/{lead_id}/demo/reply')
def demo_reply(lead_id: int, body: Message):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        lead = lead_from_db(db, lead_id)
        if lead['do_not_call'] or not lead['contact_allowed'] or not lead['consent_source'].strip() or lead['status'] == 'not_interested':
            raise HTTPException(status_code=403, detail='Consent required')
        state = db.execute('SELECT closed FROM demo_states WHERE lead_id=?', (lead_id,)).fetchone()
        if state and state['closed']:
            raise HTTPException(status_code=409, detail='This demonstration has ended. Start a new demo to continue.')
        old = db.execute('SELECT role, message FROM conversations WHERE lead_id=? ORDER BY id', (lead_id,)).fetchall()
        if not old:
            raise HTTPException(status_code=409, detail='Start a demo conversation first')
        if old[-1]['role'] != 'agent':
            raise HTTPException(status_code=409, detail='Invalid conversation state')
        previous_customer = [r['message'] for r in old if r['role'] == 'customer']
        customer_messages = previous_customer + [body.message]
        reply, changes = respond(body.message, lead, customer_messages)
        ended = changes.get('status') == 'not_interested' or len(customer_messages) >= 4
        if ended:
            db.execute('INSERT OR REPLACE INTO demo_states (lead_id, closed) VALUES (?, 1)', (lead_id,))
        db.execute('INSERT INTO conversations (lead_id, role, message) VALUES (?, ?, ?)', (lead_id, 'customer', body.message))
        db.execute('INSERT INTO conversations (lead_id, role, message) VALUES (?, ?, ?)', (lead_id, 'agent', reply))
        if changes:
            fields = ', '.join(f'{key}=?' for key in changes)
            db.execute(f"UPDATE leads SET {fields}, updated_at=datetime('now') WHERE id=?", (*changes.values(), lead_id))
    return {'reply': reply, 'lead': get_lead(lead_id), 'mode': 'simulation-only', 'ended': ended}

# Serve the built dashboard on the same origin in the self-hosted package.
from pathlib import Path
from fastapi.staticfiles import StaticFiles
_frontend = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
if _frontend.is_dir():
    app.mount('/', StaticFiles(directory=str(_frontend), html=True), name='dashboard')
