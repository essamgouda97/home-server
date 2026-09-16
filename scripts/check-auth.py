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
                for _ in range(4):
                    location=r.headers.get('Location','')
                    if r.status not in (301,302,303,307,308) or not (location.startswith('/') or urlsplit(location).hostname==host):break
                    from urllib.parse import urljoin
                    r.close()
                    r=response(anonymous,urljoin(entry['url'],location))
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
    import subprocess, re, yaml
    identities=yaml.safe_load((Path.home()/'.config/home-server/secrets/authelia/users.yml').read_text())['users']
    from identity_policy import groups, allowed
    assert identities['mgouda']['groups']==groups('mgouda')
    for host,entry in services().items():
        expected='one_factor' if allowed('mgouda',entry['id']) else 'deny'
        result=subprocess.run(['docker','exec','home-authelia','authelia','access-control','check-policy','--config','/config/configuration.yml','--username','mgouda','--groups',','.join(groups('mgouda')),'--url',entry['url']],capture_output=True,text=True,check=True)
        assert "The policy '"+expected+"'" in result.stdout,entry['id']+' household policy mismatch'
    print('PASS Mariam household access and owner-only denial across all registered apps')

if __name__=='__main__':main()
