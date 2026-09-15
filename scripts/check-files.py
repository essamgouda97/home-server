#!/usr/bin/env python3
"""Mac integration check: web browse/create/overwrite/delete on the live mounts.

Touches only uniquely named probes created by this run. Never reads user files.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import urllib.request
import uuid

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
home, data = settings['SERVER_HOME'], settings['SERVER_DATA_DIR']
roots = {'Creative': settings['CREATIVE_ROOT'], 'Code': home+'/workspace',
         'Repositories': home+'/repos', 'Media': data+'/media',
         'Downloads': data+'/downloads', 'Home': home, 'Storage': settings['SERVER_STORAGE']}
password = subprocess.run(['security','find-internet-password','-a','egouda','-s','files.lan','-w'],
                          capture_output=True,text=True,check=True).stdout.rstrip('\n')
base = 'http://files.lan'
req = urllib.request.Request(base+'/api/login',data=json.dumps(dict(username='egouda',password=password)).encode(),
                             headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=15) as r:
    token = r.read().decode().strip().strip('"')
del password
def call(path, method='GET', payload=None):
    req = urllib.request.Request(base+path,method=method,data=payload,
                                 headers={'X-Auth':token,'Content-Type':'application/octet-stream'})
    with urllib.request.urlopen(req,timeout=20) as r:
        return r.read()

listing = json.loads(call('/api/resources/'))
assert set(roots) <= {x['name'] for x in listing['items']}, 'Missing root folders'
print('PASS: all seven live server locations appear in files.lan.')
creative = json.loads(call('/api/resources/Creative/'))
aliases = set(roots) - {'Creative'}
assert not (aliases | {'Creative', 'LifeDashboard'}) & {x['name'] for x in creative['items']}, \
    'Server catalog mount placeholders leaked into the Creative workspace'
print('PASS: Creative is separate from the server catalog.')
for label, path in roots.items():
    call('/api/resources/'+label+'/')
    name = '.files-check-'+uuid.uuid4().hex+'.bin'
    # The mergerfs branch roots are root-owned; test its user-owned server
    # directory without changing host filesystem permissions.
    subdir = 'server/' if label == 'Storage' else ''
    relative = label+'/'+subdir+name
    payload = os.urandom(4096)
    created = False
    try:
        call('/api/resources/'+relative+'?override=false','POST',payload)
        created = True
        assert call('/api/raw/'+relative) == payload
        payload = b'updated-'+payload
        call('/api/resources/'+relative+'?override=true','POST',payload)
        remote = str(Path(path)/subdir/name)
        code = 'from pathlib import Path; import hashlib; print(hashlib.sha256(Path('+repr(remote)+').read_bytes()).hexdigest())'
        actual = subprocess.check_output(['ssh','home-server','python3 -c '+shlex.quote(code)],text=True).strip()
        assert actual == hashlib.sha256(payload).hexdigest(), 'Web upload does not match live server path'
        call('/api/resources/'+relative,'DELETE')
        created = False
        assert subprocess.run(['ssh','home-server','test ! -e '+shlex.quote(remote)]).returncode == 0
        print('PASS: '+label+' browse, upload, overwrite and delete match the live server directory.')
    finally:
        if created:
            call('/api/resources/'+relative,'DELETE')
