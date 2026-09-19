#!/usr/bin/env python3
"""Verify Gluetun port forwarding from inside qBittorrent's VPN namespace."""

from __future__ import annotations

import http.cookiejar
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request


BASE = 'http://127.0.0.1:15080'
PORT_FILE = Path('/mnt/server/vpn/gluetun/forwarded_port')


def main():
    port_text = PORT_FILE.read_text().strip()
    assert port_text.isdigit() and 1024 <= int(port_text) <= 65535, 'Invalid forwarded port file'
    port = int(port_text)
    password = json.loads((Path.home()/'.config/home-server/secrets/service-passwords.json').read_text())['torrents']
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        BASE+'/api/v2/auth/login',
        data=urllib.parse.urlencode({'username':'egouda','password':password}).encode(),
        headers={'Origin':BASE,'Referer':BASE+'/'},
    )
    with opener.open(req,timeout=20) as response:assert response.read() in (b'Ok.',b'')
    with opener.open(BASE+'/api/v2/app/preferences',timeout=20) as response:listen=json.load(response)['listen_port']
    assert listen==port, 'qBittorrent does not match the VPN forwarded port'
    probe=subprocess.run(
        ['docker','exec','qbittorrent','sh','-c',
         'if command -v curl >/dev/null; then curl -fsS --max-time 20 "$1"; '
         'else wget -qO- --timeout=20 "$1"; fi','probe',
         'https://portcheck.transmissionbt.com/'+str(port)],
        text=True,capture_output=True,timeout=30,
    )
    assert probe.returncode==0 and probe.stdout.strip().startswith('1'), 'Forwarded peer port is externally closed'
    host_ip=urllib.request.urlopen('https://api.ipify.org',timeout=20).read().strip()
    vpn_ip=subprocess.check_output(
        ['docker','exec','qbittorrent','sh','-c',
         'if command -v curl >/dev/null; then curl -fsS --max-time 20 https://api.ipify.org; '
         'else wget -qO- --timeout=20 https://api.ipify.org; fi'],timeout=30,
    ).strip()
    assert host_ip and vpn_ip and host_ip != vpn_ip, 'VPN egress is not distinct from the host'
    print('PASS forwarded peer port is externally open')
    print('PASS qBittorrent listen port matches Gluetun')
    print('PASS VPN egress differs from host; addresses withheld')
    return 0


if __name__=='__main__':sys.exit(main())

