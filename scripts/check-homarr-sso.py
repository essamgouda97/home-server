#!/usr/bin/env python3
"""Prove central login creates the existing native Homarr session (no app password)."""
import json
import urllib.request
import urllib.parse
from auth_session import AuthSession

BASE='https://home.egouda.xyz'
def homarr_login(session):
    with session.opener.open(BASE+'/api/auth/csrf',timeout=20) as r:csrf=json.load(r)['csrfToken']
    data=urllib.parse.urlencode({'csrfToken':csrf,'callbackUrl':BASE+'/boards','json':'true'}).encode()
    req=urllib.request.Request(BASE+'/api/auth/signin/oidc',data=data,headers={'Content-Type':'application/x-www-form-urlencoded','X-Auth-Return-Redirect':'1','Origin':BASE})
    with session.opener.open(req,timeout=25) as r:response=json.load(r)
    with session.opener.open(response['url'],timeout=25) as r:
        landing=urllib.parse.urlsplit(r.url)
        assert landing.hostname=='home.egouda.xyz','OIDC did not return to Homarr'
    with session.opener.open(BASE+'/api/auth/session',timeout=20) as r:identity=json.load(r)
    assert identity.get('user'),'Native session missing after central sign-in'
    return identity['user']

def main():
    with AuthSession() as session:
        identity=homarr_login(session)
        assert identity['id']=='k2yq2prk0rj6egguo0piwc0k','Existing owner identity was not preserved'
        assert identity['name']=='egouda'
        print('PASS central credential only -> Homarr OIDC -> existing owner identity and native session')
if __name__=='__main__':main()
