#!/usr/bin/env python3
"""Prepare central authentication from vaulted secrets; never prints credentials."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'.config/home-server/secrets'
DEST=PRIVATE/'authelia'

def encoded(value):
    return base64.b64encode(value).decode().rstrip('=').replace('+','.')

def pbkdf2(password):
    salt=secrets.token_bytes(16); rounds=310000
    digest=hashlib.pbkdf2_hmac('sha512',password.encode(),salt,rounds)
    return f'$pbkdf2-sha512${rounds}${encoded(salt)}${encoded(digest)}'

def import_jellyfin(value):
    _,algorithm,parameters,salt,digest=value.split('$')
    assert algorithm=='PBKDF2-SHA512' and parameters.startswith('iterations=')
    rounds=int(parameters.split('=')[1]); assert rounds>=210000
    return f'$pbkdf2-sha512${rounds}${encoded(bytes.fromhex(salt))}${encoded(bytes.fromhex(digest))}'

def main():
    os.umask(0o077);DEST.mkdir(parents=True,exist_ok=True)
    password=json.loads((PRIVATE/'pending-service-passwords.json').read_text())['auth']
    users_path=DEST/'users.yml'
    if not users_path.exists():
        with sqlite3.connect('file:/mnt/server/jellyfin/config/data/data/jellyfin.db?mode=ro',uri=True) as db:
            old=dict(db.execute('SELECT Username,Password FROM Users'))
        # Verify the import algorithm against the known, vaulted Jellyfin owner
        # credential before importing Mariam's verifier, without knowing hers.
        jf=json.loads((PRIVATE/'service-passwords.json').read_text())['jellyfin']
        _,alg,parameters,salt,digest=old['egouda'].split('$')
        assert secrets.compare_digest(hashlib.pbkdf2_hmac('sha512',jf.encode(),bytes.fromhex(salt),int(parameters.split('=')[1])).hex().lower(),digest.lower())
        users={'egouda':{'displayname':'Essam','password':pbkdf2(password),'email':'egouda@home.egouda.xyz','groups':['owners','household']},
               'mgouda':{'displayname':'Mariam','password':import_jellyfin(old['mgouda']),'email':'mgouda@home.egouda.xyz','groups':['household']}}
        users_path.write_text(yaml.safe_dump({'users':users}))
    for name in ['jwt_secret','session_secret','storage_key']:
        p=DEST/name
        if not p.exists():p.write_text(secrets.token_urlsafe(48))
    config=yaml.safe_load((ROOT/'config/auth/configuration.yml').read_text())
    catalog=json.loads((ROOT/'config/services.json').read_text())['services']
    from urllib.parse import urlsplit
    rules=[]
    for s in catalog:
        assert s['auth']['mode']=='gateway' and s['auth']['access'] in ('household','owner')
        rules.append({'domain':urlsplit(s['url']).hostname,'policy':'one_factor','subject':['group:'+('household' if s['auth']['access']=='household' else 'owners')]})
    config['access_control']['rules']=rules
    (DEST/'configuration.yml').write_text(yaml.safe_dump(config,sort_keys=False))
    # SSD path creation requires existing owner sudo authorization, not a new secret.
    sudo=(PRIVATE/'creative_password').read_text().strip()+'\n'
    r=subprocess.run(['sudo','-S','-p','','install','-d','-m','700','-o','1000','-g','1000','/srv/mergerfs/ssd/authelia'],input=sudo,text=True,capture_output=True)
    assert r.returncode==0,'Cannot prepare Authelia state directory'
    for p in DEST.iterdir():p.chmod(0o600)
    command=['docker','compose','--env-file','server.conf','-f','compose.auth.yml']
    r=subprocess.run(command+['run','--rm','authelia','authelia','validate-config','--config','/config/configuration.yml'],cwd=ROOT,capture_output=True,text=True)
    if r.returncode:
        # Error messages can contain private configuration. Retain privately only.
        (DEST/'validation.log').write_text(r.stdout+r.stderr)
        raise SystemExit('Auth configuration validation failed; private validation.log retained')
    subprocess.run(command+['up','-d'],cwd=ROOT,check=True)
    print('Central auth configured; owner and household identities prepared. Proxy unchanged.')

if __name__=='__main__':main()
