#!/usr/bin/env python3
"""Move owner uploads and completed scans beside Creative on the SSD.

Stop File Browser, Samba and home-print-documents before --apply. The old Scans
path becomes a compatibility symlink for the pinned printing Compose stack.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

CREATIVE = Path('/srv/mergerfs/ssd/creative')
DRIVE = Path('/srv/mergerfs/ssd/drive')
STATE = Path.home() / '.local/state/home-print-documents/scan.json'
BACKUP_BASE = Path.home() / '.local/state/home-server-maintenance/drive-root'
SERVICES = ('filebrowser', 'samba', 'home-print-documents')


def digest_tree(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            result[path.relative_to(root).as_posix()] = digest.hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if STATE.exists() and json.loads(STATE.read_text()).get('mode') == 'scanning':
        raise SystemExit('Active scan: wait before migrating')
    old = {name: CREATIVE / name for name in ('AI Inbox', 'Scans')}
    new = {name: DRIVE / name for name in old}
    if old['Scans'].is_symlink() and old['Scans'].resolve() == new['Scans'].resolve():
        print('Drive folders already migrated')
        return
    if not all(path.is_dir() and not path.is_symlink() for path in old.values()):
        raise SystemExit('Expected source directories are missing or already redirected')
    if any(path.exists() or path.is_symlink() for path in new.values()):
        raise SystemExit('Destination exists; inspect before moving')
    if (DRIVE / 'Creative').exists() or (DRIVE / 'Creative').is_symlink():
        raise SystemExit('Drive/Creative exists; inspect before moving')
    if CREATIVE.stat().st_dev != DRIVE.parent.stat().st_dev:
        raise SystemExit('Source and destination are on different filesystems')
    for service in SERVICES:
        status = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', service],
                                capture_output=True, text=True)
        if args.apply and status.returncode == 0 and status.stdout.strip() == 'true':
            raise SystemExit(f'Stop {service} before moving data')
    if not args.apply:
        print('Ready to move AI Inbox and Scans; use --apply after stopping dependent services')
        return
    backup = BACKUP_BASE / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup, 0o700)
    for name, source in old.items():
        shutil.copytree(source, backup / name, symlinks=True)
        if digest_tree(source) != digest_tree(backup / name):
            raise SystemExit('Backup verification failed; no move performed')
    DRIVE.mkdir(mode=0o700, exist_ok=True)
    os.chmod(DRIVE, 0o700)
    moved = []
    try:
        for name, source in old.items():
            source.rename(new[name])
            moved.append(name)
        old['Scans'].symlink_to(new['Scans'], target_is_directory=True)
        (DRIVE / 'Creative').symlink_to(CREATIVE, target_is_directory=True)
        for name in old:
            if digest_tree(new[name]) != digest_tree(backup / name):
                raise RuntimeError('Move verification failed')
    except Exception:
        if old['Scans'].is_symlink():
            old['Scans'].unlink()
        if (DRIVE / 'Creative').is_symlink():
            (DRIVE / 'Creative').unlink()
        for name in reversed(moved):
            new[name].rename(old[name])
        raise
    print('Moved AI Inbox and Scans with verified private backup; scanner compatibility path retained')

if __name__ == '__main__':
    main()
