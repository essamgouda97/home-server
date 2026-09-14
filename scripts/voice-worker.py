"""HA-container worker loaded by configure-codex-home.py, never run on its own."""
import asyncio
import time
from urllib.parse import urlparse

async def configure_voice(request, ws_call, headers, pipeline_id):
    from homeassistant.components.conversation import HOME_ASSISTANT_AGENT
    engines = {}
    entries = await request('/api/config/config_entries/entry?domain=wyoming', headers=headers)
    for title, domain, host, port in [('Home Voice: Whisper','stt',WHISPER_HOST,10300), ('Home Voice: Piper','tts',PIPER_HOST,10200)]:
        matches = [e for e in entries if e['title'] == title]
        if len(matches) > 1:
            raise RuntimeError('Duplicate managed voice integration')
        if matches:
            entry_id = matches[0]['entry_id']
        else:
            flow = await request('/api/config/config_entries/flow', {'handler':'wyoming','show_advanced_options':False}, headers=headers)
            result = await request('/api/config/config_entries/flow/'+flow['flow_id'],
                                   {'host':host,'port':port}, headers=headers)
            if result['type'] != 'create_entry':
                raise RuntimeError('Voice integration could not connect')
            entry_id = result['result']['entry_id']
            await ws_call('config_entries/update', entry_id=entry_id, title=title)
        for attempt in range(40):
            registry = await ws_call('config/entity_registry/list')
            entity_ids = [e['entity_id'] for e in registry if e['config_entry_id'] == entry_id
                          and e['entity_id'].startswith(domain+'.') and not e['disabled_by']]
            if len(entity_ids) == 1:
                engines[domain] = entity_ids[0]
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Voice entity did not become available')
    desired = await ws_call('assist_pipeline/pipeline/get', pipeline_id=pipeline_id)
    desired.pop('id', None)
    desired.update(stt_engine=engines['stt'], stt_language=VOICE_LANGUAGE,
                   tts_engine=engines['tts'], tts_language=PIPER_VOICE.split('-')[0],
                   tts_voice=PIPER_VOICE, language=VOICE_LANGUAGE,
                   conversation_language=VOICE_LANGUAGE, prefer_local_intents=True)
    await ws_call('assist_pipeline/pipeline/update', pipeline_id=pipeline_id, **desired)
    local = dict(desired, name='Home Local', conversation_engine=HOME_ASSISTANT_AGENT,
                 conversation_language=VOICE_LANGUAGE, language=VOICE_LANGUAGE,
                 prefer_local_intents=True)
    pipelines = (await ws_call('assist_pipeline/pipeline/list'))['pipelines']
    old = next((p for p in pipelines if p['name']=='Home Local'), None)
    if old:
        await ws_call('assist_pipeline/pipeline/update', pipeline_id=old['id'], **local)
    else:
        await ws_call('assist_pipeline/pipeline/create', **local)
    print('PASS: local Whisper/Piper connected to Codex and Home Local.', flush=True)

async def synthesize_probe(text):
    from wyoming.client import AsyncTcpClient
    from wyoming.tts import Synthesize, SynthesizeVoice
    from wyoming.audio import AudioStart, AudioChunk, AudioStop
    async with AsyncTcpClient(PIPER_HOST,10200) as client:
        await client.write_event(Synthesize(text=text, voice=SynthesizeVoice(name=PIPER_VOICE)).event())
        chunks = []
        rate = None
        async with asyncio.timeout(60):
            while event := await client.read_event():
                if AudioStart.is_type(event.type):
                    start = AudioStart.from_event(event)
                    if start.width != 2 or start.channels != 1:
                        raise RuntimeError('Unexpected generated audio format')
                    rate = start.rate
                elif AudioChunk.is_type(event.type):
                    chunks.append(AudioChunk.from_event(event).audio)
                elif AudioStop.is_type(event.type):
                    break
        if not rate or not chunks:
            raise RuntimeError('Speech synthesis returned no audio')
        # Give VAD leading/trailing silence around the synthetic command.
        return rate, b'\0'*((rate//4)*2) + b''.join(chunks) + b'\0'*(rate*2)

async def check_voice(session, base, access_token, request, ws_call, headers):
    pipelines = (await ws_call('assist_pipeline/pipeline/list'))['pipelines']
    # Probe only the virtual switch. End each pipeline with it switched off.
    for name in ['Home Local','Codex']:
        pipeline = next(p for p in pipelines if p['name']==name)
        for action in (['on','off',None] if name == 'Codex' else ['on','off']):
            phrase = ('Turn '+action+' the Codex demo switch.' if action else
                      'Briefly explain why the sky is blue.')
            rate, audio = await synthesize_probe(phrase)
            started = time.monotonic()
            transcript = None
            audio_url = None
            async with session.ws_connect(base+'/api/websocket') as ws:
                await ws.receive_json()
                await ws.send_json({'type':'auth','access_token':access_token})
                if (await ws.receive_json())['type'] != 'auth_ok':
                    raise RuntimeError('Voice test authentication failed')
                await ws.send_json({'id':1,'type':'assist_pipeline/run','pipeline':pipeline['id'],
                                    'start_stage':'stt','end_stage':'tts','input':{'sample_rate':rate},'timeout':180})
                async with asyncio.timeout(200):
                    while True:
                        event = await ws.receive_json()
                        if event.get('type') == 'result':
                            if not event['success']:
                                print('VOICE CHECK: '+str(event.get('error',{})), flush=True)
                                raise RuntimeError('Voice pipeline failed to start')
                            continue
                        if event.get('type') != 'event':
                            continue
                        details = event['event']
                        kind = details['type']
                        data = details.get('data', {})
                        if kind == 'run-start':
                            channel = bytes([data['runner_data']['stt_binary_handler_id']])
                            for offset in range(0,len(audio),4096):
                                await ws.send_bytes(channel+audio[offset:offset+4096])
                            await ws.send_bytes(channel)
                        elif kind == 'stt-end':
                            transcript = data['stt_output']['text']
                        elif kind == 'intent-end':
                            if data['intent_output']['response']['response_type'] == 'error':
                                raise RuntimeError('Voice command could not be understood')
                        elif kind == 'tts-end':
                            audio_url = data['tts_output']['url']
                        elif kind == 'error':
                            raise RuntimeError('Voice pipeline error: '+data.get('code','unknown'))
                        elif kind == 'run-end':
                            break
            if not transcript or (action and action not in transcript.lower()) or not audio_url:
                raise RuntimeError('Voice transcript or reply audio missing')
            # Do not send an owner bearer token to an arbitrary returned URL.
            # HA's audio path is fetched from this known local origin.
            parsed = urlparse(audio_url)
            if not parsed.path.startswith('/api/tts_proxy/'):
                raise RuntimeError('Unexpected speech reply URL')
            url = base + parsed.path + ('?'+parsed.query if parsed.query else '')
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                reply = await response.read()
            if len(reply) < 1000:
                raise RuntimeError('Spoken reply was empty')
            if action:
                state = await request('/api/states/input_boolean.codex_demo', headers=headers)
                if state['state'] != action:
                    raise RuntimeError('Voice command did not change the virtual switch')
            outcome = 'state '+action if action else 'open-ended Codex answer'
            print('PASS: '+name+' speech → '+outcome+' → audio reply ('+
                  str(round(time.monotonic()-started,1))+' seconds).', flush=True)
