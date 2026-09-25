#!/usr/bin/env python3
"""Host-side bounded gVisor job runner. Never mounts the Docker socket into apps."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

ROOT=Path('/srv/mergerfs/ssd/shared-workspace/jobs')
POLICY=Path(__file__).resolve().parents[1]/'config/identities.json'
DATABASE=Path('/srv/mergerfs/ssd/shared-workspace/app/workspace.sqlite3')
IMAGE='home-server/workspace-sandbox:1'

def allowed(actor):
    user=json.loads(POLICY.read_text())['users'].get(actor['username'])
    if not user or not (user.get('owner') or 'workspace' in user.get('services',[])):return False
    if actor.get('key_id'):
        import sqlite3
        with sqlite3.connect(DATABASE) as c:
            row=c.execute('SELECT 1 FROM keys WHERE id=? AND username=? AND scope=? AND revoked=0 AND expires>?',(actor['key_id'],actor['username'],'write',int(time.time()))).fetchone()
        return bool(row)
    return not actor.get('machine')

def write(path,value):
    tmp=path.with_suffix('.pending')
    tmp.write_text(json.dumps(value));tmp.chmod(0o600);tmp.replace(path)

def execute(dest):
    pending=dest/'pending.json'
    try:pending.rename(dest/'running.json')
    except FileNotFoundError:return
    metadata=json.loads((dest/'running.json').read_text())
    name='workspace-job-'+dest.name
    started=time.monotonic();result={**metadata,'status':'failed'}
    proc=None
    try:
        if not allowed(metadata['actor']):raise RuntimeError('Submitting identity or key no longer has write access')
        inputs=dest/'inputs'
        if inputs.is_symlink() or inputs.resolve()!=dest.resolve()/'inputs':raise RuntimeError('Invalid input directory')
        if any(p.is_symlink() or not p.is_file() for p in inputs.iterdir()):raise RuntimeError('Invalid input file')
        if hashlib.sha256((inputs/'script.py').read_bytes()).hexdigest()!=metadata['script_sha256']:raise RuntimeError('Script integrity mismatch')
        # Mount only this run's immutable input files. No writable host mounts.
        cmd=['docker','run','--name',name,'--runtime=runsc','--network=none','--read-only',
             '--user=65532:65532','--cap-drop=ALL','--security-opt=no-new-privileges:true',
             '--memory=512m','--memory-swap=512m','--cpus=1','--pids-limit=64',
             '--ulimit','nofile=128:128','--ulimit','fsize=16777216:16777216',
             '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777',
             '--mount','type=bind,src='+str(inputs)+',dst=/inputs,readonly',
             '--log-driver=none',IMAGE]
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        sel=selectors.DefaultSelector()
        for stream in (proc.stdout,proc.stderr):os.set_blocking(stream.fileno(),False);sel.register(stream,selectors.EVENT_READ)
        output={proc.stdout:bytearray(),proc.stderr:bytearray()}
        while sel.get_map():
            if time.monotonic()-started>60:raise RuntimeError('Script exceeded 60 seconds')
            if not allowed(metadata['actor']):raise RuntimeError('Access revoked while script was running')
            for key,_ in sel.select(.25):
                chunk=os.read(key.fileobj.fileno(),65536)
                if not chunk:sel.unregister(key.fileobj);continue
                output[key.fileobj].extend(chunk)
                if len(output[key.fileobj])>(2*1024*1024 if key.fileobj is proc.stdout else 128*1024):raise RuntimeError('Script output limit exceeded')
        code=proc.wait(timeout=3)
        result['stderr']=output[proc.stderr].decode('utf-8',errors='replace')
        if code:raise RuntimeError('Script exited with code '+str(code))
        try:result['result']=json.loads(output[proc.stdout])
        except (ValueError,UnicodeDecodeError):raise RuntimeError('Script must print one valid JSON result')
        result['status']='succeeded'
    except Exception as exc:
        result['error']=str(exc)
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
        if proc and proc.poll() is None:proc.kill();proc.wait()
        result['duration_seconds']=round(time.monotonic()-started,3)
        write(dest/'result.json',result)
        (dest/'running.json').unlink(missing_ok=True)
        # Remove ephemeral copies, retain script + manifest for reproducibility.
        # Files remain backed by Paperless or versioned records.
        inputs=dest/'inputs'
        if inputs.exists():
            inputs.chmod(0o700)
            for p in inputs.iterdir():
                if p.name not in ('script.py','manifest.json'):p.unlink()
        import sqlite3
        with sqlite3.connect(DATABASE,timeout=20) as c:
            c.execute('INSERT INTO audit(timestamp,actor,key_id,action,object_id,snapshot) VALUES(?,?,?,?,?,?)',
                      (int(time.time()),metadata['actor']['username'],metadata['actor'].get('key_id'),'job.'+result['status'],dest.name,None))

def main():
    os.umask(0o077)
    if not Path('/srv/mergerfs/ssd').is_mount():raise RuntimeError('Workspace SSD is not mounted')
    ROOT.mkdir(parents=True,exist_ok=True)
    with open(ROOT/'.worker.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # A service restart never reruns a script whose outcome is uncertain.
        for p in ROOT.glob('*/running.json'):
            name='workspace-job-'+p.parent.name
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
            value=json.loads(p.read_text());write(p.parent/'result.json',{**value,'status':'failed','error':'Worker restarted; run interrupted. Submit a new job.'});p.unlink()
        while True:
            if not Path('/srv/mergerfs/ssd').is_mount():raise RuntimeError('Workspace SSD is not mounted')
            for p in sorted(ROOT.glob('*/pending.json')):
                if re.fullmatch('[a-f0-9]{32}',p.parent.name):execute(p.parent)
            time.sleep(1)
if __name__=='__main__':main()
