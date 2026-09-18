#!/usr/bin/env python3
"""Focused safety and retrieval checks for the owner-only knowledge index."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from PIL import Image

spec = importlib.util.spec_from_file_location('home_knowledge', Path(__file__).with_name('home-knowledge.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class KnowledgeTest(unittest.TestCase):
    def test_sync_removes_deleted_sources_and_secret_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / 'repo'
            (repo / 'docs').mkdir(parents=True)
            doc = repo / 'docs' / 'storage.md'
            doc.write_text('Draw boards live on the SSD.\npassword = private-value\n')
            db = module.connect(root / 'private' / 'index.sqlite3')
            result = module.sync(db, repo, root / 'missing.db', root / 'creative', False)
            self.assertEqual(result['documents'], 1)
            match = module.search(db, 'Draw boards SSD')[0]
            self.assertIn('SSD', match['excerpt'])
            self.assertNotIn('private-value', match['excerpt'])
            self.assertIsNone(db.execute('SELECT embedding FROM documents').fetchone()[0])
            doc.unlink()
            module.sync(db, repo, root / 'missing.db', root / 'creative', False)
            self.assertEqual(module.search(db, 'Draw'), [])

    def test_draw_board_is_indexed_without_deleted_elements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / 'repo'
            (repo / 'docs').mkdir(parents=True)
            draw = root / 'draw.db'
            db = sqlite3.connect(draw)
            db.executescript('''
              CREATE TABLE projects(id TEXT,name TEXT,description TEXT,updated_at TEXT);
              CREATE TABLE elements(id TEXT,project_id TEXT,data TEXT,label_text TEXT,is_deleted INTEGER);
              INSERT INTO projects VALUES('board-1','Architecture','Servers and disks','today');
              INSERT INTO elements VALUES('e1','board-1',NULL,'The SSD holds Draw boards',0);
              INSERT INTO elements VALUES('e2','board-1',NULL,'Deleted secret',1);
            ''')
            db.close()
            index = module.connect(root / 'private' / 'index.db')
            module.sync(index, repo, draw, root / 'creative', False)
            match = module.search(index, 'SSD boards')[0]
            self.assertEqual(match['source'], 'draw')
            self.assertEqual(match['url'], 'https://draw.home.egouda.xyz/?board=board-1')
            self.assertNotIn('Deleted secret', module.fetch(index, match['id'])['text'])

    def test_attachment_allowlist_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            creative = root / 'creative'
            inbox = creative / 'AI Inbox'
            inbox.mkdir(parents=True)
            (inbox / 'hello.txt').write_text('Photo notes from phone')
            (inbox / 'escape.txt').symlink_to(root / 'outside.txt')
            (root / 'outside.txt').write_text('private')
            self.assertEqual([p.name for p in module.attachment_paths(creative)], ['hello.txt'])
            self.assertEqual(module.resolve_attachment(creative, 'AI Inbox/hello.txt').name, 'hello.txt')
            attachment = next(module.attachment_documents(creative))
            self.assertIn('%2FAI%20Inbox%2Fhello.txt', attachment[3])
            with self.assertRaises(ValueError):
                module.resolve_attachment(creative, '../outside.txt')
            with self.assertRaises(ValueError):
                module.resolve_attachment(creative, 'AI Inbox/escape.txt')
            photo = inbox / 'phone.jpg'
            Image.new('RGB', (2400, 1200), '#2854aa').save(photo)
            block = module.attachment_preview(creative, 'AI Inbox/phone.jpg')
            self.assertEqual(block['type'], 'image')
            self.assertEqual(block['mimeType'], 'image/jpeg')
            self.assertTrue(block['data'])

if __name__ == '__main__':
    unittest.main()
