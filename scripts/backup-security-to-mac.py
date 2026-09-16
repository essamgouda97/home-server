#!/usr/bin/env python3
"""Pull a consistent recovery archive into encrypted restic storage on this Mac."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

HOME=Path.home()
REPO=HOME/'Library/Application Support/HomeServer/EncryptedBackups'
KEY=HOME/'.config/home-server/backup-password'
RESTIC=shutil.which('restic') or '/opt/homebrew/bin/restic'

def main():
 os.umask(0o077)
 assert shutil.disk_usage(HOME).free > 1536*1024**2,'Mac has less than 1.5 GiB free; backup deferred to preserve disk space'
 assert KEY.is_file(),'Escrow backup encryption password in 1Password first'
 REPO.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 env={**os.environ,'RESTIC_REPOSITORY':str(REPO),'RESTIC_PASSWORD_FILE':str(KEY)}
 if not (REPO/'config').exists():subprocess.run([RESTIC,'init'],env=env,check=True,capture_output=True)
 worker="""from pathlib import Path
import subprocess
pw=(Path.home()/'.config/home-server/secrets/creative_password').read_text().strip()+'\\n'
r=subprocess.run(['sudo','-S','-p','','python3',str(Path.home()/'workspace/home-server/scripts/snapshot-security-state.py')],input=pw,text=True,capture_output=True)
if r.returncode:raise SystemExit('Server snapshot failed; no backup claimed')
print(r.stdout.strip())
"""
 import shlex
 result=subprocess.run(['ssh','-o','BatchMode=yes','home-server','python3','-c',shlex.quote(worker)],text=True,capture_output=True,check=True)
 source=result.stdout.strip();assert source.startswith('/home/egouda/.local/state/home-server-security-backups/') and source.endswith('.tar')
 transfer=subprocess.Popen(['ssh','home-server','cat',source],stdout=subprocess.PIPE)
 try:
  saved=subprocess.run([RESTIC,'backup','--stdin','--stdin-filename','home-server-recovery.tar','--tag','home-server-config','--json'],stdin=transfer.stdout,env=env,capture_output=True,text=True)
 finally:transfer.stdout.close()
 assert transfer.wait()==0 and saved.returncode==0,'Encrypted backup failed'
 rows=[json.loads(l) for l in saved.stdout.splitlines()]
 snapshot=next(r['snapshot_id'] for r in rows if r.get('message_type')=='summary')
 subprocess.run([RESTIC,'check','--read-data'],env=env,check=True,capture_output=True)
 dump=subprocess.Popen([RESTIC,'dump',snapshot,'home-server-recovery.tar'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 restored=subprocess.run(['ssh','home-server','python3 ~/workspace/home-server/scripts/verify-security-restore.py'],stdin=dump.stdout,capture_output=True,text=True)
 dump.stdout.close()
 assert dump.wait()==0 and restored.returncode==0, 'Restore verification failed'
 print(restored.stdout.strip())
 print('Encrypted snapshot:',snapshot,'media/footage excluded.')

if __name__=='__main__':main()
