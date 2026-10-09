"""Private exports and explicit erasure, preserving hashed suppression and quotas."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool
from .db import connect

router = APIRouter(prefix='/api/privacy', tags=['Privacy'])

class Erasure(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reviewed: StrictBool


def lead_row(db, lead_id):
    row = db.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Lead not found')
    return dict(row)

@router.get('/leads/{lead_id}/export')
def export(lead_id: int):
    with connect() as db:
        data = {'lead': lead_row(db, lead_id)}
        for table in ('conversations', 'ai_sessions', 'followups', 'notifications'):
            data[table] = [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE lead_id=?', (lead_id,))]
        for table in ('ai_messages', 'sip_calls', 'call_queue'):
            data[table] = [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE session_id IN (SELECT id FROM ai_sessions WHERE lead_id=?)', (lead_id,))]
    # No database salt, credentials or other customers' records are exported.
    return JSONResponse(data, headers={'Content-Disposition': f'attachment; filename="akki-lead-{lead_id}.json"', 'Cache-Control': 'no-store'})

@router.post('/leads/{lead_id}/erase')
def erase(lead_id: int, body: Erasure):
    if not body.reviewed:
        raise HTTPException(422, 'Review the export and explicitly confirm erasure')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        lead = lead_row(db, lead_id)
        from .speech import connections
        if any(row['id'] in connections for row in db.execute('SELECT id FROM ai_sessions WHERE lead_id=?', (lead_id,))):
            raise HTTPException(409, 'Disconnect the browser microphone before erasure')
        if db.execute("SELECT 1 FROM sip_calls c JOIN ai_sessions s ON s.id=c.session_id WHERE s.lead_id=? AND c.state IN ('preparing','waiting','connected')", (lead_id,)).fetchone() or db.execute("SELECT 1 FROM call_queue q JOIN ai_sessions s ON s.id=q.session_id WHERE s.lead_id=? AND q.state='dispatching'", (lead_id,)).fetchone():
            raise HTTPException(409, 'Stop active calls and wait for preparation to finish before erasure')
        if db.execute('SELECT akki_phone_key(?)', (lead['phone'],)).fetchone()[0]:
            db.execute('INSERT OR IGNORE INTO phone_suppressions(fingerprint) VALUES (akki_phone_fingerprint(?))', (lead['phone'],))
        # Queue references call IDs; remove jobs before cascading session deletion.
        db.execute('DELETE FROM call_queue WHERE session_id IN (SELECT id FROM ai_sessions WHERE lead_id=?)', (lead_id,))
        for table in ('ai_sessions', 'conversations', 'demo_states', 'followups', 'notifications'):
            db.execute(f'DELETE FROM {table} WHERE lead_id=?', (lead_id,))
        db.execute("""UPDATE leads SET business_name=?,category='Other',city='',phone='',website='',
          contact_name='',contact_allowed=0,consent_source='',do_not_call=1,status='not_interested',
          requirements='',budget='',timeline='',notes='',structured_requirements='{}',
          discovery_source='',discovery_source_id='',discovery_source_url='',discovery_observed_at='',
          updated_at=datetime('now') WHERE id=?""", (f'Erased lead {lead_id}', lead_id))
        db.execute("INSERT INTO audit_events(action,resource) VALUES ('lead-erased',?)", (str(lead_id),))
    return {'erased': True, 'lead_id': lead_id, 'suppression_preserved': True,
            'backup_erasure_required': True}

@router.get('/readiness')
def readiness():
    import os
    from .security import key
    with connect() as db:
        integrity = db.execute('PRAGMA quick_check').fetchone()[0]
    return {'database_ok': integrity == 'ok', 'owner_authentication': bool(key()),
            'secure_cookies': os.environ.get('AKKI_SECURE_COOKIES') == '1',
            'private_sip_enabled': os.environ.get('AKKI_SIP_LAB') == '1',
            'pstn_connected': False, 'automatic_retries': False,
            'production_ready': False,
            'remaining_checks': ['Human speech and latency acceptance', 'Hindi/Telugu voice models and testing',
                                 'Windows voice and WSL2 SIP testing', 'Always-on host, TLS and restore drills',
                                 'Licensed PSTN access and commercial calling authorization', 'Multi-user roles']}
