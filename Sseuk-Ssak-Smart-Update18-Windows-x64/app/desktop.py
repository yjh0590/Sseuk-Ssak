"""Serve the desktop renderer on a private, short-lived loopback address."""
import ctypes
import json
import os
import secrets
import select
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import chrome_link
import folder_ops
import junk
import storage_view
import windows_ui
from analysis_views import folder_index
from download_versions import word_groups
from engine import held, relocate, scan, signature, validate_row
from folder_compare import FolderCompare
from local_groups import organize_rows, choose_keepers as choose
from recycle import recycle, empty_recycle_bin
from result_view import CleanupResult, describe
from smart_service import SmartService

BASE = Path(__file__).resolve().parent
IDLE_SECONDS = 180  # the page pings every 15 s; stop the server once the window is gone
FILTERS = ('같은 이름', '전체 파일', '복사본', '풀어둔 ZIP', '작업 버전', '변환 파일', '큰 파일', 'ZIP 확인')
KEEPER_MODES = ('date', 'number', 'manual', 'version')
FOLDER_SIZE = '폴더 용량'
JS = 'text/javascript'
ASSETS = {
    '': ('index.html', 'text/html; charset=utf-8'),
    'style.css': ('style.css', 'text/css'),
    'ui.js': ('ui.js', JS),
    'storage.js': ('storage.js', JS),
    'layout_scale.js': ('layout_scale.js', JS),
    'folder_ui.js': ('folder_ui.js', JS),
    'smart_ui.js': ('smart_ui.js', JS),
    'icon.ico': ('Sseuk-Ssak.ico', 'image/x-icon'),
    'mark.png': ('mark.png', 'image/png'),
    'font.ttf': ('fonts/SseukSsakDance.ttf', 'font/ttf'),
}


def stamp_text(seconds):
    return time.strftime('%Y.%m.%d %H:%M:%S', time.localtime(seconds))


def ask_directory(initial):
    import tkinter as tk
    from tkinter import filedialog
    win = tk.Tk()
    win.withdraw()
    win.attributes('-topmost', True)
    try:
        return filedialog.askdirectory(parent=win, initialdir=initial)
    finally:
        win.destroy()


def top_child(parent, path):
    """The direct child of parent that contains path, or None."""
    try:
        parts = path.relative_to(parent).parts
    except ValueError:
        return None
    return parent / parts[0] if parts else None


