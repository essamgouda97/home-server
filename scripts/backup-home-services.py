#!/usr/bin/env python3
"""Private app-state backup; briefly pauses File Browser and HA, not media."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import shutil
import sqlite3
import tarfile
import tempfile

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
data = Path(settings['SERVER_DATA_DIR'])
secrets = Path(settings['HOME_SERVER_SECRETS_DIR'])
destination = Path.home() / '.local/state/home-server-backups'
destination.mkdir(parents=True, exist_ok=True, mode=0o700)
destination.chmod(0o700)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
name = 'home-services-' + stamp + '.tar.gz'
running = []
for container in ['filebrowser', 'homeassistant']:
    result = subprocess.run(['docker', 'inspect', '--format', '{{.State.Running}}', container],
                            capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip() == 'true':
        running.append(container)
try:
    if running:
        subprocess.run(['docker', 'stop', '-t', '60', *running], check=True)
    command = ['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'sh',
               '-v', str(data / 'homeassistant') + ':/source/homeassistant:ro',
               '-v', str(data / 'filebrowser') + ':/source/filebrowser:ro',
               '-v', str(secrets) + ':/source/secrets:ro',
               '-v', str(destination) + ':/backup', 'home-server/samba:local', '-c',
               'umask 077; tar -czf /backup/"$1" -C /source homeassistant filebrowser secrets && chown 1000:1000 /backup/"$1"',
               'backup', name]
    subprocess.run(command, check=True)
finally:
    if running:
        subprocess.run(['docker', 'start', *running], check=True)
archive = destination / name
with tarfile.open(archive) as tf:
    members = tf.getnames()
    if not all(any(m.startswith(prefix) for m in members) for prefix in ['homeassistant/', 'filebrowser/', 'secrets/']):
        raise SystemExit('Archive incomplete; do not use it for recovery.')
    with tempfile.TemporaryDirectory(prefix='home-services-restore-') as tmp:
        restore = Path(tmp)
        for name in ['homeassistant/home-assistant_v2.db', 'filebrowser/filebrowser.db']:
            target = restore / Path(name).name
            with tf.extractfile(name) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
        with sqlite3.connect((restore / 'home-assistant_v2.db').as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise SystemExit('Restored Home Assistant database failed its integrity check.')
        # Exercise File Browser's real database reader against a disposable restore.
        # Account listing output is captured because it can include password hashes.
        checked = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                                  '--user', '1000:1000', '--entrypoint', '/bin/filebrowser',
                                  '-v', str(restore) + ':/restore',
                                  'filebrowser/filebrowser:v2.63.23@sha256:a469ea076d4a1b4b1d86a41d130f2f536cd9da996a2b1fb39c0d7635f9d89b9a',
                                  '--database', '/restore/filebrowser.db', 'users', 'ls'], capture_output=True)
        if checked.returncode or b'egouda' not in checked.stdout:
            raise SystemExit('Restored File Browser account database failed its check.')
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo))
metadata = archive.with_suffix('.json')
metadata.write_text(json.dumps({'created': stamp, 'git_revision': revision, 'archive': name,
                                'git_dirty': dirty,
                                'contains_secrets': True, 'contains_footage': False}, indent=2) + '\n')
metadata.chmod(0o600)
print('Private backup restore-verified (HA database and File Browser account):', archive)
print('Restore the same Git revision and private state together. Keep an independent backup copy.')
