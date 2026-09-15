#!/usr/bin/env python3
"""Consistent local whiteboard snapshots, including images in SQLite."""
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3

os.umask(0o077)
source = Path('/srv/mergerfs/ssd/excalidraw/excalidraw.db')
assert source.is_file(), 'Whiteboard database is missing'
directory = Path.home() / '.local/state/home-server-maintenance/excalidraw'
directory.mkdir(mode=0o700, parents=True, exist_ok=True)
target = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.db')
with sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True) as live:
    with sqlite3.connect(target) as backup:
        live.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('Whiteboard snapshot created and integrity verified:', target.name)
