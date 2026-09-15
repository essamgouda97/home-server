#!/usr/bin/env python3
"""Install Mac companions and retire local history writers after server migration."""
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

repo=Path(__file__).resolve().parents[1]
agents=Path.home()/'Library/LaunchAgents'
logs=Path.home()/'Library/Logs/home-server';logs.mkdir(parents=True,exist_ok=True)
backup=Path.home()/'.local/state/life-dashboard-migration/launchagents'
backup.mkdir(parents=True,exist_ok=True,mode=0o700)
for suffix in ('ble','google'):
    label='com.egouda.personal-finances.fitbit-history-'+suffix
    original=agents/(label+'.plist')
    if original.exists():
        if not (backup/original.name).exists(): shutil.copy2(original,backup/original.name)
        subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
        subprocess.run(['launchctl','disable',f'gui/{os.getuid()}/{label}'],check=True)
for name,script in [('fitbit-relay','push-life-fitbit.py'),('mac-companion','life-mac-companion.py')]:
    if name == 'fitbit-relay' and (Path.home()/'.config/home-server/gym-pi-primary').exists():
        continue # The gym Pi owns live capture; preserve the user's explicit Mac retirement.
    label='com.egouda.life-dashboard.'+name
    p=agents/(label+'.plist')
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
    p.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':['/usr/bin/python3',str(repo/'scripts'/script)],
        'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'Umask':63,
        'StandardOutPath':str(logs/(name+'.log')),'StandardErrorPath':str(logs/(name+'-error.log'))}))
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(p)],check=True)
print('Mac Fitbit and Resolve companions installed; local history writers retired.')
