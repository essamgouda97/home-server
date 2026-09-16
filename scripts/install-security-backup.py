#!/usr/bin/env python3
"""Schedule encrypted Mac backups; requires the Mac awake and server reachable."""
from pathlib import Path
import os
import plistlib
import subprocess
import sys
repo=Path(__file__).resolve().parents[1]
label='local.home-server.security-backup'
logs=Path.home()/'Library/Logs/home-server';logs.mkdir(parents=True,exist_ok=True)
p=Path.home()/'Library/LaunchAgents'/(label+'.plist');p.parent.mkdir(parents=True,exist_ok=True)
p.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':[sys.executable,str(repo/'scripts/backup-security-to-mac.py')],'StartCalendarInterval':{'Hour':18,'Minute':30},'StandardOutPath':str(logs/'security-backup.log'),'StandardErrorPath':str(logs/'security-backup-error.log'),'ProcessType':'Background','EnvironmentVariables':{'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'}}))
subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(p)],check=True)
print('Encrypted recovery backup scheduled daily at 18:30; low-space guard enabled.')
