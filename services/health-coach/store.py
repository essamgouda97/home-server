import json
import os
import sqlite3
import time
from pathlib import Path

DATA = Path(os.environ.get('COACH_DATA', '/data'))


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'coach.sqlite', timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    return db


def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS edits(
          id TEXT PRIMARY KEY, address TEXT NOT NULL, identity TEXT NOT NULL,
          expected TEXT NOT NULL, value TEXT NOT NULL, status TEXT NOT NULL,
          created REAL NOT NULL, error TEXT NOT NULL DEFAULT '');
        CREATE UNIQUE INDEX IF NOT EXISTS pending_cell ON edits(address) WHERE status IN ('pending','conflict');
        CREATE TABLE IF NOT EXISTS entries(
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, day TEXT NOT NULL, value TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS device_events(
          id TEXT PRIMARY KEY, session TEXT NOT NULL, observed REAL NOT NULL,
          received REAL NOT NULL, value TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'suggested');
        CREATE TABLE IF NOT EXISTS heart_samples(
          observed INTEGER PRIMARY KEY, bpm INTEGER NOT NULL, session TEXT);
        ''')


def get(db, key, default=None):
    row = db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default


def put(db, key, value):
    db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (key,json.dumps(value,ensure_ascii=False)))


def backup():
    folder=DATA/'backups'; folder.mkdir(exist_ok=True)
    path=folder/(time.strftime('%Y%m%dT%H%M%S')+'-'+str(time.time_ns())+'.sqlite')
    with connect() as db, sqlite3.connect(path) as dest: db.backup(dest)
    path.chmod(0o600)
    return path
