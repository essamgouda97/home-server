#!/usr/bin/env python3
"""Reconcile the Codex Assist pipeline with supported HA APIs (server only).

--check uses subscription quota to toggle only the virtual demo switch on/off.
Owner credentials and temporary session tokens never leave subprocess stdin.
"""
import argparse
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
parser.add_argument('--voice', action='store_true', help='Reconcile local Whisper/Piper and Home Local pipeline')
parser.add_argument('--check-voice', action='store_true', help='Test synthetic spoken commands through both pipelines')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
password = (Path(settings['HOME_SERVER_SECRETS_DIR'])/'creative_password').read_text()
worker = r'''
import asyncio
import aiohttp

async def main():
    base = 'http://' + SERVER_IP + ':8123'
    client = base + '/'
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as s:
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
            states = await request('/api/states', headers=headers)
            agents = [x['entity_id'] for x in states if x['entity_id'].startswith('conversation.')
                      and x['attributes'].get('friendly_name') == 'Codex']
            if len(agents) != 1:
                raise RuntimeError('Codex conversation entity is not available')
            agent = agents[0]
            pipelines = (await ws_call('assist_pipeline/pipeline/list'))['pipelines']
            existing = next((p for p in pipelines if p['name'] == 'Codex'), None)
            desired = dict(name='Codex', conversation_engine=agent, conversation_language='en',
                           language='en', stt_engine=None, stt_language=None, tts_engine=None,
                           tts_language=None, tts_voice=None, wake_word_entity=None,
                           wake_word_id=None, prefer_local_intents=False)
            if existing:
                # Preserve any speech engines added later in the UI.
                # HA requires the full schema for updates, not a partial patch.
                desired = {k: existing.get(k, v) for k, v in desired.items()}
                desired.update(conversation_engine=agent, conversation_language='en')
                await ws_call('assist_pipeline/pipeline/update', pipeline_id=existing['id'], **desired)
                pipeline_id = existing['id']
            else:
                created = await ws_call('assist_pipeline/pipeline/create', **desired)
                pipeline_id = created['id']
            await ws_call('assist_pipeline/pipeline/set_preferred', pipeline_id=pipeline_id)
            await ws_call('homeassistant/expose_entity', assistants=['conversation'],
                          entity_ids=['input_boolean.codex_demo'], should_expose=True)
            preferred = await ws_call('assist_pipeline/pipeline/get')
            if preferred['conversation_engine'] != agent:
                raise RuntimeError('Codex is not the preferred pipeline')
            print('PASS: Codex is the default Assist agent; virtual demo switch exposed.', flush=True)
            if VOICE:
                await configure_voice(request, ws_call, headers, pipeline_id)
            if CHECK_VOICE:
                await check_voice(s, base, tokens['access_token'], request, ws_call, headers)
            if CHECK:
                conversation_id = None
                for text, expected in [('Turn on the Codex demo switch.', 'on'),
                                       ('Turn off the Codex demo switch.', 'off')]:
                    payload = dict(text=text, language='en', agent_id=agent)
                    if conversation_id:
                        payload['conversation_id'] = conversation_id
                    result = await request('/api/conversation/process', payload, headers=headers)
                    if result['response']['response_type'] == 'error':
                        raise RuntimeError('Codex conversation returned an error')
                    conversation_id = result['conversation_id']
                    state = await request('/api/states/input_boolean.codex_demo', headers=headers)
                    if state['state'] != expected:
                        raise RuntimeError('Codex did not change the virtual switch')
                    print('PASS: Codex changed virtual demo switch to ' + expected + '.', flush=True)
        finally:
            async with s.post(base + '/auth/token', data={'action':'revoke', 'token':tokens['refresh_token']}):
                pass
asyncio.run(main())
'''

source = 'PASSWORD = ' + repr(password) + '\nSERVER_IP = ' + repr(settings['SERVER_IP']) + '\nCHECK = ' + repr(args.check) + '\n'
source += 'VOICE = '+repr(args.voice or args.check_voice)+'\nCHECK_VOICE = '+repr(args.check_voice)+'\n'
source += 'VOICE_LANGUAGE = '+repr(settings.get('VOICE_LANGUAGE','en'))+'\nPIPER_VOICE = '+repr(settings.get('PIPER_VOICE','en_US-lessac-high'))+'\n'
source += 'WHISPER_HOST = '+repr(settings.get('WHISPER_HOST','172.22.0.2'))+'\nPIPER_HOST = '+repr(settings.get('PIPER_HOST','172.22.0.3'))+'\n'
source += (repo/'scripts/voice-worker.py').read_text()+'\n'+worker
result = subprocess.run(['docker', 'exec', '-i', 'homeassistant', 'python3', '-'],
                        input=source, text=True, capture_output=True)
for line in result.stdout.splitlines():
    if line.startswith(('PASS:', 'VOICE CHECK:')):
        print(line)
if result.returncode:
    raise SystemExit('Codex Home setup/check failed. Check service health, integration and owner login; no credentials printed.')
