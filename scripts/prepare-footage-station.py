#!/usr/bin/env python3
"""Prepare a removable Pi boot card on Linux; inspect by default, --erase to write.

Requires an explicit stable USB by-id path and exact capacity. The official raw
image hash is checked before any card changes and against card read-back. Existing
non-ISO filesystem contents are archived before formatting. Archives and rendered
SSH provisioning live outside the public repository. Never accepts a system disk.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import uuid

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / 'config/footage-station'
CHUNK = 8 * 1024 * 1024


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def output(*args):
    return run(*args, capture_output=True, text=True).stdout


def hash_file(path, limit=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while limit is None or limit > 0:
            chunk = f.read(CHUNK if limit is None else min(CHUNK, limit))
            if not chunk:
                if limit:
                    raise ValueError('Unexpected end of image/device')
                break
            h.update(chunk)
            if limit is not None:
                limit -= len(chunk)
    return h.hexdigest()


def inspect(device, expected_size):
    if not str(device).startswith('/dev/disk/by-id/usb-') or not device.is_symlink():
        raise ValueError('Select a stable /dev/disk/by-id/usb-... whole-device link.')
    real = device.resolve(strict=True)
    if not stat.S_ISBLK(real.stat().st_mode):
        raise ValueError('Not a block device')
    disk = json.loads(output('lsblk', '--tree', '-b', '-J', '-o',
        'PATH,SIZE,MODEL,TRAN,RM,TYPE,FSTYPE,LABEL,MOUNTPOINTS', real))['blockdevices'][0]
    validate_disk(disk, expected_size)
    return real, disk


def validate_disk(disk, expected_size):
    if disk['type'] != 'disk' or disk['tran'] != 'usb' or not disk['rm']:
        raise ValueError('Refusing a non-removable, non-USB, or partition target')
    if int(disk['size']) != expected_size or not 8_000_000_000 <= expected_size <= 128_000_000_000:
        raise ValueError('Capacity differs from the explicitly selected boot card')
    if not disk.get('children'):
        raise ValueError('No partition tree found; cannot prove existing contents were backed up')
    for node in [disk, *disk.get('children', [])]:
        if node.get('children') and node is not disk:
            raise ValueError('Nested block-device holders are unsafe to overwrite')
        if node is not disk and node['type'] != 'part':
            raise ValueError('Target has non-partition holders')
        for mount in node.get('mountpoints', []) or []:
            if mount and not (mount.startswith('/media/') or mount.startswith('/run/media/')):
                raise ValueError('Target has a system or non-removable mount: ' + mount)


def seed(settings, public_keys, console_password_hash=None):
    keys = []
    for path in public_keys:
        for key in path.read_text().splitlines():
            if not key.strip():
                continue
            if not re.fullmatch(r'(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp\d+) [A-Za-z0-9+/=]+(?: .*)?', key):
                raise ValueError('Expected an OpenSSH PUBLIC key, without authorized_keys options')
            if key not in keys:
                keys.append(key)
    if not keys:
        raise ValueError('At least one SSH public key is required')
    files = [
        {'path': '/usr/local/sbin/footage-station-bootstrap', 'permissions': '0755',
         'content': (CONFIG / 'bootstrap.sh').read_text()},
        {'path': '/etc/systemd/system/footage-station-bootstrap.service', 'permissions': '0644',
         'content': (CONFIG / 'bootstrap.service').read_text()},
        {'path': '/etc/ssh/sshd_config.d/00-footage-station.conf', 'permissions': '0644',
         'content': 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n'},
    ]
    user = {'hostname': settings['hostname'], 'manage_etc_hosts': True,
        'timezone': settings['timezone'], 'locale': 'en_CA.UTF-8',
        'users': [{'name': settings['username'], 'groups': ['adm', 'sudo', 'plugdev'],
            'shell': '/bin/bash', 'lock_passwd': True,
            'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'ssh_authorized_keys': keys}],
        'disable_root': True, 'ssh_pwauth': False, 'enable_ssh': True,
        'ssh_deletekeys': True, 'ssh_genkeytypes': ['ed25519', 'rsa'],
        'package_update': False, 'package_upgrade': False, 'write_files': files,
        'runcmd': [['systemctl', 'enable', '--now', 'ssh'],
            ['systemctl', 'daemon-reload'],
            ['systemctl', 'enable', 'footage-station-bootstrap.service'],
            ['systemctl', 'start', '--no-block', 'footage-station-bootstrap.service']],
        'final_message': 'Footage station SSH ready; base package setup continues in systemd.'}
    if console_password_hash is not None:
        if not re.fullmatch(r'\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}', console_password_hash):
            raise ValueError('Console password must be a SHA-512 crypt hash from private storage.')
        user['users'][0]['passwd'] = console_password_hash
        user['users'][0]['lock_passwd'] = False
        # Unlocking console access does not enable SSH password authentication.
    # JSON is a strict subset of YAML; no third-party YAML serializer is needed.
    network = {'network': {'version': 2, 'renderer': 'NetworkManager',
        'ethernets': {'wired': {'match': {'name': 'e*'}, 'dhcp4': True,
            'dhcp6': True, 'optional': True}}}}
    return {'user-data': '#cloud-config\n' + json.dumps(user, indent=2) + '\n',
        'network-config': json.dumps(network, indent=2) + '\n',
        'meta-data': json.dumps({'instance-id': 'footage-pi-' + uuid.uuid4().hex,
            'local-hostname': settings['hostname']}) + '\n'}


def mount_partition(device, directory, fstype, writable=False):
    options = 'rw,nosuid,nodev,noexec' if writable else 'ro,nosuid,nodev,noexec'
    if fstype == 'ext4' and not writable:
        options += ',noload'
    run('mount', '-t', fstype, '-o', options, device, directory)


def backup_existing(real, disk, destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    (destination / 'device-before.json').write_text(json.dumps(disk, indent=2) + '\n')
    (destination / 'partition-table.sfdisk').write_text(output('sfdisk', '--dump', real))
    archives = []
    with tempfile.TemporaryDirectory(prefix='footage-card-backup-') as temporary:
        for part in disk.get('children', []):
            fs = part.get('fstype')
            if fs == 'iso9660':
                # Installer ISO is reproducible; save identity, not a redundant ISO.
                continue
            if not fs:
                # Preserve small unformatted boot partitions exactly.
                if int(part['size']) > 16 * 1024 * 1024:
                    raise ValueError('Unknown filesystem; cannot safely preserve existing contents')
                archive = destination / (Path(part['path']).name + '.raw')
                with open(part['path'], 'rb') as src, archive.open('xb') as dst:
                    shutil.copyfileobj(src, dst, CHUNK)
            else:
                if fs not in ('vfat', 'exfat', 'ext4'):
                    raise ValueError('Unsupported backup filesystem: ' + fs)
                mount_partition(part['path'], temporary, fs)
                archive = destination / (Path(part['path']).name + '.tar.gz')
                try:
                    run('tar', '--acls', '--xattrs', '--numeric-owner', '-czf', archive,
                        '-C', temporary, '.')
                    run('tar', '-tzf', archive, stdout=subprocess.DEVNULL)
                    # Compare extracted bytes/metadata against the read-only source.
                    run('tar', '--acls', '--xattrs', '--compare', '-zf', archive, '-C', temporary)
                finally:
                    run('umount', temporary)
            archives.append({'file': archive.name, 'sha256': hash_file(archive)})
    (destination / 'archives.json').write_text(json.dumps(archives, indent=2) + '\n')
    os.sync()
    print('Existing writable contents preserved:', destination, flush=True)


@contextmanager
def pause_automounter():
    """Prevent desktop automounts racing raw writes; restore the prior service state."""
    if not shutil.which('systemctl'):
        yield
        return
    unit = 'udisks2.service'
    loaded = output('systemctl', 'show', unit, '--property=LoadState', '--value').strip()
    enabled = subprocess.run(['systemctl', 'is-enabled', unit], capture_output=True, text=True).stdout.strip()
    if loaded == 'not-found' or enabled in ('masked', 'masked-runtime'):
        yield
        return
    active = subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0
    run('systemctl', 'mask', '--runtime', '--now', unit)
    try:
        yield
    finally:
        run('systemctl', 'unmask', '--runtime', unit)
        if active:
            run('systemctl', 'start', unit)


def prepare(args):
    if args.erase:
        if os.geteuid() != 0:
            raise ValueError('Writing the selected card requires sudo')
        with pause_automounter():
            return prepare_card(args)
    return prepare_card(args)


def prepare_card(args):
    settings = json.loads((CONFIG / 'image.json').read_text())
    password_hash = None
    if args.console_password_hash_file:
        info = args.console_password_hash_file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ValueError('Console password hash file must be private (mode 0600).')
        password_hash = args.console_password_hash_file.read_text().strip()
    seeds = seed(settings, args.public_key, password_hash)
    real, disk = inspect(args.device, args.expected_size)
    print(json.dumps(disk, indent=2), flush=True)
    if not args.erase:
        print('Inspection only. --erase explicitly authorizes replacement of this card.')
        return
    if os.geteuid() != 0:
        raise ValueError('Writing the selected card requires sudo')
    if args.image.stat().st_size != settings['extract_size']:
        raise ValueError('Raw image size does not match the pinned release')
    print('Verifying official raw image SHA-256...', flush=True)
    if hash_file(args.image) != settings['extract_sha256']:
        raise ValueError('Image checksum mismatch; card untouched')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = args.backup_root / stamp
    identity = real.stat().st_rdev
    # Re-read identity/mounts immediately before unmounting and backing up.
    current, disk = inspect(args.device, args.expected_size)
    if current != real or current.stat().st_rdev != identity:
        raise ValueError('Device identity changed')
    for node in reversed([disk, *disk.get('children', [])]):
        for mount in node.get('mountpoints', []) or []:
            if mount:
                run('umount', mount)
    backup_existing(real, disk, backup)
    current, disk = inspect(args.device, args.expected_size)
    if current != real or current.stat().st_rdev != identity:
        raise ValueError('Device identity changed after backup')
    if any(m for n in [disk, *disk.get('children', [])] for m in n.get('mountpoints', []) or []):
        raise ValueError('Card was remounted; refusing to write')
    print('Writing Raspberry Pi OS to', real, flush=True)
    # Opening r+b cannot create a regular file if the device disappears.
    with args.image.open('rb') as src, real.open('r+b', buffering=0) as dst:
        if os.fstat(dst.fileno()).st_rdev != identity:
            raise ValueError('Device changed before write')
        shutil.copyfileobj(src, dst, CHUNK)
        os.fsync(dst.fileno())
    run('blockdev', '--flushbufs', real)
    print('Reading back the complete written image...', flush=True)
    if hash_file(real, settings['extract_size']) != settings['extract_sha256']:
        raise ValueError('Card read-back checksum mismatch; do not boot this card')
    run('blockdev', '--rereadpt', real)
    run('udevadm', 'settle')
    table = json.loads(output('lsblk', '--tree', '-J', '-o', 'PATH,FSTYPE,LABEL', real))['blockdevices'][0]
    boot = next(p for p in table['children'] if p['fstype'] == 'vfat')
    with tempfile.TemporaryDirectory(prefix='footage-card-boot-') as temporary:
        mount_partition(boot['path'], temporary, 'vfat', writable=True)
        try:
            folder = Path(temporary)
            for required in ['config.txt', 'cmdline.txt', 'user-data', 'meta-data', 'network-config']:
                if not (folder / required).is_file():
                    raise ValueError('Image lacks expected cloudinit-rpi boot files: ' + required)
            for name, contents in seeds.items():
                (folder / name).write_text(contents)
            os.sync()
        finally:
            run('umount', temporary)
        # Verify persisted first-boot files after a fresh read-only mount.
        mount_partition(boot['path'], temporary, 'vfat')
        try:
            for name, contents in seeds.items():
                if (Path(temporary) / name).read_text() != contents:
                    raise ValueError('Boot configuration read-back differs: ' + name)
        finally:
            run('umount', temporary)
    report = {'prepared_at': stamp, 'device': str(args.device), 'capacity': args.expected_size,
        'image': settings, 'image_readback_verified': True,
        'boot_config_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k,v in seeds.items()},
        'hardware_boot_verified': False}
    (backup / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
    os.sync()
    print('PREPARED: image and boot config verified; all card filesystems unmounted.', flush=True)
    print('Move the card to the Pi microSD slot, connect Ethernet, then power it on.', flush=True)
    print('First boot target: ' + settings['username'] + '@' + settings['hostname'] + '.local')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', type=Path, required=True)
    parser.add_argument('--expected-size', type=int, required=True)
    parser.add_argument('--image', type=Path, required=True, help='Verified, decompressed .img')
    parser.add_argument('--public-key', type=Path, action='append', required=True)
    parser.add_argument('--console-password-hash-file', type=Path,
                        help='Private mode-0600 SHA-512 crypt hash; SSH stays key-only')
    parser.add_argument('--backup-root', type=Path, required=True)
    parser.add_argument('--erase', action='store_true')
    args = parser.parse_args()
    prepare(args)


if __name__ == '__main__':
    main()
