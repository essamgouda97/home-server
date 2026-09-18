#!/usr/bin/env python3
"""Verify the one-time drive move preserves bytes and the scanner compatibility path."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('move_drive_inbox',Path(__file__).with_name('move-drive-inbox.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class MoveDriveInboxTest(unittest.TestCase):
    def test_move_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            creative=root/'creative'
            drive=root/'drive'
            inbox=creative/'AI Inbox'
            scans=creative/'Scans'
            inbox.mkdir(parents=True)
            scans.mkdir()
            (inbox/'photo.jpg').write_bytes(b'photo')
            (scans/'scan.pdf').write_bytes(b'scan')
            with patch.object(module,'CREATIVE',creative), patch.object(module,'DRIVE',drive), \
                 patch.object(module,'STATE',root/'state.json'), patch.object(module,'BACKUP_BASE',root/'backup'), \
                 patch.object(module,'SERVICES',()), patch.object(sys,'argv',['move-drive-inbox.py','--apply']):
                module.main()
                self.assertEqual((drive/'AI Inbox/photo.jpg').read_bytes(),b'photo')
                self.assertEqual((drive/'Scans/scan.pdf').read_bytes(),b'scan')
                self.assertTrue((creative/'Scans').is_symlink())
                self.assertEqual((drive/'Creative').resolve(), creative.resolve())
                self.assertFalse((creative/'AI Inbox').exists())
                self.assertEqual(len(list((root/'backup').glob('*/Scans/scan.pdf'))),1)
                module.main()

if __name__=='__main__':
    unittest.main()
