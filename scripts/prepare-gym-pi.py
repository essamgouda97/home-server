#!/usr/bin/env python3
"""Configure an already initialized Raspberry Pi OS card offline; never flash it.

Run on Linux as root. Wi-Fi JSON must be a private file outside the repository
with keys ssid and password. Only --apply writes to the selected removable card.
"""
import argparse
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / 'config/gym-pi'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True)
    # Netplan errors can contain passwords: never echo subprocess output on error.
    require(result.returncode == 0, f'{args[0]} failed (output withheld)')
    return result.stdout


def network_config(credentials):
    ssid, password = credentials['ssid'], credentials['password']
    require(isinstance(ssid, str) and 1 <= len(ssid.encode()) <= 32,
            'SSID must contain 1–32 bytes')
    require(isinstance(password, str) and (
        8 <= len(password) <= 63 or re.fullmatch(r'[0-9a-fA-F]{64}', password)),
        'Use an 8–63 character Wi-Fi password or 64 digit hexadecimal PSK')
    require(not any(ord(c) < 32 for c in ssid + password), 'Control characters are unsupported')
    return json.dumps({'network': {
        'version': 2, 'renderer': 'NetworkManager',
        'wifis': {'wlan0': {
            'dhcp4': True, 'dhcp6': True, 'optional': True,
            'regulatory-domain': 'CA',
            'access-points': {ssid: {'password': password, 'band': '2.4GHz'}}}},
    }}, indent=2) + '\n'


def render_check(network):
    with tempfile.TemporaryDirectory(prefix='gym-pi-netplan-') as tmp:
        folder = Path(tmp) / 'etc/netplan'
        folder.mkdir(parents=True)
        source = folder / '90-gym-pi.yaml'
        source.write_text(network)
        source.chmod(0o600)
        command('netplan', 'generate', '--root-dir', tmp)
        profiles = list((Path(tmp) / 'run/NetworkManager/system-connections').glob('*.nmconnection'))
        require(len(profiles) == 1, 'Expected exactly one generated Wi-Fi profile')
        profile = configparser.ConfigParser(interpolation=None)
        profile.read(profiles[0])
        require(profile['connection']['interface-name'] == 'wlan0', 'Wrong Wi-Fi interface')
        require(profile['wifi']['band'] == 'bg', 'Expected 2.4 GHz')
        require(profile['ipv4']['method'] == 'auto', 'Expected DHCP')
        require(profile['wifi-security']['key-mgmt'] == 'wpa-psk', 'Expected personal Wi-Fi security')
        require(profile['connection'].get('autoconnect', 'true') != 'false', 'Autoconnect disabled')


def check_mount(root, disk, fstype):
    require(root != Path('/') and root.is_mount(), 'Expected a separate mounted card partition')
    mount = json.loads(command('findmnt', '-J', '-M', root))['filesystems'][0]
    require(mount['fstype'] == fstype and 'rw' in mount['options'].split(','),
            'Wrong filesystem type or partition is not writable')
    require(any(p['path'] == mount['source'] and p['type'] == 'part'
                for p in disk.get('children', [])), 'Mount does not belong to selected card')


def safe_path(root, relative):
    path = root / relative
    require(not path.is_symlink() and path.resolve().is_relative_to(root),
            'Refusing symlink or path outside card')
    return path


