#!/usr/bin/env python3
"""Copy a camera folder to Creative, verify SHA-256, and preserve every source.

Example: python3 scripts/ingest-footage.py /Volumes/DJI/DCIM 2026-09-14-river pocket-card-01
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

CHUNK = 8 * 1024 * 1024
def publish_exclusive(partial, target, share=Path('/Volumes/Creative')):
    """Publish without overwrite; Mac SMB delegates this one operation to SSH."""
    if sys.platform == 'darwin':
        # macOS SMB supports neither hard links nor RENAME_EXCL. Perform the
        # atomic link on the server filesystem, without copying the data twice.
        repo = Path(__file__).resolve().parents[1]
        settings = dict(line.split('=', 1) for line in (repo / 'server.conf').read_text().splitlines()
                        if line and not line.startswith('#') and '=' in line)
        paths = [str(p.relative_to(share)) for p in (partial, target)]
        worker = '''import json,os,sys
from pathlib import Path
root,a,b=json.loads(sys.stdin.readline())
root=Path(root).resolve()
paths=[root/a,root/b]
for p in paths:
    if root not in p.resolve().parents or any(q.is_symlink() for q in [p,*p.parents]):
        sys.exit(2)
try:
    os.link(*paths)
except FileExistsError:
    sys.exit(17)
'''
        import shlex
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'home-server',
                                 'python3 -c ' + shlex.quote(worker)],
                                input=json.dumps([settings['CREATIVE_ROOT'], *paths]),
                                text=True, capture_output=True)
        if result.returncode == 17:
            raise FileExistsError(str(target))
        if result.returncode:
            raise OSError('Server could not finalize verified footage; check SSH access. Source retained.')
    else:
        os.link(partial, target)

def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            result.update(chunk)
    return result.hexdigest()

def ingest(source, share, project, card):
    source, share = source.resolve(), share.resolve()
    if not source.is_dir() or not os.path.ismount(share):
        raise ValueError('Source must be a folder and Creative must be an actual mounted share.')
    if source == share or source in share.parents or share in source.parents:
        raise ValueError('Source and destination must be separate locations.')
    for name in [project, card]:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', name) or '..' in name:
            raise ValueError('Project/card names must contain only letters, numbers, dots, hyphens or underscores.')
    root = share / 'Projects' / project
    destination = root / 'Originals' / card
    if any(p.is_symlink() for p in [root, root / 'Originals', destination]):
        raise ValueError('Destination must not contain symbolic links.')
    destination.mkdir(parents=True, exist_ok=True)
    for folder in ['Audio', 'Graphics', 'Exports', 'Manifests']:
        (root / folder).mkdir(exist_ok=True)
    rows = []
    copied = skipped = total = 0
    for original in sorted(source.rglob('*')):
        if original.is_symlink():
            raise ValueError('Symbolic links are not camera originals; copy aborted.')
        relative = original.relative_to(source)
        target = destination / relative
        if any(parent.is_symlink() for parent in [target, *target.parents]):
            raise ValueError('Refusing to follow a destination symbolic link.')
        if original.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not original.is_file():
            raise ValueError('Unsupported source file type.')
        before = original.stat()
        expected = digest(original)
        if target.exists():
            if not target.is_file() or digest(target) != expected:
                raise ValueError(f'Destination differs; nothing overwritten: {relative}')
            skipped += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name('.' + target.name + '.ingest-' + uuid.uuid4().hex)
            try:
                with original.open('rb') as src, partial.open('xb') as dst:
                    shutil.copyfileobj(src, dst, CHUNK)
                    dst.flush()
                    os.fsync(dst.fileno())
                if digest(partial) != expected:
                    raise OSError('Checksum mismatch; original retained.')
                after = original.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise OSError('Source changed while copying; original retained.')
                shutil.copystat(original, partial)
                publish_exclusive(partial, target, share)
                copied += 1
            finally:
                partial.unlink(missing_ok=True)
        rows.append({'path': relative.as_posix(), 'bytes': before.st_size, 'sha256': expected})
        total += before.st_size
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    manifest = root / 'Manifests' / f'{card}-{stamp}.json'
    manifest.write_text(json.dumps({'card': card, 'verified_at': stamp, 'files': rows}, indent=2) + '\n')
    print(f'Verified {len(rows)} files, {total:,} bytes: {copied} copied, {skipped} already identical.')
    print(f'Originals: {destination}\nManifest: {manifest}\nSource files were not erased. Keep another independent copy.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('project')
    parser.add_argument('card')
    parser.add_argument('--share', type=Path, default=Path('/Volumes/Creative'))
    args = parser.parse_args()
    ingest(args.source, args.share, args.project, args.card)
