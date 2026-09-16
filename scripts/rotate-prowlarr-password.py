#!/usr/bin/env python3
"""Rotate Prowlarr owner login using an escrowed unique credential."""
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
os.umask(0o077)
root=Path.home()/'.config/home-server/secrets';password=json.loads((root/'pending-service-passwords.json').read_text())['prowlarr']
backup=Path.home()/'.local/state/home-server-maintenance/prowlarr-security'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup.mkdir(parents=True)
with sqlite3.connect('/mnt/server/prowlarr/data/prowlarr.db') as live,sqlite3.connect(backup/'prowlarr.db') as saved:live.backup(saved)
key=ET.parse('/mnt/server/prowlarr/data/config.xml').findtext('ApiKey');url='http://127.0.0.1:9696/api/v1/config/host'
with urllib.request.urlopen(urllib.request.Request(url,headers={'X-Api-Key':key})) as r:settings=json.load(r)
settings.update({'username':'egouda','password':password,'passwordConfirmation':password,'authenticationMethod':'forms','authenticationRequired':'enabled'})
with urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(settings).encode(),method='PUT',headers={'X-Api-Key':key,'Content-Type':'application/json'})) as r:r.read()
active=root/'service-passwords.json';values=json.loads(active.read_text());values['prowlarr']=password;active.write_text(json.dumps(values));active.chmod(0o600)
print('Prowlarr unique owner credential applied.')
