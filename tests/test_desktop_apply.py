"""desktop.App의 검사 → 선택 → 휴지통 이동 흐름. 실제 휴지통 대신 임시 폴더로 옮긴다."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import APP  # noqa: F401  (app 폴더를 import 경로에 추가)
import desktop


class ApplyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'docs'
        self.bin = Path(tmp.name) / 'bin'
        self.root.mkdir()
        self.bin.mkdir()
        self.recycled = []
        # 실제 휴지통과 폴더 선택 창 대신 가짜를 끼운다
        for name, fake in (('recycle', self.fake_recycle), ('ask_directory', lambda initial: str(self.root))):
            patcher = mock.patch.object(desktop, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = desktop.App()

    def fake_recycle(self, path):
        self.recycled.append(path)
        shutil.move(str(path), str(self.bin / f'{len(self.recycled)}_{path.name}'))

    def write(self, name, text, age=0):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        t = 1_700_000_000 - age
        os.utime(p, (t, t))
        return p

    def scan(self):
        return self.app.dispatch('scan', {'mode': 'files'})

    def entry(self, state, kind, name):
        return next(f for f in state['files'] if f['kind'] == kind and Path(f['path']).name == name)

    def trash(self, *ids):
        return self.app.dispatch('apply', {'op': 'trash', 'ids': list(ids)})

    def test_copy_is_recycled_and_keeper_stays(self):
        keeper = self.write('a.txt', 'same', age=0)
        copy = self.write('old/a-copy.txt', 'same', age=100)
        state = self.scan()
        result = self.trash(self.entry(state, '복사본', 'a-copy.txt')['id'])
        self.assertEqual(self.recycled, [copy])
        self.assertTrue(keeper.exists())
        self.assertEqual(len(result['ok']), 1)
        self.assertFalse(any(Path(f['path']) == copy for f in result['state']['files']))

    def test_same_name_keeper_is_protected(self):
        self.write('report.txt', 'new', age=0)
        old = self.write('report (1).txt', 'old', age=100)
        state = self.scan()
        keeper = self.entry(state, '같은 이름', 'report.txt')
        self.assertTrue(keeper['protected'])
        result = self.trash(keeper['id'])
        self.assertEqual(self.recycled, [])
        self.assertEqual(result['ok'], [])
        result = self.trash(self.entry(result['state'], '같은 이름', 'report (1).txt')['id'])
        self.assertEqual(self.recycled, [old])

    def test_file_changed_after_scan_is_refused(self):
        self.write('a.txt', 'same', age=0)
        copy = self.write('old/a-copy.txt', 'same', age=100)
        state = self.scan()
        copy.write_text('changed!', encoding='utf-8')
        result = self.trash(self.entry(state, '복사본', 'a-copy.txt')['id'])
        self.assertEqual(self.recycled, [])
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(copy.exists())

    def test_keeper_changed_after_scan_blocks_same_name(self):
        new = self.write('report.txt', 'new', age=0)
        self.write('report (1).txt', 'old', age=100)
        state = self.scan()
        new.write_text('edited later', encoding='utf-8')
        result = self.trash(self.entry(state, '같은 이름', 'report (1).txt')['id'])
        self.assertEqual(self.recycled, [])
        self.assertIn('남길 파일이 바뀌었어요', next(iter(result['errors'].values())))

    def test_mixed_kinds_and_unknown_ids_are_rejected(self):
        self.write('a.txt', 'same', age=0)
        self.write('old/a-copy.txt', 'same', age=100)
        state = self.scan()
        copy = self.entry(state, '복사본', 'a-copy.txt')['id']
        whole = self.entry(state, '전체 파일', 'a.txt')['id']
        with self.assertRaises(ValueError):
            self.trash(copy, whole)
        with self.assertRaises(ValueError):
            self.trash('없는-id')
        with self.assertRaises(ValueError):
            self.app.dispatch('없는-작업', {})
        self.assertEqual(self.recycled, [])

    def test_recycle_failure_is_reported_not_raised(self):
        self.write('a.txt', 'same', age=0)
        copy = self.write('old/a-copy.txt', 'same', age=100)
        state = self.scan()

        def broken(path):
            raise OSError('사용 중인 파일')

        mock.patch.object(desktop, 'recycle', broken).start()
        result = self.trash(self.entry(state, '복사본', 'a-copy.txt')['id'])
        self.assertEqual(result['ok'], [])
        self.assertIn('사용 중인 파일', next(iter(result['errors'].values())))
        self.assertTrue(copy.exists())

    def test_executable_is_previewed_not_opened(self):
        import preview

        self.write('보고서.pdf.exe', 'not a pe')
        self.write('run.bat', 'del /q %TEMP%\\*.tmp')
        state = self.scan()
        with (
            mock.patch.object(desktop.subprocess, 'Popen') as popen,
            mock.patch.object(desktop.os, 'startfile', create=True) as start,
            mock.patch.object(preview, 'signature', return_value='서명 없음'),
        ):
            exe = self.app.dispatch('open_file', {'id': self.entry(state, '전체 파일', '보고서.pdf.exe')['id']})
            bat = self.app.dispatch('open_file', {'id': self.entry(state, '전체 파일', 'run.bat')['id']})
        start.assert_not_called()
        popen.assert_not_called()
        self.assertIn('.pdf 파일처럼 보이지만', exe['preview']['detail'])
        self.assertIn('PE)이 아니에요', exe['preview']['detail'])
        self.assertIn('del /q %TEMP%\\*.tmp', bat['preview']['detail'])


class BrowserTests(unittest.TestCase):
    def test_edge_when_chrome_missing(self):
        import chrome_link

        edge = Path('C:/edge/msedge.exe')
        with (
            mock.patch.object(chrome_link, 'find_chrome', side_effect=FileNotFoundError),
            mock.patch.object(chrome_link, 'find_edge', return_value=edge),
        ):
            self.assertEqual(chrome_link.find_browser(), edge)


if __name__ == '__main__':
    unittest.main()
