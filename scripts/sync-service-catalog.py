#!/usr/bin/env python3
"""Validate catalog endpoints and reconcile Homarr without moving existing tiles."""
from datetime import datetime, timezone
import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit
os.umask(0o077)
repo=Path(__file__).resolve().parents[1]
services=json.loads((repo/'config/services.json').read_text())['services']
assert len({s['id'] for s in services})==len(services)
def check(s):
 try:
  with urllib.request.urlopen(s['url'],timeout=15) as r:code=r.status
 except urllib.error.HTTPError as e:code=e.code
 except OSError:return s['id'],False
 return s['id'],code in s['expected_status']
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=dict(pool.map(check,services))
failed=[k for k,v in results.items() if not v]
assert not failed,'Unreachable catalog entries: '+', '.join(failed)
backup=Path.home()/'.local/state/home-server-maintenance/catalog';backup.mkdir(parents=True,exist_ok=True)
with sqlite3.connect('/mnt/server/homarr/appdata/db/db.sqlite') as db:
 db.execute('PRAGMA foreign_keys=ON')
 with sqlite3.connect(backup/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite')) as saved:db.backup(saved)
 db.execute('BEGIN IMMEDIATE')
 board=db.execute('SELECT id FROM board WHERE name=?',('home-server',)).fetchone()[0]
 section=db.execute('SELECT id FROM section WHERE board_id=? AND kind=?',(board,'empty')).fetchone()[0]
 layouts=db.execute('SELECT id,column_count FROM layout WHERE board_id=?',(board,)).fetchall()
 bases={layout:db.execute('SELECT COALESCE(MAX(y_offset+height),0) FROM item_layout WHERE section_id=? AND layout_id=?',(section,layout)).fetchone()[0] for layout,columns in layouts}
 added=updated=placed=0
 for s in services:
  found=db.execute('SELECT id FROM app WHERE rtrim(href,?)=?',('/',s['url'].rstrip('/'))).fetchone()
  if found:
   app_id=found[0];db.execute('UPDATE app SET name=?,description=?,href=?,ping_url=? WHERE id=?',(s['title'],s['category'],s['url'],s['probe_url'],app_id));updated+=1
  else:
   app_id=uuid.uuid4().hex[:24]
   db.execute('INSERT INTO app (id,name,description,icon_url,href,ping_url) VALUES (?,?,?,?,?,?)',(app_id,s['title'],s['category'],s['icon'],s['url'],s['probe_url']));added+=1
  items=db.execute('SELECT id,options FROM item WHERE board_id=? AND kind=?',(board,'app')).fetchall()
  if any(json.loads(options).get('json',{}).get('appId')==app_id for _,options in items):continue
  item=uuid.uuid4().hex[:24];db.execute('INSERT INTO item (id,board_id,kind,options) VALUES (?,?,?,?)',(item,board,'app',json.dumps({'json':{'appId':app_id}})))
  for layout,columns in layouts:
   y=bases[layout]+placed//columns
   db.execute('INSERT INTO item_layout VALUES (?,?,?,?,?,?,?)',(item,section,layout,placed%columns,y,1,1))
  placed+=1
 assert not db.execute('PRAGMA foreign_key_check').fetchall()
print('PASS catalog:',len(services),'reachable apps;',added,'added,',updated,'updated; existing layout preserved.')