def write(root, relative, content, mode=0o644):
    path = safe_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)
    require(path.read_text() == content, 'Written file differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True, type=Path)
    parser.add_argument('--expected-size', required=True, type=int)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--boot', required=True, type=Path)
    parser.add_argument('--wifi-json', required=True, type=Path)
    parser.add_argument('--backup-dir', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'Run as root on the Linux maintenance host')
    os.umask(0o077)
    require(str(args.device).startswith('/dev/disk/by-id/usb-') and args.device.is_symlink(),
            'Use the stable USB whole-device link')
    disk = json.loads(command('lsblk', '--tree', '-b', '-J', '-o',
                             'PATH,SIZE,TRAN,RM,TYPE', args.device))['blockdevices'][0]
    require(disk['tran'] == 'usb' and disk['rm'] and disk['type'] == 'disk',
            'Expected a removable USB card')
    require(disk['size'] == args.expected_size and 8_000_000_000 <= args.expected_size <= 128_000_000_000,
            'Card capacity does not match')
    root, boot = args.root.resolve(strict=True), args.boot.resolve(strict=True)
    check_mount(root, disk, 'ext4')
    check_mount(boot, disk, 'vfat')
    require((root / 'etc/hostname').read_text().strip() in ('footage-pi', 'gym-pi'),
            'Unexpected existing card identity')
    require('ID=raspbian' in (root / 'etc/os-release').read_text() or
            (root / 'etc/rpi-issue').exists(), 'Expected Raspberry Pi OS')
    require((boot / 'bcm2710-rpi-3-b.dtb').is_file() and (boot / 'kernel8.img').is_file(),
            'Missing Pi 3B 64 bit boot files')
    require((root / 'home/egouda/.ssh/authorized_keys').stat().st_size > 0,
            'Seed SSH authorized keys before provisioning')
    require(not args.wifi_json.is_symlink() and
            stat.S_IMODE(args.wifi_json.stat().st_mode) & 0o077 == 0 and
            not args.wifi_json.resolve().is_relative_to(REPO),
            'Wi-Fi credentials must be a private file outside Git')
    network = network_config(json.loads(args.wifi_json.read_text()))
    render_check(network)
    old = list((root / 'etc/netplan').glob('*.yaml')) + list((root / 'etc/netplan').glob('*.yml'))
    for path in old:
        safe_path(root, str(path.relative_to(root)))
        require(path.name in ('50-cloud-init.yaml', '90-footage.yaml', '90-gym-pi.yaml') or
                (path.name.startswith('90-NM-') and 'netplan-wired' in path.read_text()),
                'Unexpected Netplan profile; inspect before replacing')
    require(not list((root / 'etc/NetworkManager/system-connections').glob('*')),
            'Unexpected saved NetworkManager profiles; inspect before replacing')
    print('Validated removable card, Pi 3B boot files, SSH keys and generated Wi-Fi profile.')
    if not args.apply:
        print('Inspection only; add --apply to configure the card.')
        return
    backup = args.backup_dir.resolve() / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    require(not any(backup.is_relative_to(p) for p in (REPO, root, boot)),
            'Backups must be outside Git and the card')
    backup.mkdir(parents=True, mode=0o700)
    command('tar', '--acls', '--xattrs', '-czf', backup / 'root-config.tar.gz',
            '-C', root, 'etc', 'var/lib/systemd/rfkill', 'var/lib/NetworkManager')
    seeds = [name for name in ('user-data', 'network-config', 'meta-data') if (boot / name).exists()]
    if seeds:
        command('tar', '-czf', backup / 'boot-seed.tar.gz', '-C', boot, *seeds)
    command('tar', '-tzf', backup / 'root-config.tar.gz')
    # The card has completed cloud-init previously; direct persistent config is
    # required. Prevent its old footage-pi seed from restoring the old identity.
    for path in old:
        path.unlink()
    write(root, 'etc/netplan/90-gym-pi.yaml', network, 0o600)
    write(root, 'etc/cloud/cloud-init.disabled', '# Provisioned offline by prepare-gym-pi.py\n')
    write(root, 'etc/cloud/cloud.cfg.d/99-gym-pi-network.cfg', 'network: {config: disabled}\n')
    write(root, 'etc/hostname', 'gym-pi\n')
    hosts = (root / 'etc/hosts').read_text()
    hosts = re.sub(r'(?m)^127\.0\.1\.1\s+.*$', '127.0.1.1\tgym-pi', hosts)
    if not re.search(r'(?m)^127\.0\.1\.1\s', hosts):
        hosts += '\n127.0.1.1\tgym-pi\n'
    write(root, 'etc/hosts', hosts)
    write(root, 'etc/ssh/sshd_config.d/00-gym-pi.conf',
          'PubkeyAuthentication yes\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n')
    write(root, 'etc/NetworkManager/conf.d/90-gym-pi.conf', '[connection]\nwifi.powersave=2\n')
    write(root, 'var/lib/NetworkManager/NetworkManager.state',
          '[main]\nNetworkingEnabled=true\nWirelessEnabled=true\nWWANEnabled=true\n', 0o600)
    write(root, 'etc/modprobe.d/gym-pi-regdomain.conf', 'options cfg80211 ieee80211_regdom=CA\n')
    write(root, 'etc/systemd/journald.conf.d/gym-pi.conf',
          '[Journal]\nStorage=persistent\nSystemMaxUse=64M\nRuntimeMaxUse=16M\n')
    for path in (root / 'var/lib/systemd/rfkill').glob('*'):
        if path.name.endswith((':wlan', ':bluetooth')):
            write(root, str(path.relative_to(root)), '0\n', 0o600)
    for source, destination, mode in [
        ('bootstrap.sh', 'usr/local/sbin/gym-pi-bootstrap', 0o755),
        ('bootstrap.service', 'etc/systemd/system/gym-pi-bootstrap.service', 0o644),
        ('radio.service', 'etc/systemd/system/gym-pi-radio.service', 0o644),
    ]:
        write(root, destination, (CONFIG / source).read_text(), mode)
    for unit in ('footage-station-bootstrap.service', 'footage-network-report.timer'):
        if (root / 'etc/systemd/system' / unit).exists():
            command('systemctl', '--root', root, 'disable', unit)
    command('systemctl', '--root', root, 'enable', 'NetworkManager', 'ssh', 'avahi-daemon',
            'bluetooth', 'gym-pi-radio.service', 'gym-pi-bootstrap.service')
    for name in seeds:
        write(boot, name, '# Archived on the maintenance host; cloud-init disabled on this card.\n')
    write(root, 'etc/gym-pi-provisioning.json', json.dumps({
        'hostname': 'gym-pi', 'model': 'Raspberry Pi 3 Model B',
        'wifi_band': '2.4GHz', 'country': 'CA', 'ssh_user': 'egouda',
        'boot_network_verified': False,
    }, indent=2) + '\n')
    render_check((root / 'etc/netplan/90-gym-pi.yaml').read_text())
    require(stat.S_IMODE((root / 'etc/netplan/90-gym-pi.yaml').stat().st_mode) == 0o600,
            'Wi-Fi file must be mode 0600')
    os.sync()
    print(f'Configured gym-pi. Private configuration backup: {backup}')
    print('Unmount both card partitions before removal. Physical boot verification is pending.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        # Avoid a traceback containing variables/secret configuration.
        raise SystemExit(str(error)) from None