class App:
    """One desktop session. Every UI request goes through dispatch()."""

    def __init__(self):
        self.smart = SmartService()
        self.folder_compare = FolderCompare()
        self.refs = {}
        self.chrome_job = None
        self.chrome_outcome = None
        self.reset_state()
        self.handlers = {
            'init': lambda v, progress: self.snapshot(),
            'reset': self.on_reset,
            'smart_pick': self.on_smart_pick,
            'smart': lambda v, progress: self.smart.handle(v),
            'refresh_space': self.on_refresh_space,
            'folder_find': self.on_folder_find,
            'folder_bulk_prepare': lambda v, progress: self.folder_compare.prepare_bulk(v.get('ids')),
            'folder_bulk_remove': self.on_folder_bulk_remove,
            'folder_compare': lambda v, progress: self.folder_compare.compare(v['source'], v['reference']),
            'folder_remove': self.on_folder_remove,
            'grouping': self.on_grouping,
            'keeper': self.on_keeper,
            'scan': self.on_scan,
            'recycle_info': lambda v, progress: {'size': storage_view.recycle_size(None)},
            'empty_recycle': self.on_empty_recycle,
            'repair_downloads': lambda v, progress: windows_ui.restore_downloads_label(windows_ui.data_dir() / 'display-backup'),
            'rank': self.on_rank,
            'open_file': self.on_open_file,
            'reveal': self.on_reveal,
            'setup': self.on_setup,
            'chrome': self.on_chrome,
            'chrome_status': self.on_chrome_status,
            'apply': self.on_apply,
        }

    def reset_state(self):
        self.root = None
        self.rows = []
        self.raw_rows = []
        self.stash = []
        self.index = []
        self.junks = []
        self.logs = []
        self.across = False
        self.keeper_mode = 'date'
        self.keeper_stamps = {}
        self.overrides = {}
        self.last_storage = None
        self.word_mode = 'off'
        self.word_keyword = ''
        self.similar_names = False
        self.refs.clear()

    def dispatch(self, action, v, progress=lambda event: None):
        handler = self.handlers.get(action)
        if handler is None:
            raise ValueError('작업을 찾지 못했어요.')
        if self.chrome_job and self.chrome_job.is_alive() and action not in ('init', 'chrome_status'):
            raise ValueError('크롬 다운로드 정리가 끝난 뒤 다시 시도해 주세요.')
        return handler(v, progress)

    # --- shared helpers -------------------------------------------------

    def pack(self, p, n, reason, kind, obj, group=None):
        key = secrets.token_hex(10)
        self.refs[key] = (kind, obj)
        return dict(id=key, path=str(p), name=windows_ui.display_name(p), size=n, note=reason, kind=kind, group=str(group or ''))

    def same_name_stamps(self):
        return {r.path: r.stamp for r in self.rows if r.kind == '같은 이름'}

    def collect(self, kind, report):
        if kind == 'junk':
            self.junks, self.logs = junk.collect(self.root, junk.user_temp())
            return
        self.index = []
        self.last_storage = None
        rows, _, self.logs = scan(self.root, progress=report, folder_data=self.index, across=self.across)
        self.raw_rows = list(rows)
        self.rows = organize_rows(self.raw_rows, self.word_mode, self.word_keyword, self.similar_names, self.keeper_mode, self.overrides)
        self.stash = held(self.root)
        self.keeper_stamps = self.same_name_stamps()
        self.overrides.clear()
        self.rows = choose(self.rows, self.keeper_mode, self.overrides)

    def snapshot(self, space=None):
        # Folder-size ids belong to the separate rank list; keep them valid across refreshes.
        for key in [k for k, (kind, _) in self.refs.items() if kind != FOLDER_SIZE]:
            del self.refs[key]
        files = [self.pack(r.path, r.size, r.detail, r.kind, r, r.group) | {
                    'compare': str(r.keep or ''),
                    'date': stamp_text(r.stamp[1] / 1e9),
                    'protected': r.kind == '같은 이름' and not r.keep}
                 for r in self.rows]
        temp = [self.pack(r.path, r.stamp[0], r.reason, '정크 파일', r) for r in self.junks]
        saved = []
        for p, d in self.stash:
            try:
                saved.append(self.pack(d, p.stat().st_size, '원래 위치로 복원할 수 있어요.', '보관함', (p, d)) | {'reveal': str(p)})
            except OSError:
                pass
        root = self.root
        if space is None:
            space = storage_view.measure([root]) if root else []
        return dict(
            root=str(root or ''), files=files, junk=temp, stash=saved, logs=self.logs,
            temp=str(junk.user_temp() or ''), filters=list(FILTERS), chrome_report=self.chrome_history(),
            keeper_mode=self.keeper_mode, word_mode=self.word_mode, word_keyword=self.word_keyword,
            similar_names=self.similar_names, root_name=windows_ui.display_name(root) if root else '',
            extensions=sorted({r.path.suffix.lower().lstrip('.') for r in self.rows if r.kind == '전체 파일' and r.path.suffix}),
            storage_current=space, storage_comparison=self.last_storage)

    @staticmethod
    def chrome_history():
        # The pre-0.7.19 location inside the app folder is still read once as a fallback.
        for path in (chrome_link.result_file(), BASE / 'chrome-last-result.json'):
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
        return None

    def rescan_files(self, result):
        self.collect('files', lambda _: None)
        result['state'] = self.snapshot()
        return result

    # --- handlers ------------------------------------------------------

    def on_reset(self, v, progress):
        self.reset_state()
        return self.snapshot()

    def on_smart_pick(self, v, progress):
        chosen = ask_directory(self.smart.root or Path.home())
        if not chosen:
            return {'cancel': True}
        return self.smart.select(chosen)

    def on_refresh_space(self, v, progress):
        self.last_storage = None
        return self.snapshot(storage_view.measure([self.root]) if self.root else [])

    def on_folder_find(self, v, progress):
        if not self.root:
            raise ValueError('먼저 파일 정리에서 폴더를 선택하고 검사해 주세요.')
        return self.folder_compare.scan(self.root)

    def on_folder_bulk_remove(self, v, progress):
        return self.rescan_files(self.folder_compare.execute_bulk(v.get('token'), v.get('confirmed'), recycle))

    def on_folder_remove(self, v, progress):
        return self.rescan_files(self.folder_compare.move(v['token'], v.get('confirmed'), v.get('allow_unique'), recycle))

    def on_grouping(self, v, progress):
        mode = v.get('word_mode', 'off')
        keyword = v.get('keyword', '')
        similar = v.get('similar', False)
        if type(similar) is not bool:
            raise ValueError('비슷한 이름 설정을 확인해 주세요.')
        word_groups([], mode, keyword, similar)  # validate before changing the session
        grouped = organize_rows(self.raw_rows, mode, keyword, similar, self.keeper_mode, {})
        self.word_mode, self.word_keyword, self.similar_names = mode, keyword.strip(), similar
        self.rows = grouped
        self.overrides.clear()
        self.keeper_stamps = self.same_name_stamps()
        return self.snapshot()

    def on_keeper(self, v, progress):
        if 'mode' in v:
            if v['mode'] not in KEEPER_MODES:
                raise ValueError('남길 기준을 다시 선택해 주세요.')
            self.keeper_mode = v['mode']
            self.overrides.clear()
        elif v.get('id') in self.refs and self.refs[v['id']][0] == '같은 이름':
            row = self.refs[v['id']][1]
            if signature(row.path) != self.keeper_stamps.get(row.path):
                raise ValueError('파일이 바뀌었어요. 다시 검사해 주세요.')
            self.overrides[row.group] = row.path
        else:
            raise ValueError('같은 이름 목록에서 남길 파일을 골라 주세요.')
        self.rows = choose(self.rows, self.keeper_mode, self.overrides)
        return self.snapshot()

    def on_scan(self, v, progress):
        self.across = bool(v.get('across', False))
        if v.get('pick') or (self.root is None and v['mode'] != 'junk'):
            chosen = ask_directory(self.root or Path.home())
            if not chosen:
                return {'cancel': True}
            target = Path(chosen).absolute()
            if target != self.root:
                self.rows, self.junks, self.index, self.stash = [], [], [], []
                self.refs.clear()
            self.root = target
        last_update = 0.0

        def report(message):
            nonlocal last_update
            now = time.monotonic()
            if now - last_update >= 0.25:
                progress(message)
                last_update = now
        report('임시 파일을 확인하고 있어요.' if v['mode'] == 'junk' else '폴더 안의 파일을 확인하고 있어요.')
        self.collect(v['mode'], report)
        progress('검사 결과를 정리하고 있어요.')
        return self.snapshot()

    def on_empty_recycle(self, v, progress):
        if v.get('confirmed') is not True:
            raise ValueError('영구 삭제 확인이 필요해요.')
        error = None
        try:
            empty_recycle_bin(True)
        except OSError as e:
            error = str(e)
        self.last_storage = None
        return dict(state=self.snapshot(), remaining=storage_view.recycle_size(None), error=error)

    def on_rank(self, v, progress):
        for key in [k for k, (kind, _) in self.refs.items() if kind == FOLDER_SIZE]:
            del self.refs[key]
        if not self.index:
            return []
        children, direct, totals = self.index[0]
        p = Path(v['path']) if v.get('path') else self.root
        if p not in children:
            raise ValueError('검사한 폴더를 선택해 주세요.')
        # Build folder previews from the scan instead of walking every subtree again;
        # folder_ops.validate() re-reads the disk once, right before anything moves.
        files_below = {d: {} for d in children[p]}
        dirs_below = {d: [] for d in children[p]}
        for f, stamp in ((r.path, r.stamp) for r in self.rows if r.kind == '전체 파일'):
            top = top_child(p, f)
            if top in files_below:
                files_below[top][f] = stamp
        for d in children:
            top = top_child(p, d)
            if top in dirs_below and d != top:
                dirs_below[top].append(d)
        result = []
        for target in children[p] + [f for f, n in direct[p]]:
            if not target.exists():
                continue
            try:
                if target in files_below:
                    item = folder_ops.from_scan(self.root, target, files_below[target], dirs_below[target])
                    note = '폴더 전체와 하위 파일을 함께 이동해요.'
                else:
                    item = folder_ops.capture(self.root, target)
                    note = '선택한 파일만 이동해요.'
                modified = target.stat().st_mtime
                row = self.pack(target, item.size, note, FOLDER_SIZE, item)
                row.update(folder=item.folder, modified=modified, date=stamp_text(modified))
            except (OSError, ValueError) as e:
                row = dict(id=secrets.token_hex(10), path=str(target), name=windows_ui.display_name(target),
                           size=totals.get(target, [0])[0], folder=target.is_dir(), modified=0, date='확인 불가',
                           protected=True, note=str(e))
            if row['folder']:
                row['count'] = totals.get(target, [0, 0])[1]
            result.append(row)
        return result

    def on_open_file(self, v, progress):
        ref = self.refs.get(v.get('id'))
        if not ref or ref[0] in ('보관함', FOLDER_SIZE, '정크 파일'):
            raise ValueError('파일 정리 목록에서 파일을 골라 주세요.')
        p = ref[1].path
        if not p.is_file():
            raise ValueError('파일이 없거나 열 수 없어요. 다시 검사해 주세요.')
        try:
            os.startfile(str(p))
        except OSError as e:
            raise ValueError('파일을 열지 못했어요. 연결 프로그램이나 파일 위치를 확인해 주세요.') from e
        return {}

    def on_reveal(self, v, progress):
        p = Path(v['path'])
        if not self.root or not p.is_relative_to(self.root):
            if not any(r.path == p for r in self.junks):
                raise ValueError('검사한 파일을 골라 주세요.')
        if not p.exists():
            raise ValueError('원래 위치에 파일이 없어요. 다시 검사해 주세요.')
        subprocess.Popen(['explorer.exe', '/select,', str(p)])
        return {}

    def on_setup(self, v, progress):
        chrome_link.pairing_key()
        chrome_link.launch('chrome://extensions/')
        return {'path': str(chrome_link.HELPER)}

    def on_chrome(self, v, progress):
        # Runs in the background so this server keeps answering (pings, status polls)
        # while the Chrome tab waits for the user, for up to 15 minutes.
        def run():
            try:
                self.chrome_outcome = ('ok', chrome_link.run_cleanup())
            except Exception as e:
                self.chrome_outcome = ('error', str(e))
        self.chrome_outcome = None
        self.chrome_job = threading.Thread(target=run, daemon=True)
        self.chrome_job.start()
        return {'running': True}

    def on_chrome_status(self, v, progress):
        if self.chrome_job is None:
            raise ValueError('진행 중인 크롬 정리가 없어요. 다시 시작해 주세요.')
        if self.chrome_job.is_alive():
            return {'running': True}
        self.chrome_job = None
        status, result = self.chrome_outcome
        if status == 'error':
            raise ValueError(result)
        try:
            chrome_link.result_file().write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        except OSError:
            result['save_warning'] = '결과 저장에 실패했어요. 이 창에서 확인해 주세요.'
        return self.rescan_files(result) if self.root else result

    def on_apply(self, v, progress):
        root, refs = self.root, self.refs
        ids = list(dict.fromkeys(v['ids']))
        op = v['op']
        restore = op == 'restore'
        if op not in ('trash', 'restore') or not ids or any(k not in refs for k in ids):
            raise ValueError('목록을 다시 확인해 주세요.')
        kinds = {refs[k][0] for k in ids}
        if len(kinds) != 1 or ('보관함' in kinds) != restore or ('정크 파일' in kinds and op != 'trash') or 'ZIP 확인' in kinds:
            raise ValueError('같은 종류의 파일을 선택해 주세요.')
        selected = [refs[k][1] for k in ids]
        paths = set() if restore else {r.path for r in selected}
        keep = {r.group: r.path for r in self.rows
                if r.group and r.kind in kinds and r.path not in paths and r.path.is_file()}
        ok, errors = [], {}
        progress(dict(done=0, total=len(ids), success=0, failed=0, file='파일 상태 확인 중'))
        set_ids = set(ids)
        kept_paths = {item[0] if restore else item.path
                      for key, (kind, item) in refs.items() if kind in kinds and key not in set_ids}
        kept_paths.update(r.keep for r in selected if getattr(r, 'keep', None))
        report = CleanupResult(kept_paths)
        before_space = storage_view.measure([r[0] if restore else r.path for r in selected])
        moved_sizes = {k: 0 for k in [*storage_view.TYPES, '기타']}
        for step, (key, obj) in enumerate(zip(ids, selected), 1):
            current = obj[0] if restore else obj.path
            progress(dict(done=step - 1, total=len(ids), success=len(ok), failed=len(errors), file=current.name))
            entry = describe(current)
            try:
                if restore:
                    relocate(root, *obj)
                    entry['path'] = str(obj[1])
                    entry['name'] = obj[1].name
                elif FOLDER_SIZE in kinds:
                    folder_ops.validate(root, obj)
                    entry['size'] = obj.size
                    recycle(obj.path)
                elif '정크 파일' in kinds:
                    if (not junk.allowed(obj.root, obj.path) or signature(obj.path) != obj.stamp
                            or junk.reason(obj.path, obj.stamp, junk.user_temp()) != obj.reason):
                        raise ValueError('검사 후 바뀐 파일이에요. 다시 검사해 주세요.')
                    recycle(obj.path)
                else:
                    if obj.kind == '같은 이름':
                        if not obj.keep or obj.keep in paths:
                            raise ValueError('남길 파일을 지정한 뒤 다른 파일만 선택하세요.')
                        if signature(obj.keep) != self.keeper_stamps.get(obj.keep):
                            raise ValueError('남길 파일이 바뀌었어요. 다시 검사해 주세요.')
                    if obj.group and obj.kind != '같은 이름':
                        if obj.group not in keep:
                            raise ValueError('이 묶음에서 남길 파일 하나를 선택 해제하세요.')
                        obj = obj._replace(keep=keep[obj.group])
                    validate_row(root, obj)
                    recycle(obj.path)
                if not restore:
                    if getattr(obj, 'folder', False):
                        for relative, (isdir, stamp) in obj.tree.items():
                            if not isdir:
                                moved_sizes[storage_view.category(relative)] += stamp[0]
                    else:
                        moved_sizes[storage_view.category(current)] += entry.get('size') or 0
                report.moved.append(entry)
                ok.append(key)
            except Exception as e:
                errors[key] = str(e)
                report.failed.append(dict(entry, reason=str(e)))
            progress(dict(done=step, total=len(ids), success=len(ok), failed=len(errors), file=current.name))
        progress(dict(done=len(ids), total=len(ids), success=len(ok), failed=len(errors),
                      file='결과와 디스크 용량을 확인하고 있어요.', phase='finalizing'))
        gone = set() if restore else {refs[k][1].path for k in ok}

        def removed(path):
            return path in gone or any(parent in gone for parent in path.parents)
        self.raw_rows = [r for r in self.raw_rows if not removed(r.path)]
        self.rows = [r for r in self.rows if not removed(r.path)]
        self.junks = [r for r in self.junks if not removed(r.path)]
        self.rows = choose(self.rows, self.keeper_mode, self.overrides)
        if ok and self.index:
            dirs = {d for d in self.index[0][0] if not removed(d)}
            files = {r.path: r.stamp for r in self.rows if r.kind == '전체 파일' and r.path.parent in dirs}
            self.index = [folder_index(root, dirs, files)] if root in dirs else []
        if root and restore:
            try:
                self.stash = held(root)
            except OSError as e:
                self.logs.append(str(e))
        after_space = storage_view.measure([Path(volume['volume']) for volume in before_space])
        self.last_storage = storage_view.comparison(before_space, after_space, moved_sizes)
        result = report.finish()
        result['storage'] = self.last_storage
        return dict(ok=ok, errors=errors, state=self.snapshot(self.last_storage['after']), report=result)


