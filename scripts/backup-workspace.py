#!/usr/bin/env python3
"""Consistent private Workspace snapshot with SQLite restore verification."""
from pathlib import Path
import json,os,shutil,sqlite3,subprocess,tarfile,tempfile,time
DATA=Path('/srv/mergerfs/ssd/shared-workspace')
PRIVATE=Path.home()/'.config/home-server/secrets/workspace'
DEST=Path.home()/'.local/state/home-server-workspace-backups'

def main():
    assert Path('/srv/mergerfs/ssd').is_mount(),'Workspace SSD is not mounted'
    os.umask(0o077);DEST.mkdir(parents=True,exist_ok=True,mode=0o700)
    size=sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file() and not p.is_symlink())
    assert shutil.disk_usage(DEST).free>size*2+1024**3,'Insufficient snapshot space'
    archive=DEST/(time.strftime('%Y%m%dT%H%M%S')+'.tar')
    subprocess.run(['systemctl','--user','stop','home-workspace-worker.service'],check=True)
    containers=['shared-workspace','workspace-paperless']
    try:
        subprocess.run(['docker','stop','--time','30',*containers],capture_output=True,check=True)
        with tarfile.open(archive,'w') as tar:
            tar.add(DATA,arcname='data',recursive=True)
            tar.add(PRIVATE,arcname='private',recursive=True)
        with tempfile.TemporaryDirectory(dir=DEST) as directory:
            with tarfile.open(archive) as tar:
                for name in ['data/app/workspace.sqlite3','data/paperless/data/db.sqlite3']:
                    member=tar.extractfile(name)
                    target=Path(directory)/Path(name).name
                    target.write_bytes(member.read())
                    # Frozen source WAL files must be restored alongside the DB.
                    for suffix in ['-wal','-shm']:
                        try:part=tar.extractfile(name+suffix)
                        except KeyError:continue
                        target.with_name(target.name+suffix).write_bytes(part.read())
                    with sqlite3.connect(target) as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        archive.chmod(0o600)
    finally:
        subprocess.run(['docker','start',*containers],capture_output=True,check=True)
        subprocess.run(['systemctl','--user','start','home-workspace-worker.service'],check=True)
    metrics=Path.home()/'.local/state/home-server-metrics/workspace-backup.prom'
    temp=metrics.with_suffix('.pending');temp.write_text('home_workspace_backup_last_success_seconds '+str(time.time())+'\n');temp.chmod(0o644);temp.replace(metrics)
    print('Private Workspace snapshot restored and verified:',archive)
if __name__=='__main__':main()
