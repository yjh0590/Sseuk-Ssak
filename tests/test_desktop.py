import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import APP  # noqa: F401  (app 폴더를 import 경로에 추가)
import desktop
import engine
import folder_ops
from smart_service import SmartService
from smart_rules import RuleViolation


def fake_recycle(path):
    shutil.rmtree(path) if path.is_dir() else path.unlink()


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).absolute() / 'docs'
        (self.root / 'a' / 'inner').mkdir(parents=True)
        (self.root / 'b').mkdir()
        (self.root / 'a' / 'one.txt').write_text('1')
        (self.root / 'a' / 'inner' / 'two.txt').write_text('22')
        (self.root / 'b' / 'three.txt').write_text('333')
        (self.root / 'top.txt').write_text('4444')
        self._recycle = desktop.recycle
        desktop.recycle = fake_recycle
        self.app = desktop.App()
        self.app.root = self.root
        self.app.collect('files', lambda _: None)

    def tearDown(self):
        desktop.recycle = self._recycle
        self.tmp.cleanup()

    def rank(self):
        return {Path(r['path']).name: r for r in self.app.dispatch('rank', {'path': str(self.root)})}

    def test_rank_uses_scan_totals_and_counts(self):
        rows = self.rank()
        self.assertEqual(rows['a']['size'], 3)
        self.assertEqual(rows['a']['count'], 2)
        self.assertEqual(rows['top.txt']['size'], 4)
        self.assertNotIn('count', rows['top.txt'])

    def test_rank_ids_survive_snapshot_refresh(self):
        rows = self.rank()
        self.app.dispatch('refresh_space', {})
        result = self.app.dispatch('apply', {'ids': [rows['a']['id']], 'op': 'trash'})
        self.assertEqual(result['errors'], {})
        self.assertFalse((self.root / 'a').exists())
        self.assertTrue((self.root / 'b').exists())

    def test_folder_changed_after_rank_is_refused(self):
        rows = self.rank()
        (self.root / 'a' / 'inner' / 'new.txt').write_text('new')
        result = self.app.dispatch('apply', {'ids': [rows['a']['id']], 'op': 'trash'})
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue((self.root / 'a').exists())

    def test_from_scan_matches_disk_capture(self):
        target = self.root / 'a'
        files = {p: engine.signature(p) for p in target.rglob('*') if p.is_file()}
        item = folder_ops.from_scan(self.root, target, files, [target / 'inner'])
        folder_ops.validate(self.root, item)  # no change -> no error
        self.assertEqual(item.size, folder_ops.capture(self.root, target).size)

    def test_unknown_action(self):
        with self.assertRaises(ValueError):
            self.app.dispatch('nope', {})


class ScanTests(unittest.TestCase):
    def test_large_copies_and_same_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).absolute() / 'docs'
            root.mkdir()
            head = os.urandom(engine.CHUNK)
            (root / 'x.bin').write_bytes(head + b'tail-1')
            (root / 'y.bin').write_bytes(head + b'tail-1')
            (root / 'z.bin').write_bytes(head + b'tail-2')  # same size and head, different tail
            rows, _, _ = engine.scan(root)
            copies = {r.path.name for r in rows if r.kind == '복사본'}
            self.assertEqual(len(copies), 1)
            self.assertTrue(copies <= {'x.bin', 'y.bin'})


class SmartInputTests(unittest.TestCase):
    def test_friendly_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SmartService()
            service.select(tmp)
            with self.assertRaisesRegex(RuleViolation, '숫자'):
                service.handle({'op': 'mkdir', 'name': '업무', 'number': '두번째'})
            with self.assertRaisesRegex(RuleViolation, '필수 입력값'):
                service.handle({'op': 'mkdir'})


if __name__ == '__main__':
    unittest.main()
