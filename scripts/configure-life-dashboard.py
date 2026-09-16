#!/usr/bin/env python3
"""Provision private dashboard auth and reconcile its NPM route on the server."""
from pathlib import Path
from auth_policy import protect_if_enabled
from service_credentials import service_password
import shutil
import subprocess

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
root = Path(settings['LIFE_DASHBOARD_DATA'])
if not (root/'data/finances.sqlite').is_file():
    raise SystemExit('Migrate a verified SQLite snapshot before configuring the dashboard.')
auth = root/'codex'
auth.mkdir(mode=0o700, exist_ok=True)
if not (auth/'auth.json').exists():
    shutil.copyfile(Path.home()/'.codex/auth.json', auth/'auth.json')
(auth/'auth.json').chmod(0o600)
password = service_password('life').encode()
hashed = subprocess.run(['openssl','passwd','-6','-stdin'],input=password+b'\n',capture_output=True,check=True).stdout.strip()
del password
base = '/data/nginx/custom/home-server/'
subprocess.run(['docker','exec','npm','mkdir','-p',base], check=True)
def read(name):
    r=subprocess.run(['docker','exec','npm','cat',base+name],capture_output=True)
    return r.stdout if r.returncode == 0 else None
def write(name,data):
    subprocess.run(['docker','exec','-i','npm','sh','-c',
        'cat > "$1.tmp" && chmod 644 "$1.tmp" && mv "$1.tmp" "$1"','sh',base+name],input=data,check=True)
previous = read('life-dashboard.conf')
write('life-dashboard.htpasswd', b'egouda:'+hashed+b'\n')
write('life-dashboard.conf', protect_if_enabled((repo/'config/nginx/life-dashboard.conf.template').read_bytes()))
check = subprocess.run(['docker','exec','npm','nginx','-t'], capture_output=True)
if check.returncode:
    if previous is not None: write('life-dashboard.conf',previous)
    else: subprocess.run(['docker','exec','npm','rm','-f',base+'life-dashboard.conf'],check=True)
    raise SystemExit('Nginx validation failed; previous route restored.')
subprocess.run(['docker','exec','npm','nginx','-s','reload'],check=True)
print('Life Dashboard private authentication and life.lan route configured.')
