#!/usr/bin/env python3
"""Check the real Rust snapshot against the running Life Dashboard API contract."""
import argparse
import json
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require-live', action='store_true')
args = parser.parse_args()


def remote(host, command):
    return subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                                    host, command], timeout=15, text=True)


assert remote('egouda@gym-pi.local', 'systemctl is-active gym-heart-rate').strip() == 'active'
snapshot = json.loads(remote('egouda@gym-pi.local', 'cat /var/lib/gym-pi/fitbit-live.json'))
required = {'schemaVersion', 'status', 'deviceName', 'bpm', 'observedAtMs', 'updatedAtMs',
            'sensorContactSupported', 'sensorContactDetected', 'energyExpendedKilojoules',
            'rrIntervalsMilliseconds', 'rssiDbm', 'rssiObservedAtMs', 'recentSamples', 'message'}
assert required <= snapshot.keys()
assert snapshot['receiver'] == 'gym-pi' and len(snapshot['recentSamples']) <= 90
assert remote('home-server', 'systemctl --user is-active gym-fitbit-relay').strip() == 'active'
api = json.loads(remote('home-server', 'curl -fsS http://127.0.0.1:3030/api/health/fitbit/live'))
assert api['bridgeAvailable'], 'Dashboard rejected the snapshot or heartbeat is stale'
if args.require_live:
    now = time.time() * 1000
    for state in (snapshot, api):
        assert state['status'] == 'live' and state['observedAtMs'] is not None
        assert -10000 <= now - state['observedAtMs'] < 12000
    assert snapshot['recentSamples'], 'No physical Bluetooth observations recorded'
print('PASS Rust service, bounded snapshot schema, SSH relay and dashboard API')
print('PASS fresh physical Bluetooth observations' if args.require_live else 'Live reception not required by this check')
