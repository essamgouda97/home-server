#!/usr/bin/env python3
"""Server-side password change; read the new password only from private stdin."""
from pathlib import Path
import json
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
secret = Path(settings['HOME_SERVER_SECRETS_DIR']) / 'creative_password'
old = secret.read_text()
new = sys.stdin.read()
if len(new) < 12 or any(ord(c) < 32 for c in new):
    raise SystemExit('Use at least 12 characters with no control characters.')

def change_ha(current, replacement):
    worker = r'''
import asyncio, aiohttp
async def main():
    base = 'http://' + SERVER_IP + ':8123'
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async def post(path, payload, form=False):
            async with session.post(base + path, **{'data' if form else 'json':payload}) as r:
                r.raise_for_status()
                return await r.json()
        async def login(password):
            flow = await post('/auth/login_flow', dict(client_id=base+'/', redirect_uri=base+'/', handler=['homeassistant',None]))
            result = await post('/auth/login_flow/'+flow['flow_id'], dict(client_id=base+'/', username='egouda',password=password))
            if result.get('type') != 'create_entry':
                raise RuntimeError('Owner login needs manual action')
            return await post('/auth/token',dict(grant_type='authorization_code',code=result['result'],client_id=base+'/'),True)
        tokens = await login(CURRENT)
        try:
            async with session.ws_connect(base+'/api/websocket') as ws:
                await ws.receive_json()
                await ws.send_json(dict(type='auth',access_token=tokens['access_token']))
                assert (await ws.receive_json())['type']=='auth_ok'
                await ws.send_json(dict(id=1,type='config/auth_provider/homeassistant/change_password',current_password=CURRENT,new_password=REPLACEMENT))
                assert (await ws.receive_json()).get('success')
            print('CHANGED',flush=True)
            verified = await login(REPLACEMENT)
            async with session.post(base+'/auth/token',data={'action':'revoke','token':verified['refresh_token']}): pass
        finally:
            async with session.post(base+'/auth/token',data={'action':'revoke','token':tokens['refresh_token']}): pass
asyncio.run(main())
'''
    code = 'CURRENT='+repr(current)+'\nREPLACEMENT='+repr(replacement)+'\nSERVER_IP='+repr(settings['SERVER_IP'])+'\n'+worker
    result = subprocess.run(['docker','exec','-i','homeassistant','python3','-'],input=code,text=True,capture_output=True)
    return result.returncode == 0, 'CHANGED' in result.stdout.splitlines()

def change_files(password):
    stopped = subprocess.run(['docker','stop','filebrowser'],capture_output=True)
    if stopped.returncode:
        return False
    try:
        result = subprocess.run(['docker','compose','--env-file','server.conf','--env-file','.env',
                                 'run','--rm','--no-deps','filebrowser','--config','/config/settings.json',
                                 'users','update','egouda','--password',password],cwd=repo,capture_output=True)
    finally:
        started = subprocess.run(['docker','start','filebrowser'],capture_output=True)
    return result.returncode == 0 and started.returncode == 0

ha_changed = files_attempted = secret_changed = False
try:
    success, ha_changed = change_ha(old, new)
    if not success:
        raise RuntimeError('Home Assistant password update failed.')
    files_attempted = True
    if not change_files(new):
        raise RuntimeError('Creative Drive password update failed.')
    # Preserve the inode used by the Compose secret bind mount.
    secret.write_text(new)
    secret.chmod(0o600)
    secret_changed = True
    if subprocess.run(['docker','restart','samba'],capture_output=True).returncode:
        raise RuntimeError('Samba password reload failed.')
except Exception:
    restored = True
    if secret_changed:
        secret.write_text(old)
        restored &= subprocess.run(['docker','restart','samba'],capture_output=True).returncode == 0
    if files_attempted:
        restored &= change_files(old)
    if ha_changed:
        restored &= change_ha(new, old)[0]
    raise SystemExit('Password change failed; previous credentials restored.' if restored else
                     'Password change failed and rollback was incomplete. Keep both passwords for recovery.')
print('Updated Creative Drive, Finder and Home Assistant passwords; Home Assistant login verified.')
