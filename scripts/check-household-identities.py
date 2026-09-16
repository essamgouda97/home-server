#!/usr/bin/env python3
"""Read-only invariants for existing household media identity and least privilege."""
import importlib.util,json,sqlite3,yaml
from pathlib import Path
from identity_policy import identities,groups,allowed
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_auth',ROOT/'scripts/prepare-auth.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
private=Path.home()/'.config/home-server/secrets'
users=yaml.safe_load((private/'authelia/users.yml').read_text())['users']
assert users['mgouda']['groups']==groups('mgouda') and 'owners' not in groups('mgouda')
with sqlite3.connect('file:/mnt/server/jellyfin/config/data/data/jellyfin.db?mode=ro',uri=True) as db:
 row=db.execute('SELECT Id,Password FROM Users WHERE Username=?',('mgouda',)).fetchone()
 assert row and row[0].replace('-','').lower()=='21109ac1f8d24849b2165f7cca76fe7a'
 assert module.import_jellyfin(row[1])==users['mgouda']['password'],'Native and central Mariam verifier diverged; require secure enrollment check'
with sqlite3.connect('file:/mnt/server/jellyseerr/config/db/db.sqlite3?mode=ro',uri=True) as db:
 row=db.execute('SELECT id,jellyfinUserId,permissions FROM user WHERE jellyfinUsername=?',('mgouda',)).fetchone()
 assert row==(2,'21109ac1f8d24849b2165f7cca76fe7a',160),'Existing request profile or permissions changed'
with sqlite3.connect('file:/mnt/server/homarr/appdata/db/db.sqlite?mode=ro',uri=True) as db:
 user,board=db.execute('SELECT id,home_board_id FROM user WHERE name=?',('mgouda',)).fetchone()
 assert db.execute('SELECT is_public FROM board WHERE id=?',(board,)).fetchone()==(0,)
 assert db.execute('SELECT permission FROM boardUserPermission WHERE board_id=? AND user_id=?',(board,user)).fetchall()==[('view',)]
 assert not db.execute('SELECT 1 FROM groupMember m JOIN groupPermission p ON p.group_id=m.group_id WHERE m.user_id=?',(user,)).fetchall()
 apps=db.execute("SELECT a.href FROM item i JOIN app a ON a.id=json_extract(i.options,'$.json.appId') WHERE i.board_id=?",(board,)).fetchall()
 catalog=json.loads((ROOT/'config/services.json').read_text())['services']
 assert {x[0] for x in apps}=={s['url'] for s in catalog if allowed('mgouda',s['id']) and s['id']!='homarr'}
print('PASS Mariam: original media identity/password verifier/request permissions preserved; private read-only allowed-service dashboard; no global admin privileges')
print('Interactive Mariam sign-in is not exercised without her password.')
