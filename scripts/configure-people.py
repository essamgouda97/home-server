#!/usr/bin/env python3
"""Install the owner-only People route and private one-use invitation path."""
from pathlib import Path
import os
import secrets
import subprocess
import time
from auth_policy import protect_if_enabled

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'.config/home-server/secrets/people'
PROXY='/data/nginx/custom/home-server/people.conf'
KEY_CONF='/data/nginx/custom/home-server/people-key.conf'

def docker_write(path,data,mode='644'):
    result=subprocess.run(['docker','exec','-i','npm','sh','-c','cat > "$1.pending" && chmod "$2" "$1.pending" && mv "$1.pending" "$1"','sh',path,mode],input=data,capture_output=True)
    if result.returncode:raise RuntimeError('Could not stage proxy configuration')

def docker_read(path):
    result=subprocess.run(['docker','exec','npm','cat',path],capture_output=True)
    return result.stdout if result.returncode==0 else None

def main():
    subprocess.run(['python3',str(ROOT/'scripts/install-people-dependencies.py')],check=True)
    os.umask(0o077);PRIVATE.mkdir(parents=True,mode=0o700,exist_ok=True)
    key_path=PRIVATE/'proxy-key'
    if not key_path.exists():key_path.write_text(secrets.token_hex(32)+'\n')
    key_path.chmod(0o600)
    unit=Path.home()/'.config/systemd/user/home-server-people.service'
    unit.parent.mkdir(parents=True,exist_ok=True)
    unit.write_bytes((ROOT/'templates/systemd/home-server-people.service').read_bytes())
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','home-server-people.service'],check=True)
    for attempt in range(10):
        local=subprocess.run(['python3',str(ROOT/'scripts/check-people.py'),'--local'],capture_output=True)
        if local.returncode==0:break
        time.sleep(1)
    else:raise RuntimeError('People backend failed its local owner-boundary check')
    subprocess.run(['python3',str(ROOT/'scripts/prepare-auth.py')],check=True)
    import json
    key=key_path.read_text().strip()
    assert len(key)==64 and all(c in '0123456789abcdef' for c in key)
    key_data=('proxy_set_header X-Home-People-Key "'+key+'";\n').encode()
    source=(ROOT/'config/nginx/people.conf').read_bytes()
    rendered=protect_if_enabled(source)
    backup=Path.home()/'.local/state/home-server-maintenance/people'/time.strftime('%Y%m%dT%H%M%S')
    backup.mkdir(parents=True,mode=0o700)
    originals={KEY_CONF:docker_read(KEY_CONF),PROXY:docker_read(PROXY)}
    for name,data in originals.items():
        if data is not None:(backup/Path(name).name).write_bytes(data)
    try:
        docker_write(KEY_CONF,key_data,'600')
        docker_write(PROXY,rendered)
        check=subprocess.run(['docker','exec','npm','nginx','-t'],capture_output=True)
        if check.returncode:raise RuntimeError('Proxy validation failed')
        subprocess.run(['docker','exec','npm','nginx','-s','reload'],capture_output=True,check=True)
        for attempt in range(10):
            final=subprocess.run(['python3',str(ROOT/'scripts/check-people.py')],capture_output=True)
            if final.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('People final HTTPS owner login did not pass')
    except Exception:
        for name,data in originals.items():
            if data is None:subprocess.run(['docker','exec','npm','rm','-f',name],capture_output=True,check=True)
            else:docker_write(name,data,'600' if name==KEY_CONF else '644')
        subprocess.run(['docker','exec','npm','nginx','-s','reload'],capture_output=True)
        raise
    print('People is live; owner HTTPS and invitation boundary verified.')

if __name__=='__main__':main()
