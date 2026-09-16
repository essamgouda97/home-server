#!/usr/bin/env python3
"""Agent-safe 1Password entry point: references in Git, secrets only in a child process."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
repo=Path(__file__).resolve().parents[1]
config=json.loads((repo/'config/1password/catalog.json').read_text())
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action',choices=['status','verify','exec'])
p.add_argument('service',nargs='?')
p.add_argument('command',nargs=argparse.REMAINDER)
a=p.parse_args()
if a.action=='status':
 r=subprocess.run(['op','whoami','--account',config['account'],'--format=json'],capture_output=True,text=True)
 if r.returncode:raise SystemExit('1Password is locked or unavailable; approve the desktop prompt, then retry.')
 print('PASS 1Password desktop access; configured home-server credential references:',len(config['items']))
else:
 if a.service not in config['items']:raise SystemExit('Unknown service; register its saved vault reference first.')
 command=a.command[1:] if a.command[:1]==['--'] else a.command
 if a.action=='verify':
  command=[sys.executable,'-c',"import os;assert len(os.environ['HOME_SERVICE_PASSWORD'])>=24;print('PASS credential resolved without displaying its value')"]
 if not command:raise SystemExit('Provide a command after --')
 # Keep op's default output masking. Never add --no-masking.
 result=subprocess.run(['op','run','--account',config['account'],'--env-file',str(repo/'config/1password'/(a.service+'.refs')),'--',*command])
 raise SystemExit(result.returncode)
