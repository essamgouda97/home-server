#!/usr/bin/env python3
"""Small encrypted central-auth recovery snapshot, independent of the full backup."""
import json
from pathlib import Path
import os
import shlex
import shutil
import subprocess


def main():
    os.umask(0o077)
    local=Path.home()
    assert shutil.disk_usage(local).free>256*1024**2,'Less than 256 MiB available; auth backup deferred'
    repo=local/'Library/Application Support/HomeServer/EncryptedBackups'
    key=local/'.config/home-server/backup-password'
    assert key.is_file() and (repo/'config').is_file(),'Verified encrypted backup repository required'
    env={**os.environ,'RESTIC_REPOSITORY':str(repo),'RESTIC_PASSWORD_FILE':str(key)}
    restic=shutil.which('restic') or '/opt/homebrew/bin/restic'
    worker='''import json,sys,sqlite3,tarfile,tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix='auth-recovery-') as folder:
    dest=Path(folder)
    with sqlite3.connect('file:/srv/mergerfs/ssd/authelia/db.sqlite3?mode=ro',uri=True) as source,sqlite3.connect(dest/'db.sqlite3') as target:
        source.backup(target)
        assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    with sqlite3.connect('file:/mnt/server/homarr/appdata/db/db.sqlite?mode=ro',uri=True) as source,sqlite3.connect(dest/'homarr.sqlite3') as target:
        source.backup(target)
        assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    (dest/'manifest.json').write_text(json.dumps({'scope':'central authentication and Homarr identity links','sqlite_databases':2}))
    with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
        archive.add(dest/'manifest.json',arcname='recovery/manifest.json')
        archive.add(dest/'db.sqlite3',arcname='recovery/authelia/db.sqlite3')
        archive.add(dest/'homarr.sqlite3',arcname='recovery/homarr/db.sqlite3')
        private=Path.home()/'.config/home-server/secrets/authelia'
        for name in ['configuration.yml','users.yml','jwt_secret','session_secret','storage_key','oidc.json','homarr-oidc.env','grafana-oidc.env']:
            archive.add(private/name,arcname='recovery/secrets/authelia/'+name)
        root=Path.home()/'workspace/home-server'
        for name in ['compose.auth.yml','server.conf','config/services.json','config/identities.json','scripts/oidc_config.py','scripts/identity_policy.py']:
            archive.add(root/name,arcname='recovery/infrastructure/'+name)
'''
    source=subprocess.Popen(['ssh','home-server','python3','-c',shlex.quote(worker)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        result=subprocess.run([restic,'backup','--stdin','--stdin-filename','home-auth-recovery.tar','--tag','home-auth','--json'],env=env,stdin=source.stdout,capture_output=True,text=True)
    finally:source.stdout.close()
    assert source.wait()==0 and result.returncode==0,'Auth backup failed'
    snapshot=next(json.loads(line)['snapshot_id'] for line in result.stdout.splitlines() if json.loads(line).get('message_type')=='summary')
    dump=subprocess.Popen([restic,'dump',snapshot,'home-auth-recovery.tar'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    restored=subprocess.run(['ssh','home-server','python3 ~/workspace/home-server/scripts/verify-security-restore.py'],stdin=dump.stdout,capture_output=True,text=True)
    dump.stdout.close()
    assert dump.wait()==0 and restored.returncode==0,'Auth restore verification failed'
    print(restored.stdout.strip())
    print('PASS encrypted auth snapshot and restore:',snapshot,'(central auth only; full scheduled backup is separate)')

if __name__=='__main__':main()
