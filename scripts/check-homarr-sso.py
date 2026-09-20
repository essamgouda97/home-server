#!/usr/bin/env python3
"""Prove central login creates the existing native Homarr session (no app password)."""
import json
import http.cookiejar
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
        for padding in (0, 6000):
            if padding:
                session.cookies.set_cookie(http.cookiejar.Cookie(
                    version=0, name='home_header_regression', value='x'*padding,
                    port=None, port_specified=False, domain='home.egouda.xyz',
                    domain_specified=False, domain_initial_dot=False, path='/',
                    path_specified=True, secure=True, expires=None, discard=True,
                    comment=None, comment_url=None, rest={}, rfc2109=False))
            try:
                identity=homarr_login(session)
            finally:
                if padding:
                    session.cookies.clear('home.egouda.xyz', '/', 'home_header_regression')
            assert identity['id']=='k2yq2prk0rj6egguo0piwc0k','Existing owner identity was not preserved'
            assert identity['name']=='egouda'
        print('PASS Homarr OIDC with 6 KiB synthetic browser cookie; owner identity preserved')
        print('PASS central credential only -> Homarr OIDC -> existing owner identity and native session')
if __name__=='__main__':main()
