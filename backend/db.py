"""SQLite persistence for local development."""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get('AGENT_DB_PATH', str(Path(__file__).parent / 'data' / 'leads.sqlite3')))


def phone_key(phone):
    value = re.sub(r'\D', '', phone or '')
    if len(value) == 12 and value.startswith('91'):
        value = value[2:]
    if len(value) == 11 and value.startswith('0'):
        value = value[1:]
    return value if len(value) >= 7 else ''


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(DB_PATH), timeout=20)
    try:
        if os.name == 'posix':
            DB_PATH.chmod(0o600)
        db.row_factory = sqlite3.Row
        db.create_function('akki_phone_key', 1, phone_key, deterministic=True)
        db.execute('PRAGMA foreign_keys = ON')
        yield db
        db.commit()
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Other',
            city TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            website TEXT NOT NULL DEFAULT '',
            contact_name TEXT NOT NULL DEFAULT '',
            contact_allowed INTEGER NOT NULL DEFAULT 0,
            consent_source TEXT NOT NULL DEFAULT '',
            do_not_call INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'new',
            requirements TEXT NOT NULL DEFAULT '',
            budget TEXT NOT NULL DEFAULT '',
            timeline TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('agent', 'customer')),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_lead ON conversations(lead_id, id);
        CREATE TABLE IF NOT EXISTS demo_states (
            lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
            closed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ai_sessions (
            id TEXT PRIMARY KEY,
            lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            language TEXT NOT NULL,
            collection_consent INTEGER NOT NULL CHECK(collection_consent=1),
            state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active', 'completed', 'declined')),
            revision INTEGER NOT NULL DEFAULT 0,
            voice_generation INTEGER NOT NULL DEFAULT 0,
            interest TEXT NOT NULL DEFAULT 'unknown',
            draft_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ai_sessions_lead ON ai_sessions(lead_id);
        CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('agent', 'customer')),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sip_calls (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
            state TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT '',
            transcript TEXT NOT NULL DEFAULT '',
            timings_json TEXT NOT NULL DEFAULT '{}',
            turns_json TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT '',
            received_frames INTEGER NOT NULL DEFAULT 0,
            sent_frames INTEGER NOT NULL DEFAULT 0,
            connected_at REAL,
            ended_at REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ai_messages_session ON ai_messages(session_id, id);
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(ai_sessions)')}
        if 'voice_generation' not in columns:
            db.execute('ALTER TABLE ai_sessions ADD COLUMN voice_generation INTEGER NOT NULL DEFAULT 0')

        sip_columns = {row['name'] for row in db.execute('PRAGMA table_info(sip_calls)')}
        if 'turns_json' not in sip_columns:
            db.execute("ALTER TABLE sip_calls ADD COLUMN turns_json TEXT NOT NULL DEFAULT '[]'")

        lead_columns = {row['name'] for row in db.execute('PRAGMA table_info(leads)')}
        for column in ('discovery_source','discovery_source_id','discovery_source_url','discovery_observed_at'):
            if column not in lead_columns:
                db.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_source ON leads(discovery_source,discovery_source_id) WHERE discovery_source<>'' AND discovery_source_id<>''")

        # Suppression follows a telephone number across duplicate business records.
        # Empty numbers are not grouped. This covers API, AI and import writes.
        db.executescript("""
        CREATE TRIGGER IF NOT EXISTS suppress_duplicate_insert AFTER INSERT ON leads
        WHEN akki_phone_key(NEW.phone)!='' AND EXISTS (
          SELECT 1 FROM leads WHERE do_not_call=1 AND akki_phone_key(phone)=akki_phone_key(NEW.phone))
        BEGIN
          UPDATE leads SET do_not_call=1,contact_allowed=0 WHERE akki_phone_key(phone)=akki_phone_key(NEW.phone);
        END;
        CREATE TRIGGER IF NOT EXISTS suppress_duplicate_update AFTER UPDATE OF do_not_call,phone,contact_allowed ON leads
        WHEN akki_phone_key(NEW.phone)!='' AND EXISTS (
          SELECT 1 FROM leads WHERE do_not_call=1 AND akki_phone_key(phone)=akki_phone_key(NEW.phone))
        BEGIN
          UPDATE leads SET do_not_call=1,contact_allowed=0 WHERE akki_phone_key(phone)=akki_phone_key(NEW.phone);
        END;
        """)
        db.execute("UPDATE leads SET do_not_call=1,contact_allowed=0 WHERE akki_phone_key(phone)!='' AND akki_phone_key(phone) IN (SELECT akki_phone_key(phone) FROM leads WHERE do_not_call=1)")

        for column, definition in (('handoff_requested','INTEGER NOT NULL DEFAULT 0'),('reviewed_revision','INTEGER')):
            if column not in {r['name'] for r in db.execute('PRAGMA table_info(ai_sessions)')}:
                db.execute(f'ALTER TABLE ai_sessions ADD COLUMN {column} {definition}')
        if 'structured_requirements' not in {r['name'] for r in db.execute('PRAGMA table_info(leads)')}:
            db.execute("ALTER TABLE leads ADD COLUMN structured_requirements TEXT NOT NULL DEFAULT '{}'")
