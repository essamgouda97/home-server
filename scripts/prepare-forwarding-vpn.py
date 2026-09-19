#!/usr/bin/env python3
"""Validate and install the dormant Gluetun port-sync support on the server."""

from pathlib import Path
import shutil
import subprocess


def main():
    repo=Path(__file__).resolve().parents[1]
    secret=Path.home()/'.config/home-server/secrets/protonvpn.env'
    assert secret.is_file(),'Private Proton VPN env file is not provisioned'
    assert secret.stat().st_mode & 0o077 == 0,'Proton VPN env file must be mode 600'
    values={line.split('=',1)[0]:line.split('=',1)[1].strip() for line in secret.read_text().splitlines() if line and not line.startswith('#') and '=' in line}
    assert values.get('WIREGUARD_PRIVATE_KEY'),'WIREGUARD_PRIVATE_KEY is missing'
    state=Path('/mnt/server/vpn/gluetun');state.mkdir(parents=True,exist_ok=True,mode=0o700);state.chmod(0o700)
    units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
    for name in ('home-qbittorrent-port-sync.service','home-qbittorrent-port-sync.timer'):
        shutil.copy2(repo/'templates/systemd'/name,units/name)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    print('PASS Proton VPN credential shape and permissions')
    print('PASS Gluetun state and port-sync units prepared; migration remains inactive')


if __name__=='__main__':main()
