#!/usr/bin/env python3
"""Server-only bridge health/auth/input checks; no model request or quota use."""
from pathlib import Path
import urllib.request
import urllib.error

repo = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (repo/'server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
token = (Path(settings['HOME_SERVER_SECRETS_DIR'])/'codex_home_token').read_text().strip()
cases = [('/health', None, {}, 200),
         ('/conversation', b'{}', {}, 401),
         ('/conversation', b'{}', {'Authorization':'Bearer invalid'}, 401),
         ('/conversation', b'null', {'Authorization':'Bearer '+token}, 400),
         ('/conversation', b'{broken', {'Authorization':'Bearer '+token}, 400),
         ('/conversation', b' '*524289, {'Authorization':'Bearer '+token}, 413)]
for path, data, headers, expected in cases:
    request = urllib.request.Request('http://127.0.0.1:18790'+path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    if status != expected:
        raise SystemExit('Bridge check failed: expected HTTP '+str(expected)+' got '+str(status))
print('PASS: Codex bridge health, authentication and malformed/oversized input checks.')
