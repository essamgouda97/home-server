#!/usr/bin/env python3
"""Initialize the database once; never print a password or auth response."""
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
database = Path(settings['SERVER_DATA_DIR']) / 'filebrowser/filebrowser.db'
if database.exists():
    print('File Browser database already exists; preserving users and settings.')
    raise SystemExit(0)
password = (Path(settings['HOME_SERVER_SECRETS_DIR']) / 'creative_password').read_text()
assert len(password) >= 12 and '\n' not in password
base = ['docker', 'compose', '--env-file', 'server.conf', '--env-file', '.env',
        'run', '--rm', '--no-deps', 'filebrowser']
subprocess.run(base + ['--config', '/config/settings.json', 'config', 'init',
                      '--branding.name', 'Creative Drive', '--disableExec',
                      '--perm.execute=false', '--perm.share=false'], cwd=repo, check=True)
# File Browser's documented account CLI takes the password as an argument.
# Capture all output to avoid exposing account data in deployment logs.
result = subprocess.run(base + ['--config', '/config/settings.json', 'users', 'add',
                               'egouda', password, '--perm.admin', '--perm.execute=false',
                               '--perm.share=false'], cwd=repo, capture_output=True)
del password
if result.returncode:
    raise SystemExit('File Browser account initialization failed; inspect locally without printing credentials.')
print('Creative Drive account initialized: egouda.')
