#!/usr/bin/env python3
"""Reconcile only the repo-owned NPM custom routes, then validate and reload."""
from pathlib import Path
import shlex
import subprocess

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
root = Path('/data/nginx/custom')
routes = root / 'home-server'
subprocess.run(['docker', 'exec', 'npm', 'mkdir', '-p', str(routes)], check=True)
target = routes / 'creative-home.conf'
hook = root / 'http_top.conf'
def read(path):
    result = subprocess.run(['docker', 'exec', 'npm', 'sh', '-c',
                             'test -f ' + shlex.quote(str(path)) + ' && cat ' + shlex.quote(str(path))], capture_output=True)
    if result.returncode not in [0, 1]:
        raise RuntimeError('Unable to read NPM custom configuration.')
    return result.stdout if result.returncode == 0 else None
original_target = read(target)
original_hook = read(hook)
include = b'include /data/nginx/custom/home-server/*.conf;\n'
text = (repo / 'config/nginx/creative-home.conf.template').read_text()
text = text.replace('@@SERVER_IP@@', settings['SERVER_IP'])
def atomic(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    command = 'cat > ' + shlex.quote(str(temp)) + ' && chmod 644 ' + shlex.quote(str(temp)) + ' && mv ' + shlex.quote(str(temp)) + ' ' + shlex.quote(str(path))
    subprocess.run(['docker', 'exec', '-i', 'npm', 'sh', '-c', command], input=data, check=True)
try:
    atomic(target, text.encode())
    if include not in (original_hook or b''):
        atomic(hook, (original_hook or b'') + b'\n# Managed home-server routes\n' + include)
    subprocess.run(['docker', 'exec', 'npm', 'nginx', '-t'], check=True)
except Exception:
    for path, original in [(target, original_target), (hook, original_hook)]:
        if original is None:
            subprocess.run(['docker', 'exec', 'npm', 'rm', '-f', str(path)], check=True)
        else:
            atomic(path, original)
    raise
subprocess.run(['docker', 'exec', 'npm', 'nginx', '-s', 'reload'], check=True)
print('Reconciled files.lan and assistant.lan.')
