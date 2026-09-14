#!/usr/bin/env python3
"""Verify authenticated web/SMB access to the same files; remove only own probes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import uuid

share = Path('/Volumes/Creative')
if not os.path.ismount(share):
    raise SystemExit('Mount Creative in Finder before running this check.')
result = subprocess.run(['security', 'find-internet-password', '-a', 'egouda',
                         '-s', 'home-server.lan', '-w'], capture_output=True, text=True)
if result.returncode:
    raise SystemExit('Creative credential not found in the login Keychain.')
password = result.stdout.rstrip('\n')
del result
base = 'http://files.lan'
request = urllib.request.Request(base + '/api/login',
    data=json.dumps({'username': 'egouda', 'password': password}).encode(),
    headers={'Content-Type': 'application/json'})
del password
with urllib.request.urlopen(request, timeout=15) as response:
    token = response.read().decode().strip().strip('"')
def call(path, method='GET', data=None):
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={'X-Auth': token, 'Content-Type': 'application/octet-stream'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()

name = '.home-server-check-' + uuid.uuid4().hex + '.bin'
relative = 'Incoming/' + name
local = share / relative
payload = os.urandom(256 * 1024)
try:
    local.write_bytes(payload)
    if call('/api/raw/' + relative) != payload:
        raise ValueError('SMB write / web download mismatch.')
    print('PASS: authenticated web download matches an SMB-written file (SHA-256).')
    local.unlink()
    call('/api/resources/' + relative + '?override=false', method='POST', data=payload)
    if hashlib.sha256(local.read_bytes()).digest() != hashlib.sha256(payload).digest():
        raise ValueError('Web upload / SMB read mismatch.')
    print('PASS: web upload is readable through Finder with matching SHA-256.')
finally:
    local.unlink(missing_ok=True)
try:
    urllib.request.urlopen(base + '/api/resources/', timeout=10)
except urllib.error.HTTPError as error:
    if error.code not in [401, 403]:
        raise
    print('PASS: anonymous file access denied.')
else:
    raise SystemExit('FAIL: anonymous file access unexpectedly allowed.')
