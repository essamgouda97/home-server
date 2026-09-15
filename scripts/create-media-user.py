#!/usr/bin/env python3
"""Create a standard Jellyfin/Jellyseerr account using a hidden local prompt.

Run on the Mac. Passwords travel only in memory through SSH stdin, never in
arguments, environment variables, files, logs or the chat transcript.
"""
import argparse
from datetime import datetime, timezone
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request

def worker():
    os.umask(0o077)
    payload=json.load(sys.stdin)
    name,password,display=payload['username'],payload['password'],payload['display_name']
    assert re.fullmatch(r'[a-z][a-z0-9_-]{1,30}',name) and len(password)>=8
    settings=json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text())
    def api(service,path,data=None,method=None,opener=None,headers=None):
        base='http://127.0.0.1:8096' if service=='jellyfin' else 'http://127.0.0.1:5055/api/v1'
        auth={'X-Emby-Token':settings['jellyfin']['apiKey']} if service=='jellyfin' else {'X-Api-Key':settings['main']['apiKey']}
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json',**(headers if headers is not None else auth)},method=method)
        try:
            with (opener or urllib.request.build_opener()).open(req,timeout=30) as response:
                body=response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(service+' '+path+' HTTP '+str(error.code)) from None
    assert not any(u['Name'].lower()==name.lower() for u in api('jellyfin','/Users')), 'Account already exists; no changes made'
    backup=Path.home()/'.local/state/home-server-maintenance/media-users'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    for label,path in [('jellyfin','/mnt/server/jellyfin/config/data/data/jellyfin.db'),('jellyseerr','/mnt/server/jellyseerr/config/db/db.sqlite3')]:
        with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as source:
            with sqlite3.connect(backup/(label+'.sqlite')) as saved:
                source.backup(saved)
                assert saved.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    user=api('jellyfin','/Users/New',{'Name':name,'Password':password})
    uid=user['Id']
    (backup/'created-account.json').write_text(json.dumps({'username':name,'jellyfin_id':uid}))
    # Keep normal media access; never grant administration or media deletion.
    policy=user['Policy']
    policy.update({'IsAdministrator':False,'EnableContentDeletion':False,
                   'EnableContentDeletionFromFolders':[],'EnableSharedDeviceControl':False,
                   'EnableRemoteControlOfOtherUsers':False})
    api('jellyfin','/Users/'+uid+'/Policy',policy)
    assert not api('jellyfin','/Users/'+uid)['Policy']['IsAdministrator']
    imported=api('requests','/user/import-from-jellyfin',{'jellyfinUserIds':[uid]})
    assert len(imported)==1
    sid=imported[0]['id']
    # Follow the household auto-approval choice without inheriting admin/4K rights.
    permissions=32 | (int(settings['main'].get('defaultPermissions',32)) & 128)
    api('requests','/user/'+str(sid),{'username':display,'permissions':permissions},method='PUT')
    info=api('requests','/user/'+str(sid))
    assert info['jellyfinUserId'].replace('-','')==uid.replace('-','') and info['permissions']==permissions
    # Validate the actual user login, without any administrator credential.
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    api('requests','/auth/jellyfin',{'username':name,'password':password},opener=opener,headers={})
    logged_in=api('requests','/auth/me',opener=opener,headers={})
    assert logged_in['id']==sid
    api('requests','/auth/logout',{},opener=opener,headers={})
    # HTTPS login proves the browser-facing route accepts the same credential.
    host='https://requests.home.egouda.xyz'
    req=urllib.request.Request(host+'/api/v1/auth/jellyfin',data=json.dumps({'username':name,'password':password}).encode(),headers={'Content-Type':'application/json','Origin':host})
    with opener.open(req,timeout=30) as response: response.read()
    with opener.open(host+'/api/v1/auth/me',timeout=30) as response: assert json.load(response)['id']==sid
    req=urllib.request.Request(host+'/api/v1/auth/logout',data=b'{}',headers={'Content-Type':'application/json','Origin':host})
    with opener.open(req,timeout=30) as response: response.read()
    print(json.dumps({'status':'complete','username':name,'display_name':display,'jellyfin_id':uid,'jellyseerr_id':sid,'https_login_verified':True,'admin':False}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--username')
    parser.add_argument('--display-name')
    args=parser.parse_args()
    if args.worker:
        try: worker()
        except Exception as error:
            print(json.dumps({'status':'failed','error':str(error) if isinstance(error,(AssertionError,RuntimeError)) else type(error).__name__}))
            raise SystemExit(1)
        return
    if not sys.stdin.isatty(): raise SystemExit('Run this in Terminal for a hidden password prompt.')
    if not args.username or not args.display_name: parser.error('username and display-name are required')
    print('Create '+args.display_name+' ('+args.username+') in Jellyfin and Requests.')
    print('Password input is hidden and is never saved by this script.')
    while True:
        password=getpass.getpass('New password: ')
        if len(password)<8:
            print('Use at least 8 characters.'); continue
        if password!=getpass.getpass('Confirm password: '):
            print('Passwords did not match. Try again.'); continue
        break
    data=json.dumps({'username':args.username,'display_name':args.display_name,'password':password})
    result=subprocess.run(['ssh','-T','-o','BatchMode=yes','home-server',
        'python3 /home/egouda/workspace/home-server/scripts/create-media-user.py --worker'],input=data,text=True,capture_output=True)
    del password,data
    status=Path.home()/'.local/state/home-server-maintenance/media-users'
    status.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.umask(0o077)
    try: report=json.loads(result.stdout)
    except Exception: report={'status':'failed','error':'Connection or worker failure'}
    (status/(args.username+'-result.json')).write_text(json.dumps(report))
    if report.get('status')!='complete':
        print('Setup did not complete. Tell Codex to inspect the status; do not send your password.')
        raise SystemExit(1)
    print('Ready: '+args.username+' works in Jellyfin and Requests with the password you entered.')
    print('https://jellyfin.home.egouda.xyz\nhttps://requests.home.egouda.xyz')

if __name__=='__main__': main()
