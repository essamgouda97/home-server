#!/usr/bin/env python3
"""Add/update one service in the catalog. Use --sync on the Mac to verify and publish its Homarr tile."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
p=argparse.ArgumentParser(description=__doc__)
for key in ['id','title','url','probe-url']:p.add_argument('--'+key,required=True)
p.add_argument('--credential',default='auth')
p.add_argument('--category',default='Applications')
p.add_argument('--icon',default='https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/docker.svg')
p.add_argument('--access',choices=['owner','household'],default='owner')
p.add_argument('--adapter',choices=['gateway','native','trusted-header','oidc'],default='gateway')
p.add_argument('--sync',action='store_true')
a=p.parse_args();assert re.fullmatch('[a-z0-9-]+',a.id)
u=urlsplit(a.url);assert u.scheme=='https' and u.hostname.endswith('.home.egouda.xyz') and not u.username and not u.query
repo=Path(__file__).resolve().parents[1];file=repo/'config/services.json';catalog=json.loads(file.read_text())
entry={'id':a.id,'title':a.title,'url':a.url,'probe_url':a.probe_url,'credential':a.credential,'category':a.category,'auth':{'mode':'gateway','access':a.access,'adapter':a.adapter},'icon':a.icon,'expected_status':[200,301,302,303,307,308,401]}
catalog['services']=[s for s in catalog['services'] if s['id']!=a.id]+[entry]
file.write_text(json.dumps(catalog,indent=2)+'\n')
if a.sync:
 subprocess.run(['rsync','-a',str(file),'home-server:workspace/home-server/config/services.json'],check=True)
 subprocess.run(['ssh','home-server','cd ~/workspace/home-server && python3 scripts/prepare-auth.py && python3 scripts/configure-auth-proxies.py && python3 scripts/check-auth.py && python3 scripts/sync-service-catalog.py && python3 scripts/provision-homarr-identities.py && systemctl --user start home-server-metrics.service'],check=True)
print('Registered:',a.id,'— commit the catalog change after verification.')
