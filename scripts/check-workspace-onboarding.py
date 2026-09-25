#!/usr/bin/env python3
"""Verify public invitation routing with a synthetic invitation, then revoke it."""
import fcntl
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from auth_session import AuthSession, NoRedirect, prefer_ipv4

prefer_ipv4()
PUBLIC='https://workspace.egouda.xyz'
PEOPLE='https://people.home.egouda.xyz'
anonymous=urllib.request.build_opener(NoRedirect)

def post(opener, url, body, origin):
    request=urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type':'application/json','Origin':origin})
    try:return opener.open(request, timeout=20)
    except urllib.error.HTTPError as error:return error

with anonymous.open(PUBLIC+'/join/') as response:
    assert response.status==200 and b'Your home server invitation' in response.read()
with post(anonymous,PUBLIC+'/join/api/invitation',{'token':'invalid'},PUBLIC) as response:
    assert response.status==404
with post(anonymous,PUBLIC+'/join/api/invitation',{'token':'invalid'},'https://example.invalid') as response:
    assert response.status==403
print('PASS public join page, invalid-token denial and cross-origin denial')

with AuthSession() as session:
    with post(session.opener,PEOPLE+'/api/invitations',{'username':'wsverify'+str(int(time.time())),'name':'Synthetic onboarding verification','services':['workspace']},PEOPLE) as response:
        assert response.status==201
        invitation=json.load(response)
    assert invitation['url'].startswith(PUBLIC+'/join/#')
    token=invitation['url'].split('#',1)[1]
    try:
        with post(anonymous,PUBLIC+'/join/api/invitation',{'token':token},PUBLIC) as response:
            assert response.status==200 and json.load(response)['services']==['workspace']
    finally:
        private=Path.home()/'.config/home-server/secrets/people'
        with (private/'lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            store=json.loads((private/'invitations.json').read_text())
            digest=hashlib.sha256(token.encode()).hexdigest()
            store['invitations'][digest]['status']='revoked'
            pending=private/'workspace-check.pending'
            pending.write_text(json.dumps(store,indent=2)+'\n');pending.chmod(0o600);pending.replace(private/'invitations.json')
    with post(anonymous,PUBLIC+'/join/api/invitation',{'token':token},PUBLIC) as response:
        assert response.status==404
print('PASS owner-created Workspace-only invitation resolves publicly and revocation is enforced')
print('No person was enrolled and no invitation token was logged.')
