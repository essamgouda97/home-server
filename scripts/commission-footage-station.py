#!/usr/bin/env python3
"""Commission a booted Ethernet Pi from the Mac; never formats or erases disks."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[1]


def require_stable_power(response):
    text = response.decode().strip()
    if not re.fullmatch(r'throttled=0x[0-9a-fA-F]{1,8}', text):
        raise ValueError('Could not verify Pi power status; no importer installed.')
    flags = int(text.split('=', 1)[1], 16)
    # Firmware bits 0 and 16 mean current and earlier undervoltage respectively.
    if flags & ((1 << 0) | (1 << 16)):
        raise ValueError('Pi reports undervoltage during this boot. Correct its power supply/cable and reboot before commissioning.')


def run(host, command, data=None):
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host, command],
                            input=data, capture_output=True, check=True)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pi', default='egouda@footage-pi.local')
    parser.add_argument('--server', default='home-server')
    args = parser.parse_args()
    expected = json.loads((REPO/'config/footage-station/image.json').read_text())['target_model']
    model = run(args.pi, 'cat /proc/device-tree/model').decode().rstrip('\x00\n')
    if not model.startswith(expected + ' Rev '):
        raise SystemExit('Target is not the expected ' + expected + '; no changes made.')
    require_stable_power(run(args.pi, 'sudo -n vcgencmd get_throttled'))
    run(args.pi, 'test -e /var/lib/footage-station/base-ready && sudo -n true')
    settings = dict(line.split('=',1) for line in (REPO/'server.conf').read_text().splitlines()
                    if line and not line.startswith('#') and '=' in line)
    remote_repo = run(args.server, 'pwd').decode().strip() + '/workspace/home-server'
    run(args.server, 'test -f ' + shlex.quote(remote_repo + '/services/footage-station/receiver.py'))
    key = run(args.server, 'cat /etc/ssh/ssh_host_ed25519_key.pub').decode().split()
    if len(key) < 2 or key[0] != 'ssh-ed25519':
        raise SystemExit('Could not obtain authenticated server host key.')
    config = {'host':'egouda@'+settings['SERVER_IP'],
              'identity':'/var/lib/footage-station/id_ed25519',
              'known_hosts':'/etc/footage-station/known_hosts'}
    with tempfile.TemporaryDirectory(prefix='footage-commission-') as temp:
        staging=Path(temp)
        files=['station.py','transfer.py','storage.py','card_helper.py']
        for name in files:
            (staging/name).write_bytes((REPO/'services/footage-station'/name).read_bytes())
        (staging/'station.service').write_bytes((REPO/'config/footage-station/station.service').read_bytes())
        (staging/'config.json').write_text(json.dumps(config)+'\n')
        (staging/'known_hosts').write_text(settings['SERVER_IP']+' '+key[0]+' '+key[1]+'\n')
        archive=staging/'setup.tar'
        with tarfile.open(archive,'w') as tar:
            for name in [*files,'station.service','config.json','known_hosts']:
                tar.add(staging/name, arcname=name)
        remote_temp=run(args.pi,'mktemp -d /tmp/footage-setup.XXXXXXXX').decode().strip()
        try:
            run(args.pi, 'tar -xf - -C '+shlex.quote(remote_temp), archive.read_bytes())
            install=r'''
set -eu
src="$1"
systemctl stop footage-station.service 2>/dev/null || true
id footage-station >/dev/null 2>&1 || useradd --system --home-dir /var/lib/footage-station --shell /usr/sbin/nologin footage-station
install -d -o root -g root -m 755 /opt/footage-station /etc/footage-station
install -d -o footage-station -g footage-station -m 700 /var/lib/footage-station
for name in station.py transfer.py storage.py; do install -o root -g root -m 644 "$src/$name" /opt/footage-station/; done
install -o root -g root -m 755 "$src/card_helper.py" /usr/local/sbin/footage-card
install -o root -g root -m 644 "$src/config.json" "$src/known_hosts" /etc/footage-station/
install -o root -g root -m 644 "$src/station.service" /etc/systemd/system/footage-station.service
printf '%s\n' 'footage-station ALL=(root) NOPASSWD: /usr/local/sbin/footage-card' > /etc/sudoers.d/footage-station
chmod 440 /etc/sudoers.d/footage-station
visudo -cf /etc/sudoers.d/footage-station >/dev/null
if [ ! -f /var/lib/footage-station/id_ed25519 ]; then
  sudo -u footage-station ssh-keygen -q -t ed25519 -N '' -C footage-station -f /var/lib/footage-station/id_ed25519
fi
systemctl daemon-reload
'''
            run(args.pi, 'sudo -n sh -s -- '+shlex.quote(remote_temp), install.encode())
            public=run(args.pi,'sudo -n cat /var/lib/footage-station/id_ed25519.pub').decode().split()
            if len(public)<2 or public[0]!='ssh-ed25519':
                raise SystemExit('Unexpected station key format.')
            forced=' '.join(shlex.quote(v) for v in ['/usr/bin/python3','-s',remote_repo+'/services/footage-station/receiver.py','--root',settings['CREATIVE_ROOT']])
            entry='restrict,command="'+forced.replace('\\','\\\\').replace('"','\\"')+'" '+public[0]+' '+public[1]+' footage-station\n'
            # Replace only this appliance marker. Never replace unrelated owner keys.
            updater="""from pathlib import Path
import os,sys
p=Path.home()/'.ssh/authorized_keys'
p.parent.mkdir(mode=0o700,exist_ok=True)
lines=p.read_text().splitlines() if p.exists() else []
entry=sys.stdin.read().strip()
lines=[line for line in lines if not line.endswith(' footage-station')]
tmp=p.with_name('authorized_keys.footage-new')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as out:
 out.write('\\n'.join(lines+[entry])+'\\n');out.flush();os.fsync(out.fileno())
os.replace(tmp,p)
"""
            run(args.server, 'python3 -c '+shlex.quote(updater), entry.encode())
            run(args.pi, 'sudo -n systemctl enable footage-station.service && sudo -n systemctl restart footage-station.service')
            status=run(args.pi,'systemctl is-active footage-station.service').decode().strip()
            print('Pi service:',status)
            print('Open http://ingest.lan to see the station heartbeat, then insert a camera card.')
        finally:
            run(args.pi,'rm -rf -- '+shlex.quote(remote_temp))


if __name__ == '__main__':
    main()
