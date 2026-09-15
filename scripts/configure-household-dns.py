#!/usr/bin/env python3
"""Create only missing household DNS records; refuse conflicting records.

Run on the Mac. Reads the existing literal CLOUDFLARE_API_TOKEN assignment
without sourcing shell startup files or exposing the token.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import shlex
import urllib.error
import urllib.parse
import urllib.request

def main():
    os.umask(0o077)
    match = re.search(r'^\s*(?:export\s+)?CLOUDFLARE_API_TOKEN\s*=\s*(.+)$',(Path.home()/'.zshrc').read_text(),re.M)
    if not match: raise SystemExit('Missing Cloudflare token assignment.')
    token = shlex.split(match[1],comments=True)[0]
    if '$' in token or '`' in token: raise SystemExit('Token must be a literal assignment.')
    def api(path, data=None):
        request = urllib.request.Request('https://api.cloudflare.com/client/v4'+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=30) as response: result=json.load(response)
        except urllib.error.HTTPError as error:
            raise SystemExit('Cloudflare HTTP '+str(error.code)) from None
        if not result.get('success'): raise SystemExit('Cloudflare operation failed.')
        return result['result']
    zones = api('/zones?name=egouda.xyz')
    assert len(zones)==1
    base = '/zones/'+zones[0]['id']+'/dns_records'
    backup = Path.home()/'.local/state/home-server-maintenance/cloudflare'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    created=[]
    for name in ['home.egouda.xyz','*.home.egouda.xyz']:
        current = api(base+'?'+urllib.parse.urlencode({'name':name}))
        (backup/(name.replace('*','wildcard')+'.json')).write_text(json.dumps(current))
        if current:
            assert len(current)==1 and current[0]['type']=='A' and current[0]['content']=='10.0.0.182' and not current[0]['proxied'], 'Conflicting record: '+name
        else:
            created.append(api(base,{'type':'A','name':name,'content':'10.0.0.182','ttl':120,'proxied':False,'comment':'Private household services; no public ingress'}))
            (backup/'created.json').write_text(json.dumps(created))
        print('Verified DNS-only '+name+' -> 10.0.0.182')

if __name__ == '__main__':
    main()
