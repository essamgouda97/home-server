#!/usr/bin/env python3
"""Verify owner passwords with actual logins, never API keys or auth bypass."""
from auth_session import AuthSession
import argparse
import http.cookiejar
import json
import re
from pathlib import Path
import urllib.parse
import urllib.request

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local',action='store_true',help='Check direct services before deploying proxy changes')
    parser.add_argument('--native-only',action='store_true',help='Verify native credentials without requiring the qBittorrent proxy bridge')
    args=parser.parse_args()
    secrets=Path.home()/'.config/home-server/secrets'
    active=secrets/'service-passwords.json'
    passwords=json.loads(active.read_text()) if active.exists() else {}
    gateway=AuthSession() if not args.local and 'auth' in passwords else None
    if gateway:
        import atexit
        atexit.register(gateway.close)
    for name,port in [('torrents',15080),('sonarr',8989),('radarr',7878),('prowlarr',9696)]:
        password=passwords.get(name) or (secrets/'creative_password').read_text().strip()
        base='http://127.0.0.1:'+str(port) if args.local else 'https://'+name+'.home.egouda.xyz'
        jar=gateway.cookies if gateway else http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        is_q=name=='torrents'
        if is_q and not args.local and not args.native_only:
            with opener.open(base+'/api/v2/app/version',timeout=20) as response:
                assert response.status==200 and response.read().startswith(b'v5.')
            print('PASS torrents central credential only -> authenticated qBittorrent API')
        if not is_q:
            with opener.open(base,timeout=20) as response:
                assert urllib.parse.urlsplit(response.url).path.lower().startswith('/login'), 'Anonymous UI is not protected'
        path='/api/v2/auth/login' if is_q else '/login'
        req=urllib.request.Request(base+path,data=urllib.parse.urlencode({'username':'egouda','password':password,'rememberMe':'false'}).encode(),headers={'Origin':base,'Referer':base+'/'})
        with opener.open(req,timeout=20) as response:
            body=response.read()
            if is_q:assert (response.status==204 and not body) or body==b'Ok.','qBittorrent login rejected'
        assert list(jar),'No authenticated session cookie: '+name
        endpoint='/api/v2/app/version' if is_q else '/'
        with opener.open(base+endpoint,timeout=20) as response:
            assert response.status==200
            if not is_q:
                assert urllib.parse.urlsplit(response.url).path in ['', '/']
                assert not re.search(r'type=["\x27]password',response.read().decode())
        logout='/api/v2/auth/logout' if is_q else '/logout'
        with opener.open(urllib.request.Request(base+logout,data=b'' if is_q else None),timeout=20) as response:response.read()
        print('PASS '+name+' egouda login and authenticated access; logged out')

if __name__=='__main__':main()
