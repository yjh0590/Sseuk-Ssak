import tempfile
import unittest
from pathlib import Path
from folder_compare import FolderCompare


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.a = self.root / 'App-v1.0'
        self.b = self.root / 'App-v1.1'
        self.a.mkdir()
        self.b.mkdir()
        self.c = FolderCompare()

    def ids(self):
        g = self.c.scan(self.root)['groups']
        self.assertEqual(len(g), 1)
        return [x['id'] for x in g[0]['items']]

    def test_subset_and_safe_move(self):
        (self.a / 'same.txt').write_text('same')
        (self.b / 'same.txt').write_text('same')
        (self.b / 'new.txt').write_text('new')
        a, b = self.ids()
        r = self.c.compare(a, b)
        self.assertTrue(r['subset'])
        self.assertEqual(r['same'], 1)
        self.assertEqual(r['only_reference'], ['new.txt'])
        moved = []
        self.c.move(r['token'], True, False, moved.append)
        self.assertEqual(moved, [self.a])
        self.assertTrue(self.b.exists())

    def test_unique_requires_ack(self):
        (self.a / 'unique.txt').write_text('unique')
        (self.a / 'different.txt').write_text('old')
        (self.b / 'different.txt').write_text('new')
        a, b = self.ids()
        r = self.c.compare(a, b)
        self.assertFalse(r['subset'])
        self.assertEqual(r['different'], ['different.txt'])
        with self.assertRaises(ValueError):
            self.c.move(r['token'], True, False, lambda p: None)
        moved = []
        self.c.move(r['token'], True, True, moved.append)
        self.assertEqual(moved, [self.a])

    def test_modified_blocks(self):
        (self.a / 'x.txt').write_text('a')
        (self.b / 'x.txt').write_text('a')
        a, b = self.ids()
        r = self.c.compare(a, b)
        (self.a / 'x.txt').write_text('changed')
        with self.assertRaises(ValueError):
            self.c.move(r['token'], True, True, lambda p: self.fail('must not move'))

    def test_reference_change_blocks(self):
        a, b = self.ids()
        r = self.c.compare(a, b)
        (self.b / 'new.txt').write_text('changed')
        with self.assertRaises(ValueError):
            self.c.move(r['token'], True, True, lambda p: self.fail('must not move'))

    def test_nested_empty_dirs_and_invalid(self):
        (self.a / 'empty').mkdir()
        a, b = self.ids()
        r = self.c.compare(a, b)
        self.assertFalse(r['subset'])
        self.assertEqual(r['only_source_dirs'], ['empty'])
        with self.assertRaises(ValueError):
            self.c.compare(a, a)
        with self.assertRaises(ValueError):
            self.c.move('invalid', True, True, lambda p: None)

    def test_no_cross_parent(self):
        (self.root / 'Other-v1.0').mkdir()
        (self.root / 'Other-v1.0' / 'App-v1.2').mkdir()
        self.assertEqual(len(self.c.scan(self.root)['groups']), 1)


if __name__ == '__main__':
    unittest.main()
