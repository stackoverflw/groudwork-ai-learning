"""Durable JSON records, atomic transactions, idempotency receipts and daily backups."""
from __future__ import annotations
import contextlib
import contextvars
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('GROUNDWORK_DATA', ROOT / 'data'))
CURRENT: contextvars.ContextVar[sqlite3.Connection | None] = contextvars.ContextVar('db', default=None)
KINDS = {'progress', 'attempt', 'session', 'mistake', 'experiment', 'baseline', 'setting', 'override', 'exam', 'draft', 'content', 'task', 'reminder', 'error'}

def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / 'groundwork.db', timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=FULL')
    return c

def init() -> None:
    with connect() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id)); CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status INTEGER NOT NULL, body TEXT NOT NULL);')

@contextlib.contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    existing = CURRENT.get()
    if existing is not None:
        yield existing
        return
    c = connect()
    token = CURRENT.set(c)
    try:
        c.execute('BEGIN IMMEDIATE')
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        CURRENT.reset(token)
        c.close()

def all_records(kind: str) -> list[dict[str, Any]]:
    c = CURRENT.get() or connect()
    try:
        return [json.loads(r['body']) for r in c.execute('SELECT body FROM records WHERE kind=? ORDER BY id', (kind,))]
    finally:
        if c is not CURRENT.get():
            c.close()

def get(kind: str, key: str, default: Any = None) -> Any:
    active = CURRENT.get()
    c = active or connect()
    try:
        row = c.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()
        return json.loads(row['body']) if row else default
    finally:
        if active is None:
            c.close()

def put(kind: str, key: str, value: dict[str, Any]) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError('Unknown record kind')
    value = dict(value, id=key)
    with transaction() as c:
        c.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body', (kind, key, json.dumps(value, ensure_ascii=False, allow_nan=False)))
    return value

def export_all() -> dict[str, Any]:
    active = CURRENT.get()
    if active is not None:
        return {'schema_version': 1, 'records': {k: all_records(k) for k in sorted(KINDS)}}
    with contextlib.closing(connect()) as c:
        c.execute('BEGIN')
        token = CURRENT.set(c)
        try:
            return export_all()
        finally:
            CURRENT.reset(token)

def restore(payload: dict[str, Any]) -> None:
    if set(payload) != {'schema_version', 'records'} or payload['schema_version'] != 1 or set(payload['records']) != KINDS:
        raise ValueError('Invalid backup schema')
    for kind, rows in payload['records'].items():
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows):
            raise ValueError(f'Invalid records: {kind}')
        if len({r['id'] for r in rows}) != len(rows):
            raise ValueError(f'Duplicate record ids: {kind}')
    with transaction() as c:
        c.execute('DELETE FROM records')
        for kind, rows in payload['records'].items():
            for row in rows:
                put(kind, row['id'], row)

def backup() -> Path:
    folder = DATA / 'backups'
    folder.mkdir(exist_ok=True)
    path = folder / (datetime.now().strftime('%Y-%m-%d') + '.db')
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=folder, suffix='.tmp', delete=False) as temp:
            staging = Path(temp.name)
        try:
            with contextlib.closing(connect()) as source, contextlib.closing(sqlite3.connect(staging)) as destination:
                source.backup(destination)
                if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise RuntimeError('SQLite backup verification failed')
            staging.replace(path)
        finally:
            staging.unlink(missing_ok=True)
    for old in sorted(folder.glob('*.db'))[:-14]:
        old.unlink(missing_ok=True)
    return path
