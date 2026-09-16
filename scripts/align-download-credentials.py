#!/usr/bin/env python3
"""Align qBittorrent, Sonarr and Radarr owner logins without service restarts."""
from datetime import datetime, timezone
from pathlib import Path
import http.cookiejar
import json
import os
import shutil
import sqlite3
import urllib.parse
import urllib.request

def main():
    os.umask(0o077)
    passwords=json.loads((Path.home()/'.config/home-server/secrets/pending-service-passwords.json').read_text())
    password=passwords['torrents']
    settings=json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text())
    backup=Path.home()/'.local/state/home-server-maintenance/download-credentials'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    paths={'sonarr':Path('/mnt/server/sonarr/data'),'radarr':Path('/mnt/server/radarr/config')}
    for name,path in paths.items():
        shutil.copy2(path/'config.xml',backup/(name+'-config.xml'))
        with sqlite3.connect('file:'+str(path/(name+'.db'))+'?mode=ro',uri=True) as db:
            with sqlite3.connect(backup/(name+'.db')) as saved: db.backup(saved)
    shutil.copy2('/mnt/server/qbittorrent/config/qBittorrent/qBittorrent.conf',backup/'qBittorrent.conf')
    def arr(name,path,data=None,method=None):
        config=settings[name][0]
        req=urllib.request.Request('http://127.0.0.1:'+str(config['port'])+'/api/v3'+path,
            data=None if data is None else json.dumps(data).encode(),method=method,
            headers={'X-Api-Key':config['apiKey'],'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:
            content=response.read();return json.loads(content) if content else None
    with sqlite3.connect('file:'+str(paths['sonarr']/'sonarr.db')+'?mode=ro',uri=True) as db:
        old=json.loads(db.execute("SELECT Settings FROM DownloadClients WHERE Implementation='QBittorrent'").fetchone()[0])
    old={k.lower():v for k,v in old.items()}
    qbase='http://127.0.0.1:15080'
    def qlogin(username,secret):
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        req=urllib.request.Request(qbase+'/api/v2/auth/login',data=urllib.parse.urlencode({'username':username,'password':secret}).encode(),headers={'Referer':qbase+'/'})
        with opener.open(req,timeout=15) as response:
            body=response.read()
            assert (response.status==204 and not body) or body==b'Ok.','qBittorrent login failed'
        return opener
    q=qlogin(old['username'],old['password'])
    prefs={'web_ui_username':'egouda','web_ui_password':password,'bypass_local_auth':False,'bypass_auth_subnet_whitelist_enabled':False}
    req=urllib.request.Request(qbase+'/api/v2/app/setPreferences',data=urllib.parse.urlencode({'json':json.dumps(prefs)}).encode(),headers={'Referer':qbase+'/'})
    with q.open(req,timeout=15) as response:response.read()
    q=qlogin('egouda',password)
    with q.open(qbase+'/api/v2/app/version') as response:assert response.read()
    with q.open(urllib.request.Request(qbase+'/api/v2/auth/logout',data=b'')) as response:response.read()
    print('qBittorrent owner login aligned and verified.')
    for name in paths:
        for client in arr(name,'/downloadclient'):
            if client['implementation']!='QBittorrent':continue
            for field in client['fields']:
                if field['name']=='username':field['value']='egouda'
                if field['name']=='password':field['value']=password
            arr(name,'/downloadclient/'+str(client['id']),client,'PUT')
            arr(name,'/downloadclient/test',client,'POST')
        host=arr(name,'/config/host')
        host.update({'username':'egouda','password':passwords[name],'passwordConfirmation':passwords[name],
                     'authenticationMethod':'forms','authenticationRequired':'enabled'})
        arr(name,'/config/host',host,'PUT')
        print(name+' owner login aligned; qBittorrent connection test passed.')
    active=Path.home()/'.config/home-server/secrets/service-passwords.json'
    saved=json.loads(active.read_text()) if active.exists() else {}
    saved.update({k:passwords[k] for k in ['torrents','sonarr','radarr']})
    active.write_text(json.dumps(saved));active.chmod(0o600)
    print('Private recovery snapshot: '+str(backup))

if __name__=='__main__':main()
