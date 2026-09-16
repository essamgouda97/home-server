#!/usr/bin/env python3
"""Escrow existing recovery credentials and new backup key in the personal vault."""
import json
import os
from pathlib import Path
import secrets
import subprocess
from importlib.machinery import SourceFileLoader
helper=SourceFileLoader('credential_helper',str(Path(__file__).with_name('prepare-security-credentials.py'))).load_module()
op,VAULT=helper.op,helper.VAULT
os.umask(0o077)
existing={i['title']:i['id'] for i in op('item','list','--vault',VAULT,'--tags','HomeServer')}
base=Path.home()/'.local/state/home-server-maintenance/security-20260916'
base.mkdir(parents=True,exist_ok=True)
for name in ['legacy-household-recovery','backup-encryption','cloudflare-certificate-dns']:
 title='Home Server — '+name
 if title in existing:item=op('item','get',existing[title],'--vault',VAULT)
 else:
  if name=='legacy-household-recovery':value=subprocess.check_output(['ssh','home-server','cat ~/.config/home-server/secrets/creative_password'],text=True).strip()
  elif name=='backup-encryption':value=secrets.token_urlsafe(48)
  else:value=(base/'cloudflare-scoped-token').read_text().strip()
  item=op('item','create','--vault',VAULT,payload={'title':title,'category':'PASSWORD','tags':['HomeServer'],'fields':[{'id':'password','type':'CONCEALED','purpose':'PASSWORD','value':value}]})
 verified=op('item','get',item['id'],'--vault',VAULT)
 value=next(f['value'] for f in verified['fields'] if f.get('purpose')=='PASSWORD')
 if name=='backup-encryption':
  dest=Path.home()/'.config/home-server/backup-password';dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700);dest.write_text(value+'\n');dest.chmod(0o600)
 print('Saved and read-verified:',name,flush=True)
