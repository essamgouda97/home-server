#!/usr/bin/env python3
"""Exercise credential serialization and offline target boundaries without a card."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gym', Path(__file__).with_name('prepare-gym-pi.py'))
gym = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gym)


class ProvisioningTests(unittest.TestCase):
    def test_credentials_cannot_inject_network_settings(self):
        credentials = {'ssid': 'wifi: "quoted" # name', 'password': 'a:#"\\$()safe-password'}
        network = json.loads(gym.network_config(credentials))['network']
        self.assertEqual(set(network['wifis']), {'wlan0'})
        access = network['wifis']['wlan0']['access-points']
        self.assertEqual(list(access), [credentials['ssid']])
        self.assertEqual(access[credentials['ssid']]['password'], credentials['password'])

    def test_wifi_constraints(self):
        for credentials in ({'ssid': 'x' * 33, 'password': 'valid-password'},
                            {'ssid': 'network', 'password': 'short'},
                            {'ssid': 'network\nextra', 'password': 'valid-password'}):
            with self.subTest(credentials=credentials), self.assertRaises(ValueError):
                gym.network_config(credentials)

    def test_prederived_psk(self):
        gym.network_config({'ssid': 'network', 'password': 'a' * 64})
        with self.assertRaises(ValueError):
            gym.network_config({'ssid': 'network', 'password': 'z' * 64})

    def test_symlink_cannot_write_outside_card(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            root = Path(tmp).resolve()
            (root / 'etc').symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                gym.write(root, 'etc/hostname', 'gym-pi\n')
            self.assertFalse((Path(other) / 'hostname').exists())

    def test_reject_host_root(self):
        with self.assertRaises(ValueError):
            gym.check_mount(Path('/'), {'children': []}, 'ext4')

    def test_reject_partition_on_different_disk(self):
        mount = {'filesystems': [{'fstype': 'ext4', 'options': 'rw', 'source': '/dev/sda2'}]}
        with patch.object(Path, 'is_mount', return_value=True), patch.object(
                gym, 'command', return_value=json.dumps(mount)):
            with self.assertRaises(ValueError):
                gym.check_mount(Path('/media/card'), {'children': [
                    {'path': '/dev/sdd2', 'type': 'part'}]}, 'ext4')


if __name__ == '__main__':
    unittest.main()
