#!/usr/bin/env python3
"""Disk safety and first-boot configuration regressions; never opens a device."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import stat

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).with_name('prepare-footage-station.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.disk = {'type': 'disk', 'tran': 'usb', 'rm': True, 'size': 63864569856,
                     'mountpoints': [None], 'children': [
                         {'type': 'part', 'mountpoints': ['/media/egouda/card']}]}

    def test_only_expected_removable_card(self):
        prepare.validate_disk(self.disk, self.disk['size'])
        for change in [{'tran': 'sata'}, {'rm': False}, {'type': 'part'},
                       {'size': 64000000000}, {'mountpoints': ['/']}, {'children': []},
                       {'children': [{'type': 'part', 'mountpoints': ['/home']}]},
                       {'children': [{'type': 'crypt', 'mountpoints': [None]}]},
                       {'children': [{'type': 'part', 'mountpoints': [None],
                                      'children': [{'type': 'lvm'}]}]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare.validate_disk(dict(self.disk, **change), self.disk['size'])

    def test_no_private_keys_or_authorized_keys_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / 'key.pub'
            for content in ['-----BEGIN OPENSSH PRIVATE KEY-----',
                            'command="sh" ssh-ed25519 AAAA', '']:
                key.write_text(content)
                with self.assertRaises(ValueError):
                    prepare.seed({}, [key])

    def test_ethernet_and_key_only_ssh_without_runtime_secrets(self):
        config = json.loads((prepare.CONFIG / 'image.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            key = Path(temporary) / 'key.pub'
            key.write_text('ssh-ed25519 AAAA synthetic-test-key\n')
            seeds = prepare.seed(config, [key])
        user = json.loads(seeds['user-data'].split('\n', 1)[1])
        self.assertTrue(user['enable_ssh'])
        self.assertFalse(user['ssh_pwauth'])
        self.assertTrue(user['users'][0]['lock_passwd'])
        self.assertTrue(user['disable_root'])
        self.assertNotIn('plain_text_passwd', user['users'][0])
        network = json.loads(seeds['network-config'])['network']
        self.assertTrue(network['ethernets']['wired']['dhcp4'])
        self.assertNotIn('wifis', network)
        self.assertNotIn('packages', user)  # SSH onboarding does not wait on apt.
        self.assertIn('--no-block', user['runcmd'][-1])

    def test_hash_rejects_short_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / 'image'
            p.write_bytes(b'card')
            with self.assertRaises(ValueError):
                prepare.hash_file(p, 5)

    def test_lsblk_explicitly_requests_tree_without_name_column(self):
        device = MagicMock()
        device.__str__.return_value = '/dev/disk/by-id/usb-card'
        device.is_symlink.return_value = True
        device.resolve.return_value.stat.return_value.st_mode = stat.S_IFBLK
        with patch.object(prepare, 'output', return_value=json.dumps({'blockdevices': [self.disk]})) as command:
            prepare.inspect(device, self.disk['size'])
            self.assertIn('--tree', command.call_args.args)


if __name__ == '__main__':
    unittest.main()