def make_handler(app, token, host, origin):
    prefix = '/' + token + '/'
    streamed = ('apply', 'scan')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def response(self, code, data, typ):
            self.send_response(code)
            self.send_header('Content-Type', typ)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            name = self.path.removeprefix(prefix)
            if self.headers.get('Host') != host or not self.path.startswith(prefix) or name not in ASSETS:
                return self.send_error(404)
            file, typ = ASSETS[name]
            self.response(200, (BASE / file).read_bytes(), typ)

        def do_POST(self):
            if self.headers.get('Origin') != origin or self.headers.get('Host') != host or not self.path.startswith(prefix + 'api/'):
                return self.send_error(403)
            try:
                n = int(self.headers.get('Content-Length', 0))
                if not 0 <= n <= 8000000:
                    raise ValueError('요청이 너무 커요.')
                v = json.loads(self.rfile.read(n))
                action = self.path.rsplit('/', 1)[1]
                if action in streamed:
                    return self.stream(action, v)
                result = {} if action == 'ping' else app.dispatch(action, v)
                self.response(200, json.dumps(result).encode(), 'application/json')
            except Exception as e:
                self.response(400, json.dumps({'error': str(e)}).encode(), 'application/json')

        def stream(self, action, v):
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.close_connection = True

            def event(value):
                try:
                    self.wfile.write((json.dumps(value) + '\n').encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            try:
                event({'result': app.dispatch(action, v, lambda p: event({'progress': p}))})
            except Exception as e:
                event({'error': str(e)})

    return Handler


def start():
    windows_ui.enable_dpi()
    os.environ['TCL_LIBRARY'] = str(BASE / 'python/tcl/tcl8.6')
    os.environ['TK_LIBRARY'] = str(BASE / 'python/tcl/tk8.6')
    try:
        chrome = chrome_link.find_chrome()
    except FileNotFoundError:
        raise RuntimeError('이 버전은 Google Chrome이 필요해요. Chrome 설치 후 다시 실행해 주세요.')
    app = App()
    token = secrets.token_urlsafe(32)
    with HTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as server:
        host = f'127.0.0.1:{server.server_port}'
        origin = 'http://' + host
        server.RequestHandlerClass = make_handler(app, token, host, origin)
        server.timeout = 3
        subprocess.Popen([str(chrome), '--app=' + origin + '/' + token + '/'])
        last = time.monotonic()
        while time.monotonic() - last < IDLE_SECONDS:
            if select.select([server], [], [], 3)[0]:
                server.handle_request()
                last = time.monotonic()


if __name__ == '__main__':
    try:
        if sys.version_info < (3, 9):
            raise RuntimeError('Python 3.9 이상이 필요해요.')
        start()
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(None, str(e), '쓱-싹 실행 안내', 16)
