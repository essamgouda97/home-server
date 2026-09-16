#!/usr/bin/env python3
"""Check People owner authentication and public invitation isolation."""
import argparse
from pathlib import Path
import urllib.error
import urllib.request
from auth_session import AuthSession,NoRedirect,PORTAL

def request(opener,url,headers=None):
    try:return opener.open(urllib.request.Request(url,headers=headers or {}),timeout=10)
    except urllib.error.HTTPError as error:return error

def main():
    p=argparse.ArgumentParser();p.add_argument('--local',action='store_true');a=p.parse_args()
    key=(Path.home()/'.config/home-server/secrets/people/proxy-key').read_text().strip()
    local='http://172.18.0.1:8766'
    opener=urllib.request.build_opener(NoRedirect)
    with request(opener,local+'/health') as r:assert r.status==200
    with request(opener,local+'/',{'Remote-User':'egouda','Remote-Groups':'owners'}) as r:assert r.status==403
    with request(opener,local+'/',{'X-Home-People-Key':key,'Remote-User':'mgouda','Remote-Groups':'household'}) as r:assert r.status==403
    with request(opener,local+'/',{'X-Home-People-Key':key,'Remote-User':'egouda','Remote-Groups':'owners','Host':'people.home.egouda.xyz'}) as r:assert r.status==200 and b'Household access' in r.read()
    print('PASS People local owner boundary')
    if a.local:return
    url='https://people.home.egouda.xyz'
    with request(opener,url,{'Remote-User':'egouda','X-Forwarded-Groups':'owners'}) as r:
        assert r.status==302 and r.headers.get('Location','').startswith(PORTAL+'/')
    with AuthSession() as session:
        with request(session.no_redirect,url) as r:assert r.status==200 and b'Household access' in r.read()
    with request(opener,url+'/join/') as r:assert r.status==200 and b'Your home server invitation' in r.read()
    with request(opener,url+'/join/api/invitation') as r:
        assert r.status==404  # public GETs cannot reveal invitation records
    with request(opener,url+'/api/state') as r:
        assert r.status==302 and r.headers.get('Location','').startswith(PORTAL+'/')
    print('PASS People owner HTTPS login and isolated invitation page')

if __name__=='__main__':main()
