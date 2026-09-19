#!/usr/bin/env python3
"""Apply catalog authentication policies transactionally, with private rollback."""
import base64
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import time
from auth_policy import render,services,ROOT

NGINX=Path('/mnt/server/npm/data/nginx')

def read(path):
    target='/data/nginx/'+str(path.relative_to(NGINX))
    r=subprocess.run(['docker','exec','npm','cat',target],capture_output=True)
    if r.returncode:raise RuntimeError('Unable to read proxy configuration')
    return r.stdout

def write(path, data):
    # All file names are generated constants; secret content travels over stdin.
    target='/data/nginx/'+str(path.relative_to(NGINX))
    secret_include=path.name in ('nzbget.conf','qbittorrent.conf')
    r=subprocess.run(['docker','exec','-i','npm','sh','-c','mkdir -p "$(dirname "$1")" && cat > "$1.pending" && chmod "$2" "$1.pending" && mv "$1.pending" "$1"','sh',target,'600' if secret_include else '644'],input=data,capture_output=True)
    if r.returncode:raise RuntimeError('Unable to write proxy configuration')

def main():
    os.umask(0o077)
    policies=services()
    backup=Path.home()/'.local/state/home-server-maintenance/auth'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True,mode=0o700)
    files=sorted((NGINX/'proxy_host').glob('*.conf'))+sorted((NGINX/'custom/home-server').glob('*.conf'))
    proposed={};covered=set()
    for file in files:
        raw=read(file).decode();updated,hosts=render(raw,policies);covered.update(hosts)
        if updated!=raw:proposed[file]=updated.encode()
    assert set(policies)<=covered,'Missing HTTPS route(s): '+','.join(sorted(set(policies)-covered))
    for filename,target in [('nginx-location.conf','location.conf'),('nginx-identity.conf','identity.conf')]:
        proposed[NGINX/'custom/home-auth'/target]=(ROOT/'config/auth'/filename).read_bytes()
    proposed[NGINX/'custom/home-server/auth.conf']=(ROOT/'config/auth/nginx-portal.conf').read_bytes()
    # Preserve NZBGet's native RPC credentials and never send them to the browser.
    conf={}
    for line in Path('/mnt/server/nzbget/config/nzbget.conf').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k,v=line.split('=',1);conf[k]=v
    value=base64.b64encode((conf['ControlUsername']+':'+conf['ControlPassword']).encode()).decode()
    proposed[NGINX/'custom/home-auth/nzbget.conf']=('proxy_set_header Authorization "Basic '+value+'";\nproxy_hide_header WWW-Authenticate;\n').encode()
    # qBittorrent 5.2 can shift native authentication to the identity-aware
    # reverse proxy. Keep its distinct recovery credential and inject it only
    # after Authelia has authorized the owner.
    passwords=json.loads((Path.home()/'.config/home-server/secrets/service-passwords.json').read_text())
    value=base64.b64encode(('egouda:'+passwords['torrents']).encode()).decode()
    proposed[NGINX/'custom/home-auth/qbittorrent.conf']=('proxy_set_header Authorization "Basic '+value+'";\nproxy_hide_header WWW-Authenticate;\n').encode()
    # Global guard: a future proxy missing its registered auth location fails closed.
    top=NGINX/'custom/http_top.conf'
    original_top=read(top).decode() if top.exists() else ''
    if '# home-auth-default' not in original_top:
        proposed[top]=(original_top+'\n# home-auth-default\nauth_request /internal/authelia/authz;\n').encode()
    originals={p:read(p) if p.exists() else None for p in proposed}
    for p,data in originals.items():
        dest=backup/p.relative_to(NGINX);dest.parent.mkdir(parents=True,exist_ok=True)
        if data is not None:dest.write_bytes(data)
    (backup/'manifest.json').write_text(json.dumps({str(p):v is not None for p,v in originals.items()}))
    try:
        for p,data in proposed.items():write(p,data)
        result=subprocess.run(['docker','exec','npm','nginx','-t'],capture_output=True)
        if result.returncode:
            (backup/'validation.log').write_bytes(result.stdout+result.stderr)
            raise RuntimeError('Nginx validation failed; details retained privately')
        subprocess.run(['docker','exec','npm','nginx','-s','reload'],capture_output=True,check=True)
        time.sleep(3)
        result=subprocess.run(['python3',str(ROOT/'scripts/check-auth.py'),'--staged'],capture_output=True)
        (backup/'checks.log').write_bytes(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Authentication checks failed; restoring previous proxy configuration')
    except Exception:
        for p,data in originals.items():
            if data is not None:write(p,data)
            else:subprocess.run(['docker','exec','npm','rm','-f','/data/nginx/'+str(p.relative_to(NGINX))],capture_output=True,check=True)
        subprocess.run(['docker','exec','npm','nginx','-s','reload'],capture_output=True)
        raise
    private=Path.home()/'.config/home-server/secrets'
    applied=private/'service-passwords.json'
    saved=json.loads(applied.read_text())
    saved['auth']=json.loads((private/'pending-service-passwords.json').read_text())['auth']
    applied.write_text(json.dumps(saved));applied.chmod(0o600)
    print('Applied central auth to',len(covered),'HTTPS apps; private rollback:',backup)

if __name__=='__main__':main()
