#!/usr/bin/env python3
"""Add private HTTPS aliases to existing routes; preserve .lan configuration."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import shlex
import sqlite3
import subprocess
from urllib.parse import urlsplit, urlunsplit

DOMAIN = 'home.egouda.xyz'
ROOT = Path('/mnt/server/npm/data/nginx')
CUSTOM = ROOT / 'custom/home-server'
TARGET = CUSTOM / 'household-https.conf'

def hostname(old):
    assert old.endswith('.lan')
    return DOMAIN if old == 'home.lan' else old[:-4].replace('.', '-') + '.' + DOMAIN

def translate(text):
    return re.sub(r'(?:(http|ws)://)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.lan)\b',
                  lambda m: ({'http':'https://','ws':'wss://',None:''}[m[1]] + hostname(m[2])), text)

def write(data):
    dest = '/data/nginx/custom/home-server/household-https.conf'
    command = 'cat > ' + shlex.quote(dest + '.pending') + ' && chmod 644 ' + shlex.quote(dest + '.pending') + ' && mv ' + shlex.quote(dest + '.pending') + ' ' + shlex.quote(dest)
    subprocess.run(['docker','exec','-i','npm','sh','-c',command],input=data,check=True)

def main():
    os.umask(0o077)
    backup = Path.home()/'.local/state/home-server-maintenance/household-https'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    original = TARGET.read_bytes() if TARGET.exists() else b''
    (backup/'household-https.conf').write_bytes(original)
    sources = sorted((ROOT/'proxy_host').glob('*.conf')) + [CUSTOM/name for name in ['creative-home.conf','footage.conf','life-dashboard.conf','design-dns.conf','ods.conf']]
    rendered, hosts = [], set()
    for index, source in enumerate(sources):
        if not source.exists():
            continue
        text = source.read_text()
        names = re.findall(r'server_name\s+([^;]+);',text)
        if not names or any(not name.strip().endswith('.lan') for name in names):
            continue
        for name in names:
            for old in name.split(): hosts.add(hostname(old))
        # NPM repeats its shared HSTS map; retain only its server definition.
        if source.parent.name == 'proxy_host':
            text = text[text.index('server {'):]
        # Maps are global. Keep NPM's per-server variables used by proxy.conf.
        custom_vars = set(re.findall(r'\bmap\s+[^\n]+\s+\$(\w+)\s*\{',text))
        for variable in sorted(custom_vars,key=len,reverse=True):
            text = re.sub(r'\$'+variable+r'\b','$household_'+str(index)+'_'+variable,text)
        text = translate(text)
        # These existing UIs advertise legacy links in HTML/API responses. Adapt
        # only their HTTPS presentation, preserving the .lan clients and data.
        links = {old:hostname(old) for old in ['files.lan','life.lan']}
        if source.name == 'ods.conf':
            links = {old:hostname(old) for old in re.findall(r'server_name\s+([a-z0-9.-]+\.lan);',source.read_text())}
        if source.name in ['footage.conf','ods.conf']:
            filters = 'proxy_set_header Accept-Encoding "";\n        sub_filter_once off;\n'
            if source.name == 'ods.conf': filters += '        sub_filter_types application/json;\n'
            filters += ''.join('        sub_filter "http://'+old+'" "https://'+new+'";\n' for old,new in links.items())
            anchor = 'set $footage_backend' if source.name == 'footage.conf' else 'set $ods_backend'
            text = text.replace(anchor, filters + '        ' + anchor)
        text = re.sub(r'listen\s+(?:\[::\]:)?80;', 'listen 443 ssl;', text)
        # Avoid two identical listen directives from NPM's IPv4/IPv6 pair.
        text = text.replace('listen 443 ssl;\nlisten 443 ssl;', 'listen 443 ssl;')
        text = text.replace('server {','server {\n    ssl_certificate /etc/letsencrypt/live/household/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/household/privkey.pem;\n    ssl_protocols TLSv1.2 TLSv1.3;')
        rendered.append(text)
    assert DOMAIN in hosts and 'draw.'+DOMAIN in hosts
    redirects = 'server {\n listen 80;\n server_name ' + ' '.join(sorted(hosts)) + ';\n return 308 https://$host$request_uri;\n}\n'
    try:
        write(('\n'.join(rendered)+'\n'+redirects).encode())
        subprocess.run(['docker','exec','npm','nginx','-t'],capture_output=True,check=True)
    except Exception:
        write(original)
        raise SystemExit('HTTPS configuration validation failed; previous file restored.')
    subprocess.run(['docker','exec','npm','nginx','-s','reload'],capture_output=True,check=True)
    database = Path('/mnt/server/homarr/appdata/db/db.sqlite')
    with sqlite3.connect(database) as db:
        with sqlite3.connect(backup/'homarr.sqlite') as saved: db.backup(saved)
        db.execute('BEGIN IMMEDIATE')
        changed = 0
        for ident, href in db.execute('SELECT id,href FROM app').fetchall():
            if not href: continue
            parsed = urlsplit(href)
            if parsed.hostname and parsed.hostname.endswith('.lan') and hostname(parsed.hostname) in hosts:
                updated = urlunsplit(('https',hostname(parsed.hostname),parsed.path,parsed.query,parsed.fragment))
                db.execute('UPDATE app SET href=? WHERE id=?',(updated,ident)); changed += 1
    (backup/'hosts.json').write_text(json.dumps(sorted(hosts)))
    print(f'Validated {len(hosts)} HTTPS routes; updated {changed} dashboard links. Backup: {backup}')

if __name__ == '__main__':
    main()
