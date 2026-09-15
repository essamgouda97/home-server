#!/usr/bin/env python3
"""Read-only first-boot checks. Pass user@IP if footage-pi.local is not resolved."""
import argparse
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('host', nargs='?', default='egouda@footage-pi.local')
parser.add_argument('--jump', help='Optional existing SSH alias, e.g. home-server')
args = parser.parse_args()
if args.host.startswith('-') or (args.jump and args.jump.startswith('-')):
    parser.error('SSH host must not be an option')
command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
           '-o', 'StrictHostKeyChecking=accept-new']
if args.jump:
    command += ['-J', args.jump]
command += [args.host, '''set -eu
hostname
uname -m
cat /etc/os-release
printf '\\nHardware: '
tr -d '\\000' < /proc/device-tree/model
printf '\\n'
ip -br address
sudo -n vcgencmd get_throttled
sudo -n vcgencmd measure_temp
sudo -n passwd -S egouda
cloud-init status --long || true
systemctl is-active ssh
systemctl status footage-station-bootstrap --no-pager || true
test -f /var/lib/footage-station/base-ready
cat /var/lib/footage-station/base-ready
sudo -n sshd -T | sed -n '/^passwordauthentication /p; /^kbdinteractiveauthentication /p; /^permitrootlogin /p'
findmnt /
lsblk -o NAME,SIZE,TRAN,RM,FSTYPE,LABEL,MOUNTPOINTS
command -v python3
command -v rsync
printf '\\nBASE_READY: import application commissioning is the next stage.\\n'
''']
raise SystemExit(subprocess.run(command).returncode)
