#!/usr/bin/env python3
"""Prepare private Workspace data and internal service credentials on the server."""
from pathlib import Path
import os,json,secrets,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'.config/home-server/secrets'
DEST=PRIVATE/'workspace'
DATA=Path('/srv/mergerfs/ssd/shared-workspace')

def run(args,**kw):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,**kw)
    if p.returncode:raise RuntimeError('Command failed: '+args[0]+' (captured output withheld)')
    return p.stdout

def sudo(args):
    password=(PRIVATE/'creative_password').read_text().strip()+'\n'
    return run(['sudo','-S','-p','']+args,input=password.encode())

def main():
    os.umask(0o077);DEST.mkdir(parents=True,exist_ok=True);(DEST/'app').mkdir(exist_ok=True,mode=0o700)
    for directory in ['app','jobs','paperless/data','paperless/media','paperless/consume','paperless/export','broker']:
        sudo(['install','-d','-m','700','-o','1000','-g','1000',str(DATA/directory)])
    if not (DEST/'app/proxy-key').exists():(DEST/'app/proxy-key').write_text(secrets.token_hex(32))
    if not (DEST/'paperless.env').exists():(DEST/'paperless.env').write_text('PAPERLESS_SECRET_KEY='+secrets.token_urlsafe(48)+'\n')
    for p in DEST.rglob('*'):
        p.chmod(0o700 if p.is_dir() else 0o600)
    print('Workspace private directories and internal keys prepared.')

if __name__=='__main__':main()
