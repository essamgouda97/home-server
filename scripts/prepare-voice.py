#!/usr/bin/env python3
"""Download voice models before starting isolated speech services (server only).

Temporary bootstrap containers have outbound access and no published ports.
Runtime containers use cached models on an internal network without internet.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
compose = ['docker','compose','--env-file','server.conf','--env-file','.env']
settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
# Compose output can include private environment values: parse in memory only.
config = json.loads(subprocess.check_output(compose+['config','--format','json'], cwd=repo))
for service in ['piper', 'whisper']:
    spec = config['services'][service]
    data = Path(next(v['source'] for v in spec['volumes'] if v['target']=='/data'))
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    data.chmod(0o700)
    name = 'home-voice-bootstrap-'+service
    command = [x for x in spec['command'] if x != '--local-files-only']
    subprocess.run(['docker','pull',spec['image']], check=True, stdout=subprocess.DEVNULL)
    # Never mount runtime credentials or Home Assistant state in the downloader.
    subprocess.run(['docker','run','--detach','--rm','--name',name,'--init',
                    '--user','1000:1000','--read-only','--cap-drop','ALL',
                    '--security-opt','no-new-privileges:true',
                    '--tmpfs','/tmp:rw,nosuid,nodev,size=256m,mode=1777',
                    '--env','HOME=/tmp','--volume',str(data)+':/data',
                    spec['image'],*command], check=True, stdout=subprocess.DEVNULL)
    try:
        print('Preparing '+service+' model cache...', flush=True)
        for attempt in range(240):
            state = json.loads(subprocess.check_output(['docker','inspect',name]))[0]['State']
            if state.get('Health',{}).get('Status') == 'healthy':
                break
            if not state['Running']:
                raise RuntimeError(service+' model initialization stopped')
            time.sleep(2)
        else:
            raise RuntimeError(service+' model initialization timed out')
    finally:
        subprocess.run(['docker','stop','-t','10',name], stdout=subprocess.DEVNULL, check=True)
    manifest = {}
    for path in sorted(data.rglob('*')):
        if path.is_file() and path.name != 'model-manifest.json':
            with path.open('rb') as source:
                digest = hashlib.sha256()
                while chunk := source.read(1024*1024):
                    digest.update(chunk)
            manifest[str(path.relative_to(data))] = digest.hexdigest()
    (data/'model-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS: '+service+' cached model files fingerprinted.', flush=True)
