#!/usr/bin/env python3
"""Mac check of private app routes, static assets, document source and CSRF."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

password=subprocess.run(['security','find-internet-password','-a','egouda','-s','files.lan','-w'],
    capture_output=True,text=True,check=True).stdout.rstrip('\n')
auth='Basic '+base64.b64encode(('egouda:'+password).encode()).decode()
del password
def request(path, *, authenticated=True, data=None, origin=None):
    headers={'Authorization':auth} if authenticated else {}
    if data is not None: headers['Content-Type']='application/json'
    if origin: headers['Origin']=origin
    req=urllib.request.Request('http://life.lan'+path,headers=headers,data=data)
    try:
        with urllib.request.urlopen(req,timeout=60) as r: return r.status,r.read()
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
    assert request(path,authenticated=False)[0]==401
assert request('/api/data-version',authenticated=False)[0]==401
assert request('/api/canada-home/lease',data=b'{}',origin='http://untrusted.invalid')[0]==403
assert request('/api/canada-home/lease',data=b'{}',origin='http://life.lan')[0]==400
print('PASS: protected static assets, authentication, and write-origin checks.')
assert Path('/Volumes/LifeDashboard/docs').is_dir()
print('PASS: shared documents mounted in Finder.')
code,body=request('/api/sync-status');state=json.loads(body)
assert state['state'] in ('waiting','processing','ready'), state['state']
print('PASS: document worker status:',state['state'])
code,body=request('/api/content/canvas/ai');assert json.loads(body)['codex']['signedIn']
print('PASS: Codex subscription login available.')
