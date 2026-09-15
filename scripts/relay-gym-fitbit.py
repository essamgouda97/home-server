#!/usr/bin/env python3
"""Pull the gym Pi BLE snapshot into Life Dashboard over authenticated SSH."""
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path(__file__).resolve().parents[1]
LIMIT = 524288
STATUSES = {'starting', 'scanning', 'connecting', 'live', 'bluetooth-unavailable', 'error'}


def validate(payload):
    if len(payload) > LIMIT:
        raise ValueError('Oversize snapshot')
    data = json.loads(payload)
    if data.get('schemaVersion') != 2 or data.get('status') not in STATUSES:
        raise ValueError('Unsupported snapshot')
    for key in ('observedAtMs', 'updatedAtMs'):
        value = data.get(key)
        if value is not None and (type(value) not in (int, float) or value < 0
                                  or value > time.time() * 1000 + 10000):
            raise ValueError('Invalid snapshot timestamp')
    bpm = data.get('bpm')
    if bpm is not None and (type(bpm) is not int or not 0 <= bpm <= 65535):
        raise ValueError('Invalid BPM')
    if not isinstance(data.get('recentSamples'), list) or len(data['recentSamples']) > 90:
        raise ValueError('Unbounded history')
    return data


def mark_freshness(data, now_ms):
    result = dict(data, receiver='gym-pi')
    age = now_ms - (data.get('observedAtMs') or 0)
    heartbeat_age = now_ms - (data.get('updatedAtMs') or 0)
    if result['status'] == 'live' and not (
            data.get('observedAtMs') is not None and -10000 <= age < 12000
            and -10000 <= heartbeat_age < 15000):
        result['status'] = 'scanning'
    return result


def write_atomic(path, payload):
    temp = path.with_suffix('.relay.tmp')
    temp.write_bytes(payload)
    temp.chmod(0o600)
    temp.replace(path)


def main():
    os.umask(0o077)
    settings = dict(line.split('=', 1) for line in (REPO / 'server.conf').read_text().splitlines()
                    if line and not line.startswith('#') and '=' in line)
    folder = Path(settings['LIFE_DASHBOARD_DATA']) / 'data/bridge'
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            # The Pi is already commissioned with this server's public SSH key.
            # head bounds even an unexpected file before it crosses the connection.
            result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=3', 'egouda@gym-pi.local',
                'head -c 524289 /var/lib/gym-pi/fitbit-live.json'], capture_output=True, timeout=5)
            if result.returncode == 0:
                validate(result.stdout)
                write_atomic(folder / 'fitbit-gym-pi.json', result.stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        try:
            with (folder / 'fitbit-gym-pi.json').open('rb') as stream:
                selected = mark_freshness(validate(stream.read(LIMIT + 1)), time.time() * 1000)
            write_atomic(folder / 'fitbit-live.json', json.dumps(selected).encode() + b'\n')
        except (OSError, ValueError):
            pass
        time.sleep(2)


if __name__ == '__main__':
    main()
