#!/usr/bin/env python3
"""Rotate private proxy credentials only after 1Password escrow."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import urllib.error
import time

os.umask(0o077)
root=Path.home()/'.config/home-server/secrets'
values=json.loads((root/'pending-service-passwords.json').read_text())
base=Path('/mnt/server/npm/data/nginx/custom/home-server')
backup=Path.home()/'.local/state/home-server-maintenance/proxy-passwords'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup.mkdir(parents=True)
for file in [base/name for name in ['draw.htpasswd','life-dashboard.htpasswd','footage.htpasswd','ods.htpasswd','design-dns.conf','household-https.conf']]:
 if file.is_file():(backup/file.name).write_bytes(subprocess.check_output(['docker','exec','npm','cat','/data/nginx/custom/home-server/'+file.name]))
for service,filename in [('draw','draw.htpasswd'),('life','life-dashboard.htpasswd'),('ingest','footage.htpasswd'),('ods','ods.htpasswd')]:
 hashed=subprocess.run(['openssl','passwd','-6','-stdin'],input=values[service].encode()+b'\n',capture_output=True,check=True).stdout.strip()
 subprocess.run(['docker','exec','-i','npm','sh','-c','umask 077; cat > "$1"; chmod 644 "$1"','sh','/data/nginx/custom/home-server/'+filename],input=b'egouda:'+hashed+b'\n',check=True)
# Draw formerly shared ODS's hash. Separate only its own server blocks.
for name in ['design-dns.conf','household-https.conf']:
 p=base/name;text=p.read_text()
 import re
 lines=text.splitlines();host=None
 for i,line in enumerate(lines):
  if 'server_name ' in line:host=line.split('server_name ',1)[1].split(';',1)[0].strip()
  if 'auth_basic_user_file ' in line and host and host.split('.')[0] in ['draw','ods']:
   lines[i]='    auth_basic_user_file /data/nginx/custom/home-server/'+host.split('.')[0]+'.htpasswd;'
 text='\n'.join(lines)+'\n'
 subprocess.run(['docker','exec','-i','npm','sh','-c','cat > "$1"','sh','/data/nginx/custom/home-server/'+name],input=text.encode(),check=True)
subprocess.run(['docker','exec','npm','nginx','-t'],check=True,capture_output=True)
subprocess.run(['docker','exec','npm','nginx','-s','reload'],check=True,capture_output=True)
active=root/'service-passwords.json';saved=json.loads(active.read_text())
for service in ['draw','life','ingest','ods']:
 auth=base64.b64encode(('egouda:'+values[service]).encode()).decode()
 for attempt in range(10):
  try:
   with urllib.request.urlopen(urllib.request.Request('https://'+service+'.home.egouda.xyz/',headers={'Authorization':'Basic '+auth}),timeout=20) as r:assert r.status==200
   break
  except urllib.error.HTTPError:
   if attempt==9:raise
   time.sleep(1)
 saved[service]=values[service]
 print('PASS distinct HTTPS credential:',service)
active.write_text(json.dumps(saved));active.chmod(0o600)
