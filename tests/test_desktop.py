import os
import http.client
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
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

    def test_space_patch_preserves_file_ids(self):
        state = self.app.snapshot()
        refs = dict(self.app.refs)
        with patch.object(self.app, 'snapshot', side_effect=AssertionError('full snapshot')):
            result = self.app.dispatch('refresh_space', {'compact': True})
        self.assertNotIn('files', result['state_patch'])
        self.assertEqual(self.app.refs, refs)
        self.assertTrue(state['files'])

    def test_keeper_patch_updates_only_selected_group(self):
        for name in ('copy.txt', 'copy (1).txt', 'other.txt', 'other (1).txt'):
            (self.root / name).write_text(name)
        self.app.collect('files', lambda _: None)
        state = self.app.snapshot()
        chosen = next(r for r in state['files'] if r['kind'] == '같은 이름' and r['name'] == 'copy.txt')
        untouched = {r['id']: dict(r) for r in state['files'] if r['kind'] != '같은 이름' or r['group'] != chosen['group']}
        with patch.object(self.app, 'snapshot', side_effect=AssertionError('full snapshot')):
            result = self.app.dispatch('keeper', {'id': chosen['id'], 'compact': True})
        self.assertEqual(len(result['file_updates']), 2)
        updates = {r['id']:r for r in result['file_updates']}
        self.assertTrue(updates[chosen['id']]['protected'])
        for key,view in untouched.items():
            self.assertEqual(next(r for r in self.app.file_views if r['id'] == key), view)
        other = next(r for r in result['file_updates'] if r['id'] != chosen['id'])
        self.assertEqual(self.app.refs[other['id']][1].keep, self.root / 'copy.txt')

    def test_folder_removal_updates_totals_without_scan(self):
        # Include a second category that references the folder being removed.
        (self.root / 'a' / 'duplicate.txt').write_text('333')
        self.app.collect('files', lambda _: None)
        self.app.snapshot()
        rank_ids = set(r['id'] for r in self.rank().values())
        fake_recycle(self.root / 'a')
        with patch.object(self.app, 'collect', side_effect=AssertionError('full scan')):
            result = self.app.update_after_folder_removal({'moved': [str(self.root / 'a')]})
        self.assertEqual({r['name'] for r in result['state']['files'] if r['kind'] == '전체 파일'}, {'top.txt', 'three.txt'})
        self.assertTrue(all(not (r.keep and r.keep.is_relative_to(self.root / 'a')) for r in self.app.rows))
        self.assertFalse(rank_ids & self.app.refs.keys())
        rows = self.rank()
        self.assertEqual(rows['b']['size'], 3)
        self.assertEqual(rows['b']['count'], 1)
        self.assertNotIn('a', rows)

    def test_concurrent_mutation_is_refused(self):
        with self.app.request_lock:
            with self.assertRaisesRegex(ValueError, '진행 중인 작업'):
                self.app.dispatch('reset', {})
        self.assertIsNotNone(self.app.root)

    def test_server_answers_ping_while_operation_is_running(self):
        started, release = threading.Event(), threading.Event()
        def slow(value, progress):
            started.set()
            if not release.wait(5):
                raise RuntimeError('test operation timed out')
            return {}
        self.app.handlers['slow'] = slow
        server = desktop.ThreadingHTTPServer(('127.0.0.1', 0), desktop.BaseHTTPRequestHandler)
        host = '127.0.0.1:%s' % server.server_port
        server.RequestHandlerClass = desktop.make_handler(self.app, 'test-token', host, 'http://' + host)
        serving = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        serving.start()
        def post(action):
            connection = http.client.HTTPConnection(host, timeout=3)
            try:
                connection.request('POST', '/test-token/api/' + action, '{}', {'Origin': 'http://' + host})
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
        outcomes = []
        worker = threading.Thread(target=lambda: outcomes.append(post('slow')), daemon=True)
        try:
            worker.start()
            self.assertTrue(started.wait(2))
            self.assertEqual(post('ping'), (200, b'{}'))
            self.assertEqual(post('reset')[0], 400)
            self.assertIsNotNone(self.app.root)
        finally:
            release.set()
            worker.join(4)
            server.shutdown()
            serving.join(2)
            server.server_close()
        self.assertEqual(outcomes, [(200, b'{}')])


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
