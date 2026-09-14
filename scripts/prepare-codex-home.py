#!/usr/bin/env python3
"""Server-side private auth provisioning for the isolated Codex Home bridge."""
from pathlib import Path
import secrets
import shutil

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
root = Path(settings['HOME_SERVER_SECRETS_DIR'])
root.mkdir(parents=True,exist_ok=True,mode=0o700)
token = root/'codex_home_token'
if not token.exists():
    token.write_text(secrets.token_urlsafe(32))
token.chmod(0o600)
auth_dir = root/'codex-home-auth'
auth_dir.mkdir(exist_ok=True,mode=0o700)
auth_dir.chmod(0o700)
auth = auth_dir/'auth.json'
if not auth.exists():
    source = Path.home()/'.codex/auth.json'
    if not source.is_file():
        raise SystemExit('Sign in to Codex on the server before provisioning the bridge.')
    shutil.copyfile(source,auth)
auth.chmod(0o600)
print('Codex Home private credentials prepared; no credentials printed.')
