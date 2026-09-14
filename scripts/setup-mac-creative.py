#!/usr/bin/env python3
"""Provision private access, remember it in Keychain, and mount Creative in Finder.

Run on the Mac after host preparation. Re-running asks for the existing password;
it does not reset server credentials. Passwords are never printed.
"""
import json
import argparse
from pathlib import Path
import secrets
import shlex
import subprocess

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
secret_path = settings['HOME_SERVER_SECRETS_DIR'] + '/creative_password'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--generate', action='store_true', help='Generate or reuse private credentials and save them in Keychain without a dialog')
parser.add_argument('--change-password', action='store_true', help='Choose a new password and update the existing services and Keychain')
args = parser.parse_args()
if args.generate and args.change_password:
    parser.error('--generate and --change-password cannot be combined')
check = subprocess.run(['ssh', 'home-server', 'test -s ' + shlex.quote(secret_path)])
if check.returncode not in [0, 1]:
    raise SystemExit('Could not check server credentials; refusing to replace them.')
exists = check.returncode == 0
message = ('Enter your existing Creative Drive password.' if exists else
           'Choose a password of at least 12 characters for Creative Drive and the initial Home Assistant owner account. Username: egouda.')
if args.change_password:
    if not exists:
        raise SystemExit('Initialize the services before changing their password.')
    message = 'Choose a new password of at least 12 characters for Creative Drive (web + Finder) and Home Assistant. Username: egouda. Ubuntu credentials are not needed.'
script = 'text returned of (display dialog ' + json.dumps(message) + ' default answer "" with hidden answer buttons {"Cancel", "Continue"} default button "Continue" with title "Home services access")'
if args.generate:
    if exists:
        result = subprocess.run(['ssh', 'home-server', 'cat ' + shlex.quote(secret_path)], capture_output=True, text=True, check=True)
        password = result.stdout
        del result
    else:
        password = secrets.token_urlsafe(24)
else:
    answer = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if answer.returncode:
        raise SystemExit('Cancelled; no credentials changed.')
    password = answer.stdout.rstrip('\n')
    del answer
if len(password) < 12 or any(ord(c) < 32 for c in password):
    raise SystemExit('Use at least 12 characters, with no control characters.')
if args.change_password:
    confirm = subprocess.run(['osascript','-e','text returned of (display dialog "Enter the new home-services password again." default answer "" with hidden answer buttons {"Cancel", "Confirm"} default button "Confirm" with title "Confirm home-services password")'],capture_output=True,text=True)
    if confirm.returncode or confirm.stdout.rstrip('\n') != password:
        raise SystemExit('Cancelled or passwords did not match; services unchanged.')
    changed = subprocess.run(['ssh','home-server','cd ~/workspace/home-server && python3 scripts/change-home-services-password.py'],input=password,text=True,capture_output=True)
    if changed.returncode:
        raise SystemExit('Password change did not complete; existing Keychain entries preserved. Check service credentials before retrying.')
    print('Home-services password updated.')
if not exists:
    remote = 'umask 077; mkdir -p ' + shlex.quote(settings['HOME_SERVER_SECRETS_DIR']) + '; cat > ' + shlex.quote(secret_path)
    subprocess.run(['ssh', 'home-server', remote], input=password, text=True, check=True)

# security's interactive mode keeps the password out of the process arguments.
line = ''.join('add-internet-password -U -a egouda -s ' + host + ' -r ' + json.dumps(protocol) + ' -w ' + json.dumps(password, ensure_ascii=False) + '\n'
               for host, protocol in [('home-server.lan','smb '), ('files.lan','http'), ('assistant.lan','http')])
saved = subprocess.run(['security', '-i'], input=line, text=True, capture_output=True)
if saved.returncode:
    print('Keychain storage did not complete; use the password you chose when Finder asks.')
else:
    print('Creative Drive credential saved in the login Keychain for home-server.lan.')

local = Path.home() / 'Movies/Creative'
for folder in ['Proxies', 'Cache', 'ProjectBackups', 'Exports']:
    (local / folder).mkdir(parents=True, exist_ok=True)
print('Local editing folders ready at ~/Movies/Creative.')
print('Start the services, then run: open smb://egouda@home-server.lan/Creative')
