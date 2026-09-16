#!/usr/bin/env python3
"""Save and read-verify owner secrets in 1Password before staging them over SSH.

Only touches items tagged HomeServer. No secret is passed in a command argument.
Does not change application passwords; application migration is a separate step.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess

VAULT = '5p4vew3tptjibqhwx6ubo64jyy'  # Owner-authorized personal Employee vault.
SERVICES = {
    'jellyfin': ['https://jellyfin.home.egouda.xyz', 'https://requests.home.egouda.xyz'],
    'homarr': ['https://home.egouda.xyz'],
    'torrents': ['https://torrents.home.egouda.xyz'],
    'sonarr': ['https://sonarr.home.egouda.xyz'],
    'radarr': ['https://radarr.home.egouda.xyz'],
    'prowlarr': ['https://prowlarr.home.egouda.xyz'],
    'draw': ['https://draw.home.egouda.xyz'],
    'life': ['https://life.home.egouda.xyz'],
    'ingest': ['https://ingest.home.egouda.xyz'],
    'ods': ['https://ods.home.egouda.xyz'],
    'metrics': ['https://metrics.home.egouda.xyz'],
}

def op(*args, payload=None):
    r = subprocess.run(['op', *args, '--format=json'], input=None if payload is None else json.dumps(payload), text=True, capture_output=True)
    if r.returncode:
        raise SystemExit('1Password operation failed; no application password changed.')
    return json.loads(r.stdout)

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service');parser.add_argument('--url',action='append')
    args=parser.parse_args()
    selected=SERVICES
    if args.service:
        import re
        assert re.fullmatch('[a-z0-9-]+',args.service),'Use a lowercase service slug'
        assert args.url,'Provide at least one --url'
        selected={args.service:args.url}
    existing = op('item', 'list', '--vault', VAULT, '--tags', 'HomeServer')
    by_title = {i['title']: i['id'] for i in existing}
    staged, manifest = {}, {}
    for name, urls in selected.items():
        title = 'Home Server — ' + name
        if title in by_title:
            item = op('item', 'get', by_title[title], '--vault', VAULT)
        else:
            value = secrets.token_urlsafe(30)
            item = op('item', 'create', '--vault', VAULT, payload={
                'title': title, 'category': 'LOGIN', 'tags': ['HomeServer'],
                'urls': [{'href': u, 'primary': i == 0} for i, u in enumerate(urls)],
                'fields': [{'id': 'username', 'type': 'STRING', 'purpose': 'USERNAME', 'value': 'egouda'},
                           {'id': 'password', 'type': 'CONCEALED', 'purpose': 'PASSWORD', 'value': value}]})
        verified = op('item', 'get', item['id'], '--vault', VAULT)
        password = next(f['value'] for f in verified['fields'] if f.get('purpose') == 'PASSWORD')
        assert len(password) >= 24
        staged[name] = password
        manifest[name] = {'vault': VAULT, 'item': item['id'], 'urls': urls}
        references=Path(__file__).resolve().parents[1]/'config/1password'
        references.mkdir(parents=True,exist_ok=True)
        catalog_file=references/'catalog.json'
        catalog=json.loads(catalog_file.read_text()) if catalog_file.exists() else {'account':'colab-software.1password.com','vault':'Employee','tag':'HomeServer','items':{}}
        ref='op://'+VAULT+'/'+item['id']+'/password'
        catalog['items'][name]={'title':title,'password_ref':ref,'urls':urls}
        catalog_file.write_text(json.dumps(catalog,indent=2)+'\n')
        (references/(name+'.refs')).write_text('HOME_SERVICE_USERNAME=egouda\nHOME_SERVICE_PASSWORD='+ref+'\n')
        print('Saved and read-verified:', name, flush=True)
    worker = '''import json,sys,os
from pathlib import Path
os.umask(0o077)
p=Path.home()/'.config/home-server/secrets/pending-service-passwords.json'
old=json.loads(p.read_text()) if p.exists() else {}
old.update(json.load(sys.stdin))
p.write_text(json.dumps(old))
p.chmod(0o600)
'''
    subprocess.run(['ssh', 'home-server', 'python3', '-c', __import__('shlex').quote(worker)], input=json.dumps(staged), text=True, check=True)
    dest = Path.home()/'.local/state/home-server-maintenance/security-20260916'
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    index=dest/'1password-items.json'
    saved=json.loads(index.read_text()) if index.exists() else {}
    saved.update(manifest)
    index.write_text(json.dumps(saved,indent=2)+'\n')
    print('Passwords staged privately; applications have not been changed.')

if __name__ == '__main__': main()
