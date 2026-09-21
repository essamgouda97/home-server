#!/usr/bin/env python3
"""Keep ArabP2P jobs unlimited; never resume, add or delete a torrent.

Reads only client metadata, never media files. Logs counts, not names/passkeys.
Run periodically so newly imported jobs inherit the owner's tracker exception.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('seed', Path(__file__).with_name('check-seeding-policy.py'))
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    opener = seed.qbit_session()
    def get(path):
        return seed.get_json(seed.QBIT_URL + '/api/v2/' + path, opener=opener)
    selected = []
    for row in get('torrents/info'):
        trackers = get('torrents/trackers?' + urllib.parse.urlencode({'hash': row['hash']}))
        hosts = [urllib.parse.urlsplit(t['url']).hostname or '' for t in trackers]
        if any(h == 'arabp2p.net' or h.endswith('.arabp2p.net') for h in hosts):
            selected.append(row)
    keys = ['ratio_limit', 'seeding_time_limit', 'inactive_seeding_time_limit']
    changed = [r for r in selected if any(r.get(k) != -1 for k in keys)]
    if changed and args.apply:
        os.umask(0o077)
        dest = Path.home()/'.local/state/home-server-maintenance/arabp2p-seeding'
        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = dest/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        backup.write_text(json.dumps([{k:r.get(k) for k in ['hash', *keys]} for r in changed]))
        payload = urllib.parse.urlencode({
            'hashes': '|'.join(r['hash'] for r in changed), 'ratioLimit': -1,
            'seedingTimeLimit': -1, 'inactiveSeedingTimeLimit': -1,
            'shareLimitAction': 'Stop'}).encode()
        with opener.open(urllib.request.Request(seed.QBIT_URL+'/api/v2/torrents/setShareLimits', data=payload), timeout=30) as response:
            assert response.status == 200, 'Share-limit update failed'
        actual = {r['hash']:r for r in get('torrents/info')}
        assert all(all(actual[r['hash']].get(k) == -1 for k in keys) for r in changed), 'Share-limit readback failed'
    print(f'ArabP2P jobs={len(selected)}; unlimited={len(selected) if args.apply else len(selected)-len(changed)}; changed={len(changed) if args.apply else 0}')
    if changed and not args.apply:
        raise SystemExit('FAIL ArabP2P seed-limit exception needs applying')


if __name__ == '__main__':
    main()
