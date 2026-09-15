#!/usr/bin/env python3
"""Align egouda's Jellyfin password and Homarr integration with the household secret.

Run only when the owner requests password alignment. No password is displayed.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import urllib.error
import urllib.request

def main():
    os.umask(0o077)
    root=Path.home()/'.local/state/home-server-maintenance/jellyfin-password'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root.mkdir(parents=True)
    password=(Path.home()/'.config/home-server/secrets/creative_password').read_text().strip()
    settings=json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text())
    key=settings['jellyfin']['apiKey']
    def api(path,data=None):
        req=urllib.request.Request('http://127.0.0.1:8096'+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'X-Emby-Token':key,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                body=response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raise SystemExit('Jellyfin API failed: HTTP '+str(error.code)) from None
    users=[u for u in api('/Users') if u['Name']=='egouda']
    assert len(users)==1 and not users[0]['Policy']['IsDisabled']
    assert not any(s.get('NowPlayingItem') for s in api('/Sessions')), 'Playback active; defer password alignment'
    databases={'jellyfin':Path('/mnt/server/jellyfin/config/data/data/jellyfin.db'),
               'homarr':Path('/mnt/server/homarr/appdata/db/db.sqlite')}
    for name,path in databases.items():
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            with sqlite3.connect(root/(name+'.sqlite')) as backup:
                db.backup(backup)
                assert backup.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    with sqlite3.connect(databases['homarr']) as db:
        rows=db.execute('SELECT i.id,s.kind FROM integration i JOIN integrationSecret s ON s.integration_id=i.id WHERE lower(i.kind)=?',('jellyfin',)).fetchall()
        targets=[ident for ident,kind in rows if kind=='password']
        assert targets,'Expected a saved Homarr Jellyfin password'
        # Encrypt inside Homarr using its existing key. Capture ciphertext only.
        code='''const fs=require('fs'),crypto=require('crypto');
const value=fs.readFileSync(0,'utf8');
const key=Buffer.from(process.env.SECRET_ENCRYPTION_KEY,'hex'),iv=crypto.randomBytes(16);
const cipher=crypto.createCipheriv('aes-256-cbc',key,iv);
const encrypted=Buffer.concat([cipher.update(value),cipher.final()]);
const decipher=crypto.createDecipheriv('aes-256-cbc',key,iv);
if(Buffer.concat([decipher.update(encrypted),decipher.final()]).toString()!==value)process.exit(1);
process.stdout.write(encrypted.toString('hex')+'.'+iv.toString('hex'));'''
        encrypted=subprocess.run(['docker','exec','-i','homarr','node','-e',code],input=password,
            text=True,capture_output=True,check=True).stdout
        assert len(encrypted.split('.'))==2
        api('/Users/'+users[0]['Id']+'/Password',{'NewPw':password,'ResetPassword':False})
        db.execute('BEGIN IMMEDIATE')
        for ident in targets:
            db.execute('UPDATE integrationSecret SET value=?,updated_at=? WHERE integration_id=? AND kind=?',
                       (encrypted,int(datetime.now(timezone.utc).timestamp()*1000),ident,'password'))
    print('Jellyfin egouda password aligned; Homarr integration updated. Backups: '+str(root))

if __name__=='__main__': main()
