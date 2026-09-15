#!/usr/bin/env python3
"""Run on the server: provision private Codex auth and authenticated ingest.lan."""
from pathlib import Path
import shutil
import subprocess

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
creative = Path(settings['CREATIVE_ROOT'])
(creative / '.footage-ingest').mkdir(mode=0o750, exist_ok=True)
auth = Path(settings['HOME_SERVER_SECRETS_DIR']) / 'footage-codex-auth'
auth.mkdir(mode=0o700, exist_ok=True)
if not (auth / 'auth.json').exists():
    shutil.copyfile(Path.home() / '.codex/auth.json', auth / 'auth.json')
(auth / 'auth.json').chmod(0o600)
# Existing login is reused without displaying or persisting the plaintext password.
password = (Path(settings['HOME_SERVER_SECRETS_DIR']) / 'creative_password').read_bytes().rstrip(b'\n')
hashed = subprocess.run(['openssl', 'passwd', '-6', '-stdin'], input=password+b'\n', capture_output=True, check=True).stdout.strip()
del password
base = '/data/nginx/custom/home-server/'
subprocess.run(['docker', 'exec', 'npm', 'mkdir', '-p', base], check=True)

def read(name):
    result = subprocess.run(['docker', 'exec', 'npm', 'cat', base+name], capture_output=True)
    return result.stdout if result.returncode == 0 else None

def write(name, data):
    subprocess.run(['docker', 'exec', '-i', 'npm', 'sh', '-c',
        'cat > "$1.tmp" && chmod 644 "$1.tmp" && mv "$1.tmp" "$1"', 'sh', base+name], input=data, check=True)

previous = read('footage.conf')
write('footage.htpasswd', b'egouda:' + hashed + b'\n')
write('footage.conf', (repo / 'config/nginx/footage.conf.template').read_bytes())
check = subprocess.run(['docker', 'exec', 'npm', 'nginx', '-t'], capture_output=True)
if check.returncode:
    if previous is not None:
        write('footage.conf', previous)
    else:
        subprocess.run(['docker', 'exec', 'npm', 'rm', '-f', base+'footage.conf'], check=True)
    raise SystemExit('Nginx validation failed; previous footage route restored.')
subprocess.run(['docker', 'exec', 'npm', 'nginx', '-s', 'reload'], check=True)
print('Private Codex auth and authenticated ingest.lan route configured.')
