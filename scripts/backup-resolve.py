#!/usr/bin/env python3
"""Consistent SQLite project snapshots; keeps 14 local and 30 server archives.

This backs up the local Resolve Project Library, not footage or render caches.
"""
from datetime import datetime, timezone
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

PREFIX = 'resolve-library-'
def verify(archive):
    with tempfile.TemporaryDirectory(prefix='resolve-verify-') as tmp:
        root = Path(tmp).resolve()
        with tarfile.open(archive, 'r:gz') as tf:
            for member in tf.getmembers():
                target = (root / member.name).resolve()
                if root not in target.parents or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe archive member.')
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tf.extractfile(member) as src, target.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
        count = 0
        for path in root.rglob('*'):
            if path.is_file() and path.open('rb').read(16) == b'SQLite format 3\0':
                with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise ValueError('Snapshot database integrity check failed.')
                count += 1
        if count == 0:
            raise ValueError('No Resolve SQLite databases in archive.')
        return count

def prune(folder, keep):
    archives = sorted(folder.glob(PREFIX + '*.tar.gz'))
    for old in archives[:-keep]:
        old.unlink()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--library', type=Path, default=Path.home() / 'Library/Application Support/Blackmagic Design/DaVinci Resolve/Resolve Project Library')
    parser.add_argument('--local', type=Path, default=Path.home() / 'Movies/Creative/ProjectBackups')
    parser.add_argument('--share', type=Path, default=Path('/Volumes/Creative'))
    args = parser.parse_args()
    args.library = args.library.resolve()
    if args.verify:
        print(f'Archive restore/integrity check passed for {verify(args.verify)} SQLite databases.')
        return
    if not args.library.is_dir():
        raise SystemExit('Resolve project library not found; no backup created.')
    args.local.mkdir(parents=True, exist_ok=True)
    with (args.local / '.backup.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another Resolve backup is running.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        archive = args.local / f'{PREFIX}{stamp}.tar.gz'
        temporary = archive.with_suffix('.partial')
        with tempfile.TemporaryDirectory(prefix='resolve-snapshot-') as tmp:
            snapshot = Path(tmp) / 'Resolve Project Library'
            for source in args.library.rglob('*'):
                if source.is_symlink() or source.name.endswith(('-wal', '-shm', '-journal')):
                    continue
                target = snapshot / source.relative_to(args.library)
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open('rb') as f:
                    sqlite = f.read(16) == b'SQLite format 3\0'
                if sqlite:
                    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
                        src.backup(dst)
                else:
                    shutil.copy2(source, target)
            with tarfile.open(temporary, 'w:gz') as tf:
                tf.add(snapshot, arcname=snapshot.name)
        count = verify(temporary)
        temporary.chmod(0o600)
        os.replace(temporary, archive)
        print(f'Created and restore-verified {archive.name}: {count} SQLite databases.')
        if os.path.ismount(args.share):
            destination = args.share / 'ProjectBackups' / 'MacBookAir'
            destination.mkdir(parents=True, exist_ok=True)
            for pending in sorted(args.local.glob(PREFIX + '*.tar.gz')):
                target = destination / pending.name
                if not target.exists():
                    staging = target.with_suffix('.partial')
                    shutil.copy2(pending, staging)
                    verify(staging)
                    os.replace(staging, target)
            prune(destination, 30)
            print('Uploaded snapshots to Creative/ProjectBackups/MacBookAir.')
        else:
            print('Creative is not mounted; snapshot remains local for the next connected run.')
        prune(args.local, 14)

if __name__ == '__main__':
    main()
