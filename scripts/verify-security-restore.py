#!/usr/bin/env python3
"""Verify a decrypted recovery tar stream in a disposable server directory."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile
import tempfile
os.umask(0o077)
count=0;manifest=None
with tempfile.TemporaryDirectory(prefix='restic-restore-',dir=Path.home()/'.local/state') as tmp:
 with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
  for member in archive:
   if not member.isfile():continue
   with archive.extractfile(member) as source:
    magic=source.read(16)
    if member.name=='recovery/manifest.json':manifest=json.loads(magic+source.read())
    if magic==b'SQLite format 3\x00':
     dest=Path(tmp)/'database.db'
     with dest.open('wb') as out:out.write(magic);shutil.copyfileobj(source,out)
     with sqlite3.connect(dest) as db:assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
     dest.unlink();count+=1
assert manifest and count==manifest['sqlite_databases'] and count>0
print('PASS off-server encrypted archive restored and verified:',count,'SQLite databases')
