#!/usr/bin/env python3
"""Synchronize Gluetun's assigned port into qBittorrent without logging secrets."""

from __future__ import annotations

import http.cookiejar
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request


PORT_FILE = Path('/mnt/server/vpn/gluetun/forwarded_port')
BASE = 'http://127.0.0.1:15080'


def main():
    port_text = PORT_FILE.read_text().strip()
    if not port_text.isdigit() or not 1024 <= int(port_text) <= 65535:
        raise SystemExit('Forwarded-port file is missing or invalid')
    port = int(port_text)
    secrets = Path.home() / '.config/home-server/secrets/service-passwords.json'
    password = json.loads(secrets.read_text())['torrents']
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login = urllib.request.Request(
        BASE + '/api/v2/auth/login',
        data=urllib.parse.urlencode({'username': 'egouda', 'password': password}).encode(),
        headers={'Origin': BASE, 'Referer': BASE + '/'},
    )
    with opener.open(login, timeout=20) as response:
        if response.read() not in (b'Ok.', b''):
            raise SystemExit('qBittorrent rejected the runtime recovery credential')
    with opener.open(BASE + '/api/v2/app/preferences', timeout=20) as response:
        current = json.load(response).get('listen_port')
    if current != port:
        prefs = {'listen_port': port, 'random_port': False, 'upnp': False}
        payload = urllib.parse.urlencode({'json': json.dumps(prefs)}).encode()
        with opener.open(urllib.request.Request(BASE + '/api/v2/app/setPreferences', data=payload), timeout=20):
            pass
        reannounce = urllib.parse.urlencode({'hashes': 'all'}).encode()
        with opener.open(urllib.request.Request(BASE + '/api/v2/torrents/reannounce', data=reannounce), timeout=20):
            pass
        print('Forwarded port synchronized and torrents reannounced.')
    else:
        print('Forwarded port already synchronized.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

