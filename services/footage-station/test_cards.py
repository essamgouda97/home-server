import copy
import unittest

from card_helper import candidates


class CardSelectionTests(unittest.TestCase):
    def setUp(self):
        self.boot = {'type': 'disk', 'tran': None, 'rm': False, 'maj:min': '179:0',
            'children': [{'type': 'part', 'maj:min': '179:1', 'fstype': 'vfat', 'uuid': 'ABCD-1234',
                          'size': 500000000, 'mountpoints': ['/boot/firmware']},
                         {'type': 'part', 'maj:min': '179:2', 'fstype': 'ext4'}]}
        self.card = {'type': 'disk', 'tran': 'usb', 'rm': True, 'maj:min': '8:0',
            'children': [{'type': 'part', 'maj:min': '8:1', 'fstype': 'exfat', 'uuid': 'DCBA-4321',
                          'size': 64000000000, 'mountpoints': [None]}]}

    def test_camera_is_selected_and_pi_boot_is_excluded(self):
        cards = candidates([self.boot, self.card], '179:2')
        self.assertEqual([c['uuid'] for c in cards], ['DCBA-4321'])

    def test_usb_boot_disk_remains_excluded(self):
        self.boot.update(tran='usb', rm=True)
        self.boot['children'][0]['mountpoints'] = [None]
        self.assertEqual(len(candidates([self.boot, self.card], '179:2')), 1)

    def test_unknown_root_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'operating-system disk'):
            candidates([self.boot, self.card], '0:45')

    def test_does_not_take_over_other_mounts_or_non_camera_disks(self):
        for change in [{'mountpoints': ['/media/someone/card']}, {'fstype': 'ext4'},
                       {'uuid': '../etc'}, {'type': 'crypt'}]:
            with self.subTest(change=change):
                card = copy.deepcopy(self.card)
                card['children'][0].update(change)
                self.assertEqual(candidates([self.boot, card], '179:2'), [])
        for change in [{'tran': 'sata'}, {'rm': False}]:
            self.assertEqual(candidates([self.boot, dict(self.card, **change)], '179:2'), [])

    def test_duplicate_filesystem_ids_are_ambiguous(self):
        with self.assertRaisesRegex(ValueError, 'same filesystem ID'):
            candidates([self.boot, self.card, copy.deepcopy(self.card)], '179:2')

    def test_existing_station_readonly_mount_can_be_reused(self):
        self.card['children'][0]['mountpoints'] = ['/run/footage-cards/DCBA-4321']
        self.assertTrue(candidates([self.boot, self.card], '179:2')[0]['mounted'])


if __name__ == '__main__':
    unittest.main()
