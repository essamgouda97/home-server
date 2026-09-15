#!/usr/bin/env python3
"""Relay the existing Mac Bluetooth snapshot over SSH without moving SQLite."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time

def main():
    os.umask(0o077)
    source_job = Path.home()/'Library/LaunchAgents/com.egouda.personal-finances.fitbit-history-ble.plist'
    args = plistlib.loads(source_job.read_bytes())['ProgramArguments']
    state = Path(args[args.index('--state-file')+1])
    repo = Path(__file__).resolve().parents[1]
    settings = dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines()
                    if line and not line.startswith('#') and '=' in line)
    destination = settings['LIFE_DASHBOARD_DATA']+'/data/bridge/fitbit-live.json'
    remote = '''import os,sys,json
from pathlib import Path
os.umask(0o077)
p=Path(sys.argv[1]); data=sys.stdin.buffer.read(524289)
assert len(data)<=524288
json.loads(data);p.parent.mkdir(parents=True,exist_ok=True)
t=p.with_suffix('.tmp');t.write_bytes(data);t.replace(p)
'''
    import shlex
    command = 'python3 -c '+shlex.quote(remote)+' '+shlex.quote(destination)
    last = None
    while True:
        try:
            payload = state.read_bytes()
            if payload != last:
                json.loads(payload)
                result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',
                    'home-server',command],input=payload,capture_output=True,timeout=15)
                if result.returncode == 0: last=payload
        except (OSError, ValueError, subprocess.SubprocessError):
            pass # App shows capture timestamps/offline state; never invent live data.
        time.sleep(5)

if __name__ == '__main__': main()
