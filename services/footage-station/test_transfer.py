"""Exercise receiver subprocesses, real filesystem state and interrupted streams."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from receiver import Receiver, CHUNK
from transfer import Connection, import_folder


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / 'server'
        self.destination.mkdir()
        self.source = self.root / 'card'
        self.source.mkdir()
        self.command = [sys.executable, str(Path(__file__).with_name('receiver.py')),
                        '--root', str(self.destination)]

    def connection(self):
        connection = Connection(self.command)
        self.addCleanup(connection.close)
        return connection

    def request(self, data, path='DCIM/clip.mp4'):
        return {'op': 'begin', 'project': 'river', 'card': 'pocket-01', 'path': path,
                'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def test_end_to_end_rerun_and_source_preservation(self):
        data = os.urandom(CHUNK + 713)
        (self.source / 'DCIM').mkdir()
        (self.source / 'DCIM/clip.mp4').write_bytes(data)
        (self.source / 'DCIM/empty.srt').touch()
        events = []
        result = import_folder(self.source, 'river', 'pocket-01', self.command, events.append)
        target = self.destination / 'Projects/river/Originals/pocket-01/DCIM/clip.mp4'
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual((self.source / 'DCIM/clip.mp4').read_bytes(), data)
        report = json.loads((self.destination / result['manifest']).read_text())
        self.assertEqual(len(report['files']), 2)
        self.assertEqual(report['files'][0]['sha256'], hashlib.sha256(data).hexdigest())
        self.assertGreater(events[-1]['transferred_bytes'], 0)
        inode = target.stat().st_ino
        events.clear()
        import_folder(self.source, 'river', 'pocket-01', self.command, events.append)
        self.assertEqual(events[-1]['transferred_bytes'], 0)
        self.assertEqual(target.stat().st_ino, inode)

    def test_disconnect_in_middle_of_chunk_and_resume(self):
        data = os.urandom(200000)
        c = self.connection()
        c.request(self.request(data, 'clip.mp4'))
        header = {'op': 'chunk', 'offset': 0, 'length': len(data)}
        c.process.stdin.write((json.dumps(header) + '\n').encode() + data[:50000])
        c.process.stdin.flush()
        c.close()
        self.assertFalse((self.destination / 'Projects/river/Originals/pocket-01/clip.mp4').exists())
        resumed = self.connection()
        state = resumed.request(self.request(data, 'clip.mp4'))
        self.assertEqual(state['offset'], 50000)
        self.assertEqual(state['prefix_sha256'], hashlib.sha256(data[:50000]).hexdigest())
        resumed.close()
        (self.source / 'clip.mp4').write_bytes(data)
        events = []
        result = import_folder(self.source, 'river', 'pocket-01', self.command, events.append)
        self.assertEqual(events[-1]['transferred_bytes'], len(data) - 50000)
        self.assertTrue((self.destination / result['manifest']).is_file())

    def test_corrupt_partial_is_reset_without_touching_originals(self):
        data = b'actual-video-bytes'
        c = self.connection()
        c.request(self.request(data, 'clip.mp4'))
        c.request({'op': 'chunk', 'offset': 0, 'length': 4}, b'BAD!')
        c.close()
        (self.source / 'clip.mp4').write_bytes(data)
        events = []
        import_folder(self.source, 'river', 'pocket-01', self.command, events.append)
        self.assertEqual(events[-1]['transferred_bytes'], len(data))

    def test_conflict_preserves_existing_file(self):
        (self.source / 'clip.mp4').write_bytes(b'first')
        import_folder(self.source, 'river', 'pocket-01', self.command)
        (self.source / 'clip.mp4').write_bytes(b'second')
        with self.assertRaisesRegex(ValueError, 'different data'):
            import_folder(self.source, 'river', 'pocket-01', self.command)
        self.assertEqual((self.destination / 'Projects/river/Originals/pocket-01/clip.mp4').read_bytes(), b'first')
        self.assertEqual(len(list(self.destination.rglob('*.json'))), 1)

    def test_no_manifest_before_all_files_verified(self):
        c = self.connection()
        c.request(self.request(b'video'))
        with self.assertRaisesRegex(ValueError, 'every expected file'):
            c.request({'op': 'complete', 'file_count': 1})
        self.assertFalse(list(self.destination.rglob('*.json')))

    def test_bad_checksum_never_publishes(self):
        c = self.connection()
        c.request(self.request(b'good'))
        c.request({'op': 'chunk', 'offset': 0, 'length': 4}, b'evil')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            c.request({'op': 'finish'})
        self.assertFalse(list((self.destination / 'Projects').rglob('*.mp4')))

    def test_server_rechecks_file_before_manifest(self):
        c = self.connection()
        c.request(self.request(b'good'))
        c.request({'op': 'chunk', 'offset': 0, 'length': 4}, b'good')
        c.request({'op': 'finish'})
        p = self.destination / 'Projects/river/Originals/pocket-01/DCIM/clip.mp4'
        p.write_bytes(b'edit')
        with self.assertRaisesRegex(ValueError, 'different data'):
            c.request({'op': 'complete', 'file_count': 1})
        self.assertFalse(list(self.destination.rglob('*.json')))

    def test_path_traversal_and_destination_symlinks(self):
        for path in ['../escape', '/escape', 'a/../../escape', 'a//b', 'a\\b']:
            with self.subTest(path=path):
                c = self.connection()
                with self.assertRaises(ValueError):
                    c.request(self.request(b'data', path))
                c.close()
        outside = self.root / 'outside'
        outside.mkdir()
        (self.destination / 'Projects').symlink_to(outside, target_is_directory=True)
        c = self.connection()
        with self.assertRaises(ValueError):
            c.request(self.request(b'data'))
        self.assertEqual(list(outside.iterdir()), [])

    def test_source_symlink_is_never_followed(self):
        (self.source / 'secret').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            import_folder(self.source, 'river', 'pocket-01', self.command)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_concurrent_imports_are_serialized(self):
        first = self.connection()
        first.request({'op': 'ping'})
        second = self.connection()
        with self.assertRaisesRegex(ValueError, 'Another import'):
            second.request({'op': 'ping'})


if __name__ == '__main__':
    unittest.main()
