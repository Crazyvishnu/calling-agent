"""Durable local text conversation lab, ready for a future speech transport."""
import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from .ai import ConversationProvider, InvalidModelResponse, OllamaProvider, ProviderUnavailable
from .conversation import decline_changes
from .db import connect

router = APIRouter(prefix='/api/lab', tags=['Local AI lab'])
LANGUAGES = {
    'en-IN': "Hello! I'm Akki, an AI assistant for a website development service. This is a consenting local prototype test. You've agreed to save this conversation locally. What would you like to create or improve about your business website?",
    'hi-IN': 'नमस्ते! मैं अक्की, वेबसाइट डेवलपमेंट सेवा का AI सहायक हूँ। यह स्थानीय परीक्षण है, फोन कॉल नहीं। आपने बातचीत स्थानीय रूप से सहेजने की अनुमति दी है। आप अपनी वेबसाइट में क्या बनाना या सुधारना चाहते हैं?',
    'te-IN': 'నమస్కారం! నేను అక్కి, వెబ్‌సైట్ డెవలప్‌మెంట్ సేవకు AI సహాయకుడిని. ఇది స్థానిక పరీక్ష, ఫోన్ కాల్ కాదు. ఈ సంభాషణను స్థానికంగా సేవ్ చేయడానికి మీరు అనుమతించారు. మీ వ్యాపార వెబ్‌సైట్‌లో ఏమి నిర్మించాలి లేదా మెరుగుపరచాలి?',
}
MAX_TURNS = 20


class LabStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lead_id: int = Field(gt=0)
    language: Literal['en-IN', 'hi-IN', 'te-IN'] = 'en-IN'
    collection_consent: StrictBool

    @field_validator('collection_consent')
    @classmethod
    def require_collection_permission(cls, value):
        if not value:
            raise ValueError('Explicit collection and local transcript storage consent required')
        return value


class LabReply(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)
    revision: int = Field(ge=0)


def get_provider() -> ConversationProvider:
    return OllamaProvider()


def eligible(db, lead_id):
    lead = db.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not lead:
        raise HTTPException(404, 'Lead not found')
    if lead['do_not_call'] or not lead['contact_allowed'] or not lead['consent_source'].strip() or lead['status'] == 'not_interested':
        raise HTTPException(403, 'Documented contact consent required; declined and do-not-call leads are blocked.')
    return lead


