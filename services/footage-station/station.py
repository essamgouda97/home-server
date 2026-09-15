#!/usr/bin/env python3
"""Headless Pi appliance. Poll removable cards, import DCIM, unmount on success."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from transfer import Connection, import_folder, ssh_command

HELPER = '/usr/local/sbin/footage-card'


def helper(operation, uuid=None):
    command = ['sudo', '-n', HELPER, operation] + ([uuid] if uuid else [])
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise ValueError('Card helper failed. Check the station service log.') from None
    if result.returncode or not data.get('ok'):
        raise ValueError(data.get('error', 'Card helper rejected operation.'))
    return data


class Station:
    def __init__(self, command, mount_helper=helper, importer=import_folder, now=time.monotonic):
        self.command, self.helper, self.importer, self.now = command, mount_helper, importer, now
        self.finished = set()
        self.failures = {}
        self.retry_nonce = None
        self.event = {'phase': 'waiting', 'safe_to_remove': False}

    def publish(self):
        connection = Connection(self.command)
        try:
            policy = connection.request({'op': 'status', 'event': self.event})
            nonce = policy.get('retry_nonce')
            if nonce != self.retry_nonce:
                self.failures.clear()
                self.retry_nonce = nonce
        finally:
            connection.close()

    def tick(self):
        cards = self.helper('list')['cards']
        present = {card['uuid'] for card in cards}
        self.finished.intersection_update(present)
        self.failures = {key: value for key, value in self.failures.items() if key in present}
        if not cards:
            self.event = {'phase': 'waiting', 'safe_to_remove': False, 'file': '', 'error': ''}
        self.publish()
        for card in cards:
            uuid = card['uuid']
            if uuid in self.finished or self.failures.get(uuid, (0, 0))[0] > self.now():
                continue
            try:
                self.event = {'phase': 'mounting', 'source_uuid': uuid, 'safe_to_remove': False, 'error': ''}
                self.publish()
                mounted = self.helper('mount', uuid)
                source = Path(mounted['path']) / 'DCIM'
                if source.is_symlink() or not source.is_dir():
                    raise ValueError('No DCIM camera folder found. Use a camera card containing DCIM.')
                self.importer(source, None, None, self.command, source_uuid=uuid)
                self.event = {'phase': 'ejecting', 'source_uuid': uuid, 'safe_to_remove': False}
                self.publish()
                result = self.helper('unmount', uuid)
                if not result.get('safe_to_remove'):
                    raise ValueError('Card could not be unmounted. Leave it connected and retry.')
                self.finished.add(uuid)
                self.failures.pop(uuid, None)
                self.event = {'phase': 'safe', 'source_uuid': uuid, 'safe_to_remove': True, 'error': ''}
            except (ValueError, OSError, ConnectionError, subprocess.SubprocessError) as error:
                attempts = self.failures.get(uuid, (0, 0))[1] + 1
                self.failures[uuid] = (self.now() + min(300, 15 * 2 ** min(attempts, 5)), attempts)
                self.event = {'phase': 'failed', 'source_uuid': uuid, 'safe_to_remove': False,
                              'error': str(error)[:1000]}
                # Release our read-only mount on failure too. Never force unmount.
                try:
                    self.helper('unmount', uuid)
                except (ValueError, OSError, subprocess.SubprocessError):
                    pass
            self.publish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/footage-station/config.json')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    station = Station(ssh_command(config['host'], config['identity'], config['known_hosts']))
    while True:
        try:
            station.tick()
        except (ValueError, OSError, ConnectionError, subprocess.SubprocessError) as error:
            # No credentials or file contents are logged.
            print(json.dumps({'phase': 'retrying', 'error': str(error)[:1000]}), flush=True)
        time.sleep(10)


if __name__ == '__main__':
    main()
