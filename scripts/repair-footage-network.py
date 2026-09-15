#!/usr/bin/env python3
"""Apply the repository Ethernet configuration to an offline footage-pi card.

Mount its root filesystem read-write first. This never formats or reflashes it.
Requires the exact removable USB device, capacity, mounted root, and --apply.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CONFIG = Path(__file__).resolve().parents[1] / 'config/footage-station'


def command(*args):
    return subprocess.check_output(list(map(str, args)), text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--device', required=True, type=Path)
    parser.add_argument('--expected-size', required=True, type=int)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root on the maintenance host.')
    if not str(args.device).startswith('/dev/disk/by-id/usb-') or not args.device.is_symlink():
        parser.error('Use the stable USB whole-device link.')
    disk = json.loads(command('lsblk', '--tree', '-b', '-J', '-o',
                             'PATH,SIZE,TRAN,RM,TYPE,FSTYPE', args.device))['blockdevices'][0]
    assert disk['tran'] == 'usb' and disk['rm'] and disk['type'] == 'disk'
    assert disk['size'] == args.expected_size and 8_000_000_000 <= args.expected_size <= 128_000_000_000
    root = args.root.resolve(strict=True)
    assert root != Path('/') and root.is_mount()
    mount = json.loads(command('findmnt', '-J', '-M', root))['filesystems'][0]
    assert mount['fstype'] == 'ext4'
    assert any(p['path'] == mount['source'] and p['type'] == 'part' for p in disk['children'])
    assert (root / 'etc/hostname').read_text().strip() == 'footage-pi'
    network = (CONFIG / 'network.json').read_text()
    # Exercise actual Netplan rendering without applying host networking.
    with tempfile.TemporaryDirectory(prefix='footage-network-check-') as tmp:
        folder = Path(tmp) / 'etc/netplan'
        folder.mkdir(parents=True)
        p = folder / '90-footage.yaml'
        p.write_text(network)
        p.chmod(0o600)
        subprocess.run(['netplan', 'generate', '--root-dir', tmp], check=True)
        profile = (Path(tmp) / 'run/NetworkManager/system-connections/netplan-eth0.nmconnection').read_text()
        assert 'interface-name=eth0' in profile and 'method=auto' in profile
    old = list((root / 'etc/netplan').glob('*.yaml')) + list((root / 'etc/netplan').glob('*.yml'))
    # Only replace this station's known Ethernet-only profiles.
    for p in old:
        text = p.read_text()
        assert not p.is_symlink() and 'wifis' not in text and 'ethernets' in text
        assert p.name in ('50-cloud-init.yaml', '90-footage.yaml') or (
            p.name.startswith('90-NM-') and 'netplan-wired' in text)
    print('Validated selected card, offline root, and eth0 DHCP profile.')
    if not args.apply:
        print('Inspection only; --apply writes configuration.')
        return
    assert 'rw' in mount['options'].split(',')
    record = root / ('var/lib/footage-station/network-repair/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    record.mkdir(parents=True, mode=0o700)
    for p in old:
        shutil.copy2(p, record / p.name)
        p.unlink()
    files = {
        'etc/netplan/90-footage.yaml': (network, 0o600),
        'etc/cloud/cloud.cfg.d/99-footage-network.cfg': ('network: {config: disabled}\n', 0o644),
    }
    for source, target, mode in [
        ('journald.conf', 'etc/systemd/journald.conf.d/footage.conf', 0o644),
        ('network-report.sh', 'usr/local/sbin/footage-network-report', 0o755),
        ('network-report.service', 'etc/systemd/system/footage-network-report.service', 0o644),
        ('network-report.timer', 'etc/systemd/system/footage-network-report.timer', 0o644),
    ]:
        files[target] = ((CONFIG / source).read_text(), mode)
    for name, (content, mode) in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        assert not p.is_symlink()
        p.write_text(content)
        p.chmod(mode)
        assert p.read_text() == content
    subprocess.run(['systemctl', '--root', str(root), 'enable', 'NetworkManager', 'ssh',
                    'avahi-daemon', 'footage-network-report.timer'], check=True)
    os.sync()
    (record / 'result.json').write_text(json.dumps({
        'eth0_dhcp_installed': True, 'persistent_diagnostics_installed': True,
        'hardware_network_verified': False}) + '\n')
    print('Offline repair applied. Unmount and safely eject before booting.')


if __name__ == '__main__':
    main()
