#!/usr/bin/env python3
"""Verify owner passwords with actual logins, never API keys or auth bypass."""
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
    args=parser.parse_args()
    password=(Path.home()/'.config/home-server/secrets/creative_password').read_text().strip()
    for name,port in [('torrents',15080),('sonarr',8989),('radarr',7878)]:
        base='http://127.0.0.1:'+str(port) if args.local else 'https://'+name+'.home.egouda.xyz'
        jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        is_q=name=='torrents'
        if not is_q:
            with opener.open(base,timeout=20) as response:
                assert urllib.parse.urlsplit(response.url).path.lower().startswith('/login'), 'Anonymous UI is not protected'
        path='/api/v2/auth/login' if is_q else '/login'
        req=urllib.request.Request(base+path,data=urllib.parse.urlencode({'username':'egouda','password':password,'rememberMe':'false'}).encode(),headers={'Origin':base,'Referer':base+'/'})
        with opener.open(req,timeout=20) as response:
            body=response.read()
            if is_q:assert body==b'Ok.','qBittorrent rejected the shared password'
        assert list(jar),'No authenticated session cookie: '+name
        endpoint='/api/v2/app/version' if is_q else '/'
        with opener.open(base+endpoint,timeout=20) as response:
            assert response.status==200
            if not is_q:
                assert urllib.parse.urlsplit(response.url).path in ['', '/']
                assert not re.search(r'type=["\x27]password',response.read().decode())
        logout='/api/v2/auth/logout' if is_q else '/logout'
        with opener.open(urllib.request.Request(base+logout,data=b'' if is_q else None),timeout=20) as response:response.read()
        print('PASS '+name+' egouda/shared-password login and authenticated access; logged out')

if __name__=='__main__':main()
