#!/usr/bin/env python3
"""Remove an explicitly authorized Workspace-only identity; retain shared data.

Requires --confirm-username. Backups are private and outside Git. This restarts
Authelia to invalidate its in-memory sessions before a username can be reused.
Other applications' native accounts require their own offboarding procedure.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import yaml

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home()/'.config/home-server/secrets'

def run(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True)
    if result.returncode:
        raise RuntimeError('Maintenance step failed; captured output withheld: '+args[0])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument('--confirm-username', required=True)
    args = parser.parse_args()
    username = args.username
    assert username == args.confirm_username and username not in ('egouda','mgouda')
    catalog_path = ROOT/'config/identities.json'
    users_path = PRIVATE/'authelia/users.yml'
    invites_path = PRIVATE/'people/invitations.json'
    catalog = json.loads(catalog_path.read_text())
    person = catalog['users'].get(username)
    assert person and not person['owner'] and person['services'] == ['workspace'], 'Only a Workspace-only member can use this procedure'
    os.umask(0o077)
    backup = Path.home()/'.local/state/home-server-maintenance/account-removal'/time.strftime('%Y%m%dT%H%M%S')
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    run(['systemctl','--user','stop','home-server-people.service'])
    try:
        for path in (catalog_path, users_path, invites_path):
            shutil.copy2(path, backup/path.name)
            (backup/path.name).chmod(0o600)
        # Re-read after the enrollment service stops; never remove shared records.
        catalog = json.loads(catalog_path.read_text())
        assert catalog['users'].get(username) == person, 'Identity changed during offboarding'
        users = yaml.safe_load(users_path.read_text())
        invites = json.loads(invites_path.read_text())
        with sqlite3.connect('/srv/mergerfs/ssd/shared-workspace/app/workspace.sqlite3') as db:
            with sqlite3.connect(backup/'workspace.sqlite3') as copy:
                db.backup(copy)
            db.execute('UPDATE keys SET revoked=1 WHERE username=?', (username,))
            db.execute("UPDATE connections SET status='denied' WHERE username=?", (username,))
        for invite in invites['invitations'].values():
            if invite['username'] == username:
                invite['status'] = 'revoked'
        invites_path.write_text(json.dumps(invites,indent=2)+'\n')
        del catalog['users'][username]
        users['users'].pop(username, None)
        catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')
        # This file is watched/mounted by Authelia; write in place, then restart.
        users_path.write_text(yaml.safe_dump(users))
        run(['python3','scripts/prepare-auth.py'])
        run(['docker','restart','home-authelia'])
        run(['docker','exec','npm','nginx','-s','reload'])
    finally:
        run(['systemctl','--user','start','home-server-people.service'])
    print('Removed '+username+'; prior invitations and agent keys revoked; shared data retained.')
    print('Central browser sessions invalidated. Private recovery backup: '+str(backup))

if __name__ == '__main__':
    main()
