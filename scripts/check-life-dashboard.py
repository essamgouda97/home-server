#!/usr/bin/env python3
"""Mac check of private app routes, static assets, document source and CSRF."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from auth_session import AuthSession, NoRedirect
import os
import atexit
# On the Mac use vault.py exec auth; on the server use the private applied secret.
gateway=AuthSession(password=os.environ.get('HOME_SERVICE_PASSWORD'))
atexit.register(gateway.close)
anonymous=urllib.request.build_opener(NoRedirect)
def request(path, *, authenticated=True, data=None, origin=None):
    headers={}
    if data is not None: headers['Content-Type']='application/json'
    if origin: headers['Origin']=origin
    req=urllib.request.Request('https://life.home.egouda.xyz'+path,headers=headers,data=data)
    try:
        with (gateway.opener if authenticated else anonymous).open(req,timeout=60) as r: return r.status,r.read()
    except urllib.error.HTTPError as e: return e.code,e.read()

for route in ('/','/documents','/finances','/medical','/canada-home','/content','/content/canvas','/about','/hikes','/api/data-version','/api/sync-status'):
    code,body=request(route)
    assert code==200 and b'Application error: a server-side exception' not in body, route
    print('PASS:',route)
code,body=request('/')
assets=set(re.findall(rb'(?:src|href)="(/_next/static/[^"?]+)',body))
assert assets
for asset in assets:
    path=asset.decode();assert request(path)[0]==200
    assert request(path,authenticated=False)[0]==302
assert request('/api/data-version',authenticated=False)[0]==302
assert request('/api/canada-home/lease',data=b'{}',origin='http://untrusted.invalid')[0]==403
assert request('/api/canada-home/lease',data=b'{}',origin='https://life.home.egouda.xyz')[0]==400
print('PASS: protected static assets, authentication, and write-origin checks.')
if __import__('sys').platform=='darwin':
    assert Path('/Volumes/LifeDashboard/docs').is_dir()
    print('PASS: shared documents mounted in Finder.')
code,body=request('/api/sync-status');state=json.loads(body)
assert state['state'] in ('waiting','processing','ready'), state['state']
print('PASS: document worker status:',state['state'])
code,body=request('/api/content/canvas/ai');assert json.loads(body)['codex']['signedIn']
print('PASS: Codex subscription login available.')
