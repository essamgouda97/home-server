#!/usr/bin/env python3
"""Install a per-user daily Resolve backup job from the current checkout."""
from pathlib import Path
import os
import plistlib
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
label = 'local.home-server.resolve-backup'
logs = Path.home() / 'Library/Logs/home-server'
logs.mkdir(parents=True, exist_ok=True)
target = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
target.parent.mkdir(parents=True, exist_ok=True)
config = {
    'Label': label,
    'ProgramArguments': [sys.executable, str(repo / 'scripts/backup-resolve.py')],
    'StartCalendarInterval': {'Hour': 19, 'Minute': 0},
    'StandardOutPath': str(logs / 'resolve-backup.log'),
    'StandardErrorPath': str(logs / 'resolve-backup-error.log'),
    'ProcessType': 'Background',
}
target.write_bytes(plistlib.dumps(config))
subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], capture_output=True)
subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
print('Daily Resolve backup installed for 19:00 local time; logs in ~/Library/Logs/home-server.')
