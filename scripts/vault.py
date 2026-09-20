#!/usr/bin/env python3
"""Agent-safe 1Password entry point: references in Git, secrets only in a child process."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
repo=Path(__file__).resolve().parents[1]

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--agent',action='store_true',help='Use the dedicated unattended service-account catalog; never fall back to desktop access')
p.add_argument('--with-gateway',action='store_true',help='Also inject the shared auth credential for protected HTTPS checks')
p.add_argument('action',choices=['status','verify','exec'])
p.add_argument('service',nargs='?')
p.add_argument('command',nargs=argparse.REMAINDER)
a=p.parse_args()
config_path=repo/'config/1password'/('agents.json' if a.agent else 'catalog.json')
config=json.loads(config_path.read_text())
if a.agent:
 if not config.get('enabled'):raise SystemExit('Unattended access is not provisioned. See docs/agents/credentials.md; no desktop fallback.')
 if not os.environ.get('OP_SERVICE_ACCOUNT_TOKEN'):raise SystemExit('Provide the scoped service-account token through your protected runtime, never command arguments.')
 if a.with_gateway:raise SystemExit('Agent mode uses dedicated API credentials; owner gateway credentials are not available.')
 account_args=[]
else:
 if os.environ.get('OP_SERVICE_ACCOUNT_TOKEN'):raise SystemExit('Service-account token detected; use --agent or remove it before desktop access.')
 account_args=['--account',config['account']]

if a.action=='status':
 r=subprocess.run(['op','whoami',*account_args,'--format=json'],capture_output=True,text=True)
 if not a.agent and r.returncode and 'account is not signed in' in r.stderr.lower():
  # Desktop authorization may be scoped to the current launcher. Authenticate
  # and verify in the same process; never print or persist sign-in output.
  signin=subprocess.run(['op','signin',*account_args],capture_output=True,text=True)
  if signin.returncode==0:
   r=subprocess.run(['op','whoami',*account_args,'--format=json'],capture_output=True,text=True)
 if r.returncode:
  error=r.stderr.lower()
  if 'account is not signed in' in error:
   raise SystemExit('The configured 1Password account is not signed in to the CLI. Open 1Password and complete the official CLI sign-in flow, then retry.')
  if 'timed out' in error or 'cancel' in error:
   raise SystemExit('1Password authorization timed out or was cancelled. Retry and approve the desktop prompt.')
  raise SystemExit('1Password access could not be verified. Check desktop integration and account sign-in, then retry.')
 print('PASS 1Password '+('service-account' if a.agent else 'desktop')+' access; configured home-server credential references:',len(config['items']))
else:
 if a.service not in config['items']:raise SystemExit('Unknown service; register its saved vault reference first.')
 command=a.command[1:] if a.command[:1]==['--'] else a.command
 if a.action=='verify':
  command=[sys.executable,'-c',("import os;assert os.environ.get('HOME_SERVICE_API_TOKEN');print('PASS API credential resolved without displaying its value')" if a.agent else "import os;assert len(os.environ['HOME_SERVICE_PASSWORD'])>=24;print('PASS credential resolved without displaying its value')")]
 if not command:raise SystemExit('Provide a command after --')
 # Keep op's default output masking. Never add --no-masking.
 files=['--env-file',str(repo/'config/1password'/('agents' if a.agent else '.')/(a.service+'.refs'))]
 if a.with_gateway:files+=['--env-file',str(repo/'config/1password/gateway.refs')]
 if a.agent:
  # The workload gets its selected secret, not the token that can read the vault.
  command=[sys.executable,str(repo/'scripts/agent-secret-child.py'),*command]
 result=subprocess.run(['op','run',*account_args,*files,'--',*command])
 raise SystemExit(result.returncode)
