#!/usr/bin/env python3
"""Install only the coach HTTPS route with rollback on nginx validation failure."""
from pathlib import Path
from auth_policy import protect_if_enabled
import os
import subprocess
import time

REPO=Path(__file__).resolve().parents[1]
DEST='/data/nginx/custom/home-server/coach.conf'


def write(data):
    subprocess.run(['docker','exec','-i','npm','sh','-c','cat > '+DEST+'.pending && chmod 644 '+DEST+'.pending && mv '+DEST+'.pending '+DEST],input=data,check=True)


def main():
    os.umask(0o077)
    subprocess.run(['python3',str(REPO/'scripts/check-download-logins.py'),'--local'],check=True)
    network='health-coach_auth'
    state=subprocess.run(['docker','network','inspect',network],capture_output=True)
    if state.returncode:raise SystemExit('Start the updated Coach container before publishing its route.')
    parsed=__import__('json').loads(state.stdout)[0]
    names={v['Name'] for v in parsed.get('Containers',{}).values()}
    if 'npm' not in names:subprocess.run(['docker','network','connect',network,'npm'],check=True)
    parsed=__import__('json').loads(subprocess.run(['docker','network','inspect',network],capture_output=True,text=True,check=True).stdout)[0]
    assert {v['Name'] for v in parsed['Containers'].values()}=={'health-coach','npm'}
    subprocess.run(['docker','run','--rm','--network','none','-v',
                    str(REPO/'services/health-coach/test_coach.py')+':/app/test_coach.py:ro',
                    '--entrypoint','python','health-coach-coach','-m','unittest','test_coach.py'],check=True)
    folder=Path.home()/'.local/state/home-server-maintenance/coach-proxy'/time.strftime('%Y%m%dT%H%M%S');folder.mkdir(parents=True)
    previous=subprocess.run(['docker','exec','npm','cat',DEST],capture_output=True)
    if previous.returncode==0:(folder/'coach.conf').write_bytes(previous.stdout)
    try:
        write(protect_if_enabled((REPO/'config/nginx/coach.conf').read_bytes()))
        subprocess.run(['docker','exec','npm','nginx','-t'],capture_output=True,check=True)
    except Exception:
        if previous.returncode==0:write(previous.stdout)
        else:subprocess.run(['docker','exec','npm','mv',DEST,DEST+'.rejected'],check=True)
        raise SystemExit('Proxy validation failed; previous state restored.')
    subprocess.run(['docker','exec','npm','nginx','-s','reload'],capture_output=True,check=True)
    for attempt in range(5):
        checked=subprocess.run(['python3',str(REPO/'scripts/check-coach.py')],capture_output=True)
        if checked.returncode==0:break
        time.sleep(1)
    else:raise SystemExit('Final HTTPS login check failed after proxy reload.')
    print('Coach HTTPS login verified.')
    subprocess.run(['python3',str(REPO/'scripts/check-download-logins.py'),'--native-only'],check=True)


if __name__=='__main__':main()
