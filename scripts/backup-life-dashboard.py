#!/usr/bin/env python3
"""Private, consistent cold backup; always restart the previously running services."""
from datetime import datetime, timezone
from pathlib import Path
import json
import fcntl
import os
import subprocess
import sqlite3
import tarfile

repo = Path(__file__).resolve().parents[1]
os.umask(0o077)
settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
root=Path(settings['LIFE_DASHBOARD_DATA'])
backups=root/'backups'; backups.mkdir(mode=0o700,exist_ok=True)
lock = (backups/'.backup.lock').open('a')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('A Life Dashboard backup is already running.')
name='life-dashboard-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
temporary=backups/(name+'.partial'); final=backups/(name+'.tar.gz')
compose=['docker','compose','--project-directory',str(repo),'--env-file',str(repo/'server.conf'),'--env-file',str(repo/'.env')]
services=['life-dashboard','life-dashboard-sync','life-dashboard-health']
running=subprocess.check_output(compose+['ps','--status','running','--services'],text=True).splitlines()
restart=[name for name in services if name in running]
try:
    if restart: subprocess.run(compose+['stop',*restart],check=True)
    snapshot=backups/(name+'.sqlite')
    with sqlite3.connect(root/'data/finances.sqlite') as source, sqlite3.connect(snapshot) as target:
        source.backup(target)
        assert target.execute('pragma quick_check').fetchone()[0]=='ok'
    def include(info):
        parts=Path(info.name).parts
        if info.name == 'data/finances.sqlite' or info.name.startswith('data/backups/') or info.name.startswith('data/runtime/'):
            return None
        if parts[-1].endswith(('-shm','-wal')) or any(part.startswith('.document-sync-') for part in parts):
            return None
        return info
    with tarfile.open(temporary,'w:gz',compresslevel=1) as archive:
        for folder in ('docs','data','generated','codex'):
            archive.add(root/folder,arcname=folder,filter=include)
        archive.add(snapshot,arcname='data/finances.sqlite')
        archive.add(Path(settings['LIFE_DASHBOARD_REPO'])/'config',arcname='config')
        archive.add(Path(settings['HOME_SERVER_SECRETS_DIR'])/'life-dashboard-health',arcname='health-secrets')
    temporary.chmod(0o600)
    with tarfile.open(temporary) as archive:
        assert 'data/finances.sqlite' in archive.getnames()
    temporary.rename(final)
    metadata={'created_at':name,'app_commit':subprocess.check_output(['git','-C',settings['LIFE_DASHBOARD_REPO'],'rev-parse','HEAD'],text=True).strip(),
              'infra_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()}
    final.with_suffix('.json').write_text(json.dumps(metadata,indent=2))
    for old in sorted(backups.glob('life-dashboard-*.tar.gz'))[:-7]:
        old.unlink(); old.with_suffix('.json').unlink(missing_ok=True)
    print('Private Life Dashboard backup created:',final)
finally:
    if restart: subprocess.run(compose+['start',*restart],check=True)
    if 'snapshot' in globals(): snapshot.unlink(missing_ok=True)
