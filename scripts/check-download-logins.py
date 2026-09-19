#!/usr/bin/env python3
"""Verify native recovery credentials and seamless central download-app access."""
from auth_session import AuthSession
import argparse
import http.cookiejar
import json
import re
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

APPS=[('torrents',15080),('sonarr',8989),('radarr',7878),('prowlarr',9696)]
BRIDGED={'torrents','sonarr'}

def basic(base,jar,password):
    manager=urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None,base,'egouda',password)
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.HTTPBasicAuthHandler(manager))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local',action='store_true',help='Verify direct native recovery credentials')
    parser.add_argument('--native-only',action='store_true',help='Verify final native forms without requiring all proxy bridges')
    args=parser.parse_args()
    secrets=Path.home()/'.config/home-server/secrets'
    passwords=json.loads((secrets/'service-passwords.json').read_text())
    gateway=AuthSession() if not args.local and 'auth' in passwords else None
    if gateway:
        import atexit;atexit.register(gateway.close)
    for name,port in APPS:
        password=passwords.get(name) or (secrets/'creative_password').read_text().strip()
        base='http://127.0.0.1:'+str(port) if args.local else 'https://'+name+'.home.egouda.xyz'
        jar=gateway.cookies if gateway else http.cookiejar.CookieJar()
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        is_q=name=='torrents'
        if name in BRIDGED and not args.local and not args.native_only:
            endpoint='/api/v2/app/version' if is_q else '/'
            with opener.open(base+endpoint,timeout=20) as response:
                body=response.read()
                assert response.status==200 and 'login' not in urllib.parse.urlsplit(response.url).path.lower()
                if is_q:assert body.startswith(b'v5.')
                else:assert not re.search(rb'type=["\x27]password',body.lower())
            print('PASS '+name+' central credential only -> authenticated application')
            continue
        if not is_q:
            try:
                with opener.open(base,timeout=20) as response:
                    login=urllib.parse.urlsplit(response.url).path.lower().startswith('/login')
            except urllib.error.HTTPError as error:
                if error.code!=401:raise
                login=False;opener=basic(base,jar,password)
                with opener.open(base,timeout=20) as response:
                    assert response.status==200 and not re.search(rb'type=["\x27]password',response.read().lower())
                print('PASS '+name+' native Basic recovery login')
                continue
            assert login,'Anonymous UI is not protected'
        path='/api/v2/auth/login' if is_q else '/login'
        req=urllib.request.Request(base+path,data=urllib.parse.urlencode({'username':'egouda','password':password,'rememberMe':'false'}).encode(),headers={'Origin':base,'Referer':base+'/'})
        with opener.open(req,timeout=20) as response:
            body=response.read()
            if is_q:assert (response.status==204 and not body) or body==b'Ok.','qBittorrent login rejected'
        endpoint='/api/v2/app/version' if is_q else '/'
        with opener.open(base+endpoint,timeout=20) as response:assert response.status==200
        print('PASS '+name+' native form recovery login')

if __name__=='__main__':main()
