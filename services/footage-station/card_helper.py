#!/usr/bin/python3
"""Small root-only mount helper; never formats, repairs or writes camera cards."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess

BASE = Path('/run/footage-cards')
ACCOUNT = 'footage-station'


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def descendants(node):
    yield node
    for child in node.get('children', []):
        yield from descendants(child)


def usb_identity(device):
    """Read the actual USB ancestor, not the generic SCSI model or volume label."""
    if not isinstance(device, str) or not re.fullmatch(r'\d+:\d+', device):
        return None
    try:
        path = (Path('/sys/dev/block') / device).resolve(strict=True)
        for ancestor in (path, *path.parents):
            if (ancestor / 'idVendor').is_file():
                return tuple((ancestor / name).read_text().strip()
                             for name in ('idVendor', 'idProduct', 'product'))
    except OSError:
        pass  # Disconnection or unavailable identity must fail closed.
    return None


def candidates(tree, root_device, usb_devices=None):
    if not any(n.get('maj:min') == root_device for disk in tree for n in descendants(disk)):
        raise ValueError('Cannot identify the operating-system disk; no camera cards offered.')
    results = []
    for disk in tree:
        if any(n.get('maj:min') == root_device for n in descendants(disk)):
            continue
        if disk.get('type') != 'disk' or disk.get('tran') != 'usb':
            continue
        if not disk.get('rm'):
            identity = (usb_devices or {}).get(disk.get('maj:min'))
            # Pocket 4 internal storage advertises RM=0, model IBLOCK. Never
            # broaden this exception to arbitrary USB SSDs or other host disks.
            if not identity or identity[:2] != ('2ca3', '0020') or not identity[2].startswith('OsmoPocket4-'):
                continue
        for part in disk.get('children', []):
            uuid = part.get('uuid')
            if part.get('type') != 'part' or part.get('children') or part.get('fstype') not in ('vfat', 'exfat'):
                continue
            if not isinstance(uuid, str) or not re.fullmatch('[A-Fa-f0-9-]{4,36}', uuid):
                continue
            target = str(BASE / uuid)
            mounts = [p for p in part.get('mountpoints', []) or [] if p]
            # Do not take over a card mounted by another service or user.
            if any(p != target for p in mounts):
                continue
            results.append({'uuid': uuid, 'label': part.get('label') or 'Camera card',
                'capacity': part['size'], 'device': part['maj:min'], 'fstype': part['fstype'],
                'model': (disk.get('model') or 'USB reader').strip(), 'mounted': bool(mounts)})
    if len({p['uuid'] for p in results}) != len(results):
        raise ValueError('Two cards have the same filesystem ID. Connect only one of them.')
    return results


def list_cards():
    tree = json.loads(output('lsblk', '--tree', '-b', '-J', '-o',
        'NAME,PATH,MAJ:MIN,SIZE,MODEL,TRAN,RM,TYPE,FSTYPE,UUID,LABEL,MOUNTPOINTS'))['blockdevices']
    identities = {disk.get('maj:min'): usb_identity(disk.get('maj:min')) for disk in tree
                  if disk.get('tran') == 'usb' and not disk.get('rm')}
    return candidates(tree, output('findmnt', '-n', '-o', 'MAJ:MIN', '--target', '/'), identities)


def mounted(target):
    result = subprocess.run(['findmnt', '-J', '-M', str(target), '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS,MAJ:MIN'],
                            capture_output=True, text=True)
    if result.returncode == 1:
        return None
    result.check_returncode()
    filesystems = json.loads(result.stdout)['filesystems']
    if len(filesystems) != 1:
        raise ValueError('Unexpected mount stack; manual inspection required.')
    return filesystems[0]


def ensure_private_directory(path):
    path.mkdir(mode=0o755, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Unsafe mount directory permissions.')


def require_readonly(info):
    if info['fstype'] not in ('vfat', 'exfat') or 'ro' not in info['options'].split(','):
        raise ValueError('Camera mount is not a supported read-only filesystem.')


def mount_card(uuid):
    card = next((c for c in list_cards() if c['uuid'] == uuid), None)
    if card is None:
        raise ValueError('Selected camera card is missing, in use, or not supported.')
    ensure_private_directory(BASE)
    target = BASE / uuid
    current = mounted(target)
    if current:
        require_readonly(current)
        if current['maj:min'] != card['device']:
            raise ValueError('A different card occupies this mount; eject it first.')
    else:
        ensure_private_directory(target)
        if any(target.iterdir()):
            raise ValueError('Mount directory is not empty.')
        device = '/dev/block/' + card['device']
        if output('blkid', '-p', '-s', 'UUID', '-o', 'value', device) != uuid:
            raise ValueError('Card changed before mounting; refresh and retry.')
        account = pwd.getpwnam(ACCOUNT)
        options = f'ro,nosuid,nodev,noexec,uid={account.pw_uid},gid={account.pw_gid},umask=077'
        subprocess.run(['mount', '-t', card['fstype'], '-o', options, device, str(target)], check=True)
        current = mounted(target)
        if not current or current['maj:min'] != card['device']:
            raise ValueError('Mounted card identity does not match selection.')
        require_readonly(current)
    return {'uuid': uuid, 'path': str(target), 'readonly': True}


def unmount_card(uuid):
    target = BASE / uuid
    current = mounted(target)
    if current:
        # A disconnected card may no longer be in lsblk. Only our exact controlled
        # read-only camera mount can be released. No force/lazy unmount is allowed.
        require_readonly(current)
        subprocess.run(['umount', str(target)], check=True)
    if mounted(target):
        raise ValueError('Card is still mounted; wait for the importer to stop.')
    return {'uuid': uuid, 'safe_to_remove': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['list', 'mount', 'unmount'])
    parser.add_argument('uuid', nargs='?')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('This helper must run through its restricted sudo rule.')
    if args.operation != 'list' and (not args.uuid or not re.fullmatch('[A-Fa-f0-9-]{4,36}', args.uuid)):
        parser.error('A valid camera filesystem ID is required.')
    lock_fd = os.open('/run/lock/footage-card.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    lock_info = os.fstat(lock_fd)
    if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != 0:
        os.close(lock_fd)
        parser.error('Unsafe mount lock ownership.')
    with os.fdopen(lock_fd, 'r+') as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if args.operation == 'list':
                result = {'cards': list_cards()}
            elif args.operation == 'mount':
                result = mount_card(args.uuid)
            else:
                result = unmount_card(args.uuid)
            print(json.dumps(dict(result, ok=True)))
        except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
            print(json.dumps({'ok': False, 'error': str(error)}))
            raise SystemExit(1)


if __name__ == '__main__':
    main()
