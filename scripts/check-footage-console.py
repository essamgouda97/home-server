#!/usr/bin/env python3
"""Read-only server check of login enforcement, tracking data and Codex worker."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
url='http://'+settings['SERVER_IP']+'/api/state'
headers={'Host':'ingest.lan'}
try:
    urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=10)
    raise SystemExit('FAIL: unauthenticated tracking data was accessible.')
except urllib.error.HTTPError as error:
    status=error.code;error.close()
    if status != 401: raise SystemExit('FAIL: expected a login challenge.')
print('PASS: unauthenticated requests require login.')
password=(Path(settings['HOME_SERVER_SECRETS_DIR'])/'creative_password').read_bytes().rstrip(b'\n')
headers['Authorization']='Basic '+base64.b64encode(b'egouda:'+password).decode()
del password
with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=10) as response:
    state=json.load(response)
print('PASS: authenticated tracking API is available.')
worker=state['worker']
if not worker.get('seen_at') or (datetime.now(timezone.utc)-datetime.fromisoformat(worker['seen_at'])).total_seconds()>240:
    raise SystemExit('FAIL: Codex worker has not reported recently.')
print('PASS: Codex worker heartbeat is current.')
request=urllib.request.Request('http://'+settings['SERVER_IP']+'/api/retry',b'{}',
    dict(headers, Origin='http://untrusted.invalid', **{'Content-Type':'application/json'}))
try:
    urllib.request.urlopen(request,timeout=10)
    raise SystemExit('FAIL: cross-origin mutation was accepted.')
except urllib.error.HTTPError as error:
    status=error.code;error.close()
    if status != 403: raise SystemExit('FAIL: expected origin rejection.')
print('PASS: cross-origin changes are rejected.')
print('Station:', 'recently connected' if state['station_online'] else 'no recent heartbeat')
print('Tracked imports:',len(state['imports']))
