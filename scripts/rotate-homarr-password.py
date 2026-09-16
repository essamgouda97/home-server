#!/usr/bin/env python3
"""Rotate the owner login to its pre-saved vault credential and verify HTTPS login."""
import crypt
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request

def main():
    os.umask(0o077)
    root=Path.home()/'.config/home-server/secrets'
    password=json.loads((root/'pending-service-passwords.json').read_text())['homarr']
    path=Path('/mnt/server/homarr/appdata/db/db.sqlite')
    backup=Path.home()/'.local/state/home-server-maintenance/homarr-security'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        with sqlite3.connect(backup/'homarr.sqlite') as saved:db.backup(saved)
        salt=crypt.mksalt(crypt.METHOD_BLOWFISH,rounds=1024)
        user=db.execute('SELECT id FROM user WHERE name=?',('egouda',)).fetchone()
        assert user
        db.execute('UPDATE user SET password=? WHERE id=?',(crypt.crypt(password,salt),user[0]))
        # Password changes invalidate server-stored sessions.
        db.execute('DELETE FROM session WHERE user_id=?',(user[0],))
    base='https://home.egouda.xyz'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(base+'/api/auth/csrf') as r:csrf=json.load(r)['csrfToken']
    req=urllib.request.Request(base+'/api/auth/callback/credentials',data=urllib.parse.urlencode({'name':'egouda','password':password,'csrfToken':csrf,'callbackUrl':base+'/','json':'true'}).encode(),headers={'Origin':base,'X-Auth-Return-Redirect':'1'})
    with opener.open(req) as r:r.read()
    with opener.open(base+'/api/auth/session') as r:assert json.load(r)['user']['name']=='egouda'
    with opener.open(base+'/api/auth/csrf') as r:csrf=json.load(r)['csrfToken']
    with opener.open(urllib.request.Request(base+'/api/auth/signout',data=urllib.parse.urlencode({'csrfToken':csrf,'callbackUrl':base+'/','json':'true'}).encode())) as r:r.read()
    active=root/'service-passwords.json';saved=json.loads(active.read_text()) if active.exists() else {}
    saved['homarr']=password;active.write_text(json.dumps(saved));active.chmod(0o600)
    print('PASS Homarr unique owner password, real HTTPS login and logout; recovery snapshot saved.')

if __name__=='__main__':main()