def session_row(db, session_id):
    row = db.execute('SELECT * FROM ai_sessions WHERE id=?', (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Session not found')
    return row


def view(db, session_id):
    data = dict(session_row(db, session_id))
    data['draft'] = json.loads(data.pop('draft_json'))
    data['messages'] = [dict(r) for r in db.execute(
        'SELECT role, message, created_at FROM ai_messages WHERE session_id=? ORDER BY id', (session_id,))]
    sip = db.execute('SELECT 1 FROM sip_calls WHERE session_id=? AND connected_at IS NOT NULL LIMIT 1', (session_id,)).fetchone() is not None
    data.update(mode='local-ai-lab', real_call_placed=sip, private_sip_call_connected=sip, pstn_call_placed=False, review_required=True)
    return data


@router.get('/status')
def status():
    return OllamaProvider().status()


@router.post('/sessions', status_code=201)
def start(body: LabStart):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        eligible(db, body.lead_id)
        session_id = str(uuid4())
        db.execute('INSERT INTO ai_sessions (id, lead_id, language, collection_consent) VALUES (?, ?, ?, 1)',
                   (session_id, body.lead_id, body.language))
        db.execute('INSERT INTO ai_messages (session_id, role, message) VALUES (?, ?, ?)',
                   (session_id, 'agent', LANGUAGES[body.language]))
        return view(db, session_id)


@router.get('/sessions')
def list_sessions(lead_id: int):
    with connect() as db:
        return [dict(r) for r in db.execute(
            'SELECT id, state, created_at, language FROM ai_sessions WHERE lead_id=? ORDER BY rowid DESC LIMIT 50', (lead_id,))]


@router.get('/sessions/{session_id}')
def get_session(session_id: str):
    with connect() as db:
        return view(db, session_id)


def load_turn(session_id: str, revision: int, generation=None):
    with connect() as db:
        session = session_row(db, session_id)
        eligible(db, session['lead_id'])
        if session['state'] != 'active' or session['revision'] != revision:
            raise HTTPException(409, 'Session ended or changed. Reload it before continuing.')
        if generation is not None and session['voice_generation'] != generation:
            raise HTTPException(409, 'Voice turn interrupted; result discarded.')
        return dict(session), view(db, session_id)['messages'], json.loads(session['draft_json'])


def generate_turn(snapshot, messages, draft, body, provider):
    changes = decline_changes(body.message)
    interest = snapshot['interest']
    state = 'active'
    if changes:
        # Opt-out is processed without waiting for a model, even if Ollama is offline.
        answer = 'Understood. I have ended this conversation and disabled further outreach. Thank you.'
        state, interest = 'declined', 'not_interested'
    else:
        try:
            turn = provider.reply(messages + [{'role': 'customer', 'message': body.message}], snapshot['language'], draft)
        except ProviderUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except InvalidModelResponse as exc:
            raise HTTPException(502, str(exc)) from exc
        answer = turn.reply
        # Generated drafts can never grant permission or alter CRM qualification.
        draft.update(turn.draft.model_dump(exclude_none=True, exclude_defaults=True))
        interest = turn.interest if turn.interest != 'unknown' else interest
        if turn.opt_out or turn.interest == 'not_interested':
            changes = {'contact_allowed': False, 'status': 'not_interested'}
            if turn.opt_out:
                changes['do_not_call'] = True
            state, interest = 'declined', 'not_interested'
            answer = 'Understood. I have ended this conversation and disabled further outreach. Thank you.'
        elif turn.finished or body.revision + 1 >= MAX_TURNS:
            state = 'completed'
    return {'answer': answer, 'draft': draft, 'interest': interest, 'state': state, 'changes': changes}


def commit_turn(session_id, body, candidate, generation=None):
    answer, draft, interest, state, changes = (candidate[k] for k in ('answer', 'draft', 'interest', 'state', 'changes'))
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = session_row(db, session_id)
        if generation is not None and current['voice_generation'] != generation:
            raise HTTPException(409, 'Voice turn interrupted; result discarded.')
        # Model inference happens outside the DB lock. Recheck consent and revision at commit.
        eligible(db, current['lead_id'])
        if current['state'] != 'active' or current['revision'] != body.revision:
            raise HTTPException(409, 'Session ended or changed while the model was replying. Reload it.')
        db.executemany('INSERT INTO ai_messages (session_id, role, message) VALUES (?, ?, ?)',
                       [(session_id, 'customer', body.message), (session_id, 'agent', answer)])
        db.execute("UPDATE ai_sessions SET draft_json=?, interest=?, state=?, revision=revision+1, updated_at=datetime('now') WHERE id=?",
                   (json.dumps(draft, ensure_ascii=False), interest, state, session_id))
        if changes:
            fields = ', '.join(f'{key}=?' for key in changes)
            db.execute(f"UPDATE leads SET {fields}, updated_at=datetime('now') WHERE id=?", (*changes.values(), current['lead_id']))
            db.execute("UPDATE ai_sessions SET state='declined' WHERE lead_id=? AND state='active'", (current['lead_id'],))
        return view(db, session_id)


@router.post('/sessions/{session_id}/reply')
def reply(session_id: str, body: LabReply, provider: ConversationProvider = Depends(get_provider)):
    snapshot, messages, draft = load_turn(session_id, body.revision)
    candidate = generate_turn(snapshot, messages, draft, body, provider)
    return commit_turn(session_id, body, candidate)


@router.post('/sessions/{session_id}/end')
def end(session_id: str):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        session_row(db, session_id)
        db.execute("UPDATE ai_sessions SET state='completed', updated_at=datetime('now') WHERE id=? AND state='active'", (session_id,))
        return view(db, session_id)


@router.delete('/sessions/{session_id}', status_code=204)
def delete(session_id: str):
    with connect() as db:
        session_row(db, session_id)
        db.execute('DELETE FROM ai_sessions WHERE id=?', (session_id,))
