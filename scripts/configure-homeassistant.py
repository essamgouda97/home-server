#!/usr/bin/env python3
"""Reconcile HA HTTP settings using its API; run on the server Docker operator.

Creates the initial owner only when onboarding has no user yet. Existing accounts
are preserved. Credentials travel over container stdin, never process arguments.
Home coordinates and phone pairing remain private UI tasks.
"""
import json
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
config = json.loads((repo / 'config/homeassistant/http.json').read_text())
config['server_host'] = [settings['SERVER_IP']]
password = (Path(settings['HOME_SERVER_SECRETS_DIR']) / 'creative_password').read_text()
worker = r'''
import asyncio
import aiohttp

async def main():
    base = 'http://' + SERVER_IP + ':8123'
    client = base + '/'
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async def request(path, payload=None, form=False, headers=None):
            async with s.request('GET' if payload is None else 'POST', base + path,
                                 **({'data' if form else 'json': payload} if payload is not None else {}),
                                 headers=headers) as r:
                if r.status >= 400:
                    raise RuntimeError('HA API failed: ' + path + ' HTTP ' + str(r.status))
                return await r.json()
        async with s.get(base + '/api/onboarding') as r:
            steps = await r.json() if r.status == 200 else []
        if any(x['step'] == 'user' and not x['done'] for x in steps):
            created = await request('/api/onboarding/users', dict(name='Essam', username='egouda',
                                    password=PASSWORD, client_id=client, language='en'))
            code = created['auth_code']
            print('Initial Home Assistant owner created: egouda.', flush=True)
        else:
            flow = await request('/auth/login_flow', dict(client_id=client,
                                redirect_uri=client, handler=['homeassistant', None]))
            result = await request('/auth/login_flow/' + flow['flow_id'],
                                   dict(client_id=client, username='egouda', password=PASSWORD))
            if result.get('type') != 'create_entry':
                raise RuntimeError('Owner login needs manual action; existing account preserved.')
            code = result['result']
        tokens = await request('/auth/token', dict(grant_type='authorization_code', code=code,
                               client_id=client), form=True)
        headers = {'Authorization': 'Bearer ' + tokens['access_token']}
        try:
            for step in ['core_config', 'analytics', 'integration']:
                if any(x['step'] == step and not x['done'] for x in steps):
                    payload = dict(client_id=client, redirect_uri=client) if step == 'integration' else {}
                    await request('/api/onboarding/' + step, payload, headers=headers)
            async def ws_call(kind, **fields):
                async with s.ws_connect(base + '/api/websocket') as ws:
                    await ws.receive_json()
                    await ws.send_json({'type':'auth', 'access_token':tokens['access_token']})
                    if (await ws.receive_json())['type'] != 'auth_ok':
                        raise RuntimeError('WebSocket login failed')
                    await ws.send_json(dict(id=1, type=kind, **fields))
                    result = await ws.receive_json()
                    if not result.get('success'):
                        raise RuntimeError('HA command failed: ' + kind)
                    return result.get('result')
            state = await ws_call('http/config')
            matches = all(state['stable'].get(k) == v for k, v in CONFIG.items())
            if not matches or state['active_config_type'] != 'stable':
                await ws_call('http/config/configure', config=CONFIG)
                print('HTTP configuration applied; waiting for Home Assistant restart.', flush=True)
                await asyncio.sleep(8)
                for attempt in range(75):
                    try:
                        async with s.get(base + '/', headers=headers) as direct:
                            direct.raise_for_status()
                        async with s.get('http://' + SERVER_IP + '/', headers={'Host':'assistant.lan'}) as proxy:
                            proxy.raise_for_status()
                        state = await ws_call('http/config')
                        active = state.get('pending') if state['active_config_type'] == 'pending' else state['stable']
                        if not active or not all(active.get(k) == v for k, v in CONFIG.items()):
                            raise RuntimeError('New HTTP configuration not active yet')
                        break
                    except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
                        await asyncio.sleep(2)
                else:
                    raise RuntimeError('HTTP checks failed; leaving HA automatic rollback enabled.')
                if state['active_config_type'] == 'pending':
                    await ws_call('http/config/promote')
            print('PASS: Home Assistant HTTP settings confirmed; direct and proxy access work.', flush=True)
        finally:
            async with s.post(base + '/auth/token', data={'action':'revoke', 'token':tokens['refresh_token']}):
                pass
asyncio.run(main())
'''
source = 'PASSWORD = ' + repr(password) + '\nSERVER_IP = ' + repr(settings['SERVER_IP']) + '\nCONFIG = ' + repr(config) + '\n' + worker
result = subprocess.run(['docker', 'exec', '-i', 'homeassistant', 'python3', '-'],
                        input=source, text=True, capture_output=True)
# Emit only intentional status lines; tracebacks can contain sensitive source.
for line in result.stdout.splitlines():
    if line.startswith(('Initial ', 'HTTP ', 'PASS:')):
        print(line)
if result.returncode:
    raise SystemExit('Home Assistant reconciliation failed. Check service health and owner login; no credentials printed.')
