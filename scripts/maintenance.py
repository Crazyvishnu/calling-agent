"""Private SQLite backups and explicit transcript retention; preserves lead/DNC records."""
import argparse
from contextlib import closing
import asyncio
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.db import DB_PATH, connect, initialize
from backend.operations import initialize_operations, audit, deliver_one


def backup(destination):
    path = Path(destination).resolve()
    if path == DB_PATH.resolve() or path.exists():
        raise ValueError('Choose a new private backup file, separate from the live database')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with connect() as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    audit('backup-created', 'private-file')


def purge(days):
    if days < 1:
        raise ValueError('Retention must be at least one day')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        modifier = f'-{days} days'
        db.execute("DELETE FROM ai_sessions WHERE state!='active' AND updated_at<datetime('now',?) AND id NOT IN (SELECT session_id FROM sip_calls WHERE state IN ('preparing','waiting','connected'))", (modifier,))
        db.execute("DELETE FROM conversations WHERE created_at<datetime('now',?)", (modifier,))
    audit('transcripts-purged', str(days) + '-days')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--backup', metavar='PRIVATE_PATH')
    options.add_argument('--purge-transcripts-older-than', type=int, metavar='DAYS')
    options.add_argument('--deliver-one-notification', action='store_true')
    args = parser.parse_args()
    initialize()
    initialize_operations()
    if args.backup:
        backup(args.backup)
    elif args.purge_transcripts_older_than is not None:
        purge(args.purge_transcripts_older_than)
    else:
        asyncio.run(deliver_one())
