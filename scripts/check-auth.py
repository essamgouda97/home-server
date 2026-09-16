#!/usr/bin/env python3
"""Verify every registered browser route, identity spoof rejection and logout."""
import argparse
from pathlib import Path
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from auth_policy import services
from auth_session import AuthSession,NoRedirect,PORTAL

def response(opener,url,headers=None):
    try:return opener.open(urllib.request.Request(url,headers=headers or {}),timeout=20)
    except urllib.error.HTTPError as error:return error

def main():
    anonymous=urllib.request.build_opener(NoRedirect)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--staged',action='store_true');args=parser.parse_args()
    password=None
    if args.staged:password=json.loads((Path.home()/'.config/home-server/secrets/pending-service-passwords.json').read_text())['auth']
    with AuthSession(password=password) as session:
        for host,entry in services().items():
            with response(anonymous,entry['url'],{'Remote-User':'egouda','X-Forwarded-User':'egouda','X-Forwarded-Groups':'owners','X-Auth-Request-User':'egouda'}) as r:
                # Root paths may redirect to the app's actual path before access phase.
                if r.status in (301,302,303,307,308) and r.headers.get('Location','').startswith('/'):
                    r=response(anonymous,'https://'+host+r.headers['Location'])
                assert r.status==302 and r.headers.get('Location','').startswith(PORTAL+'/'),(entry['id'],'missing central sign-in')
                assert not r.headers.get('WWW-Authenticate'),(entry['id'],'browser Basic prompt remains')
            with response(session.no_redirect,entry['url']) as r:
                assert r.status in (200,301,302,303,307,308), (entry['id'],'authenticated app unavailable',r.status)
                assert not r.headers.get('WWW-Authenticate')
                assert not r.headers.get('Location','').startswith(PORTAL+'/'),(entry['id'],'session not shared')
            print('PASS central sign-in, spoof rejection and owner session:',entry['id'])
        cookies=list(session.cookies)
        assert any(c.name=='home_session' and c.secure and c.has_nonstandard_attr('HttpOnly') for c in cookies)
        saved=session.cookie_header('https://life.home.egouda.xyz')
    with response(anonymous,'https://life.home.egouda.xyz',{'Cookie':saved}) as r:
        assert r.status==302 and r.headers.get('Location','').startswith(PORTAL+'/'),'Logout did not revoke server session'
    print('PASS secure HttpOnly shared cookie and server-side logout revocation')

if __name__=='__main__':main()
