"""Serve the desktop renderer on a private, short-lived loopback address."""

import ctypes
import json
import os
import secrets
import select
import subprocess
import sys
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
from local_groups import choose_keepers as choose
from local_groups import organize_rows
from recycle import empty_recycle_bin, recycle
from result_view import CleanupResult, describe
from smart_service import SmartService

BASE = Path(__file__).resolve().parent
FILTERS = ['같은 이름', '전체 파일', '복사본', '풀어둔 ZIP', '작업 버전', '변환 파일', '큰 파일', 'ZIP 확인']
# 요청 경로 → (파일, Content-Type)
ASSETS = {
    '': ('index.html', 'text/html; charset=utf-8'),
    'style.css': ('style.css', 'text/css'),
    'ui.js': ('ui.js', 'text/javascript'),
    'storage.js': ('storage.js', 'text/javascript'),
    'layout_scale.js': ('layout_scale.js', 'text/javascript'),
    'folder_ui.js': ('folder_ui.js', 'text/javascript'),
    'smart_ui.js': ('smart_ui.js', 'text/javascript'),
    'icon.ico': ('Sseuk-Ssak.ico', 'image/x-icon'),
    'mark.png': ('mark.png', 'image/png'),
    'font.ttf': ('fonts/SseukSsakDance.ttf', 'font/ttf'),
}
# 열면 실행되는 형식. 파일 열기 대신 탐색기에서 위치만 보여 준다.
EXECUTABLE = set(
    '.exe .com .bat .cmd .msi .msp .scr .pif .lnk .url .reg .hta .cpl .msc .jar '
    '.ps1 .psm1 .vbs .vbe .js .jse .wsf .wsh .appref-ms .application .settingcontent-ms'.split()
)
STREAMED = ('apply', 'scan')  # 진행률을 NDJSON으로 흘려보내는 작업


def ask_folder(initial):
    import tkinter as tk
    from tkinter import filedialog

    win = tk.Tk()
    win.withdraw()
    win.attributes('-topmost', True)
    try:
        return filedialog.askdirectory(parent=win, initialdir=initial)
    finally:
        win.destroy()


def stamp_text(ns):
    return time.strftime('%Y.%m.%d %H:%M:%S', time.localtime(ns / 1e9))


class App:
    """화면 한 개의 세션 상태와 작업들. recycle/pick_folder는 테스트에서 바꿔 끼운다."""

    def __init__(self, recycle=recycle, pick_folder=ask_folder):
        self.recycle = recycle
        self.pick_folder = pick_folder
        self.smart = SmartService()
        self.folder_compare = FolderCompare()
        self.reset_state()
        self.actions = {
            'ping': lambda v, progress: {},
            'init': lambda v, progress: self.snapshot(),
            'reset': self.reset,
            'smart_pick': self.smart_pick,
            'smart': lambda v, progress: self.smart.handle(v),
            'refresh_space': self.refresh_space,
            'folder_find': self.folder_find,
            'folder_bulk_prepare': lambda v, progress: self.folder_compare.prepare_bulk(v.get('ids')),
            'folder_bulk_remove': self.folder_bulk_remove,
            'folder_compare': lambda v, progress: self.folder_compare.compare(v['source'], v['reference']),
            'folder_remove': self.folder_remove,
            'grouping': self.grouping,
            'keeper': self.keeper,
            'scan': self.scan,
            'recycle_info': lambda v, progress: {'size': storage_view.recycle_size(None)},
            'empty_recycle': self.empty_recycle,
            'repair_downloads': lambda v, progress: windows_ui.restore_downloads_label(BASE / 'display-backup'),
            'rank': self.rank,
            'open_file': self.open_file,
            'reveal': self.reveal,
            'setup': self.setup,
            'chrome': self.chrome,
            'apply': self.apply,
        }

    def handle(self, action, v, progress=lambda event: None):
        if action not in self.actions:
            raise ValueError('작업을 찾지 못했어요.')
        return self.actions[action](v, progress)

    # ── 상태 ──────────────────────────────────────────────
    def reset_state(self):
        self.root = None
        self.rows = []  # 화면에 보이는 분류 결과
        self.raw_rows = []  # 묶기 설정을 바꿀 때 다시 쓰는 원본 검사 결과
        self.stash = []  # 옛 보관함 (보관 위치, 원래 위치)
        self.index = []  # 폴더 용량 색인
        self.junks = []
        self.logs = []
        self.refs = {}  # 화면에 내보낸 id → (분류, 객체)
        self.across = False
        self.keeper_mode = 'date'
        self.keeper_stamps = {}
        self.overrides = {}
        self.last_storage = None
        self.word_mode = 'off'
        self.word_keyword = ''
        self.similar_names = False

    def pack(self, p, n, reason, kind, obj, group=None):
        key = secrets.token_hex(10)
        self.refs[key] = (kind, obj)
        return dict(
            id=key, path=str(p), name=windows_ui.display_name(p), size=n, note=reason, kind=kind, group=str(group or '')
        )

    def collect(self, kind, report):
        if kind == 'junk':
            self.junks, self.logs = junk.collect(self.root, junk.user_temp())
            return
        self.index = []
        self.last_storage = None
        rows, _, self.logs = scan(self.root, progress=report, folder_data=self.index, across=self.across)
        self.raw_rows = list(rows)
        rows = organize_rows(
            self.raw_rows, self.word_mode, self.word_keyword, self.similar_names, self.keeper_mode, self.overrides
        )
        self.stash = held(self.root)
        self.keeper_stamps = {r.path: r.stamp for r in rows if r.kind == '같은 이름'}
        self.overrides.clear()
        self.rows = choose(rows, self.keeper_mode, self.overrides)

    def snapshot(self, space=None):
        self.refs.clear()
        files = [
            self.pack(r.path, r.size, r.detail, r.kind, r, r.group)
            | {
                'compare': str(r.keep or ''),
                'date': stamp_text(r.stamp[1]),
                'protected': r.kind == '같은 이름' and not r.keep,
            }
            for r in self.rows
        ]
        temp = [self.pack(r.path, r.stamp[0], r.reason, '정크 파일', r) for r in self.junks]
        saved = []
        for p, d in self.stash:
            try:
                saved.append(
                    self.pack(d, p.stat().st_size, '원래 위치로 복원할 수 있어요.', '보관함', (p, d))
                    | {'reveal': str(p)}
                )
            except OSError:
                pass
        if space is None:
            space = storage_view.measure([self.root]) if self.root else []
        return dict(
            root=str(self.root or ''),
            files=files,
            junk=temp,
            stash=saved,
            logs=self.logs,
            temp=str(junk.user_temp() or ''),
            filters=FILTERS,
            chrome_report=self.chrome_history(),
            keeper_mode=self.keeper_mode,
            word_mode=self.word_mode,
            word_keyword=self.word_keyword,
            similar_names=self.similar_names,
            root_name=windows_ui.display_name(self.root) if self.root else '',
            extensions=sorted(
                {r.path.suffix.lower().lstrip('.') for r in self.rows if r.kind == '전체 파일' and r.path.suffix}
            ),
            storage_current=space,
            storage_comparison=self.last_storage,
        )

    def chrome_history(self):
        try:
            return json.loads((BASE / 'chrome-last-result.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def rescan_files(self, result):
        self.collect('files', lambda _: None)
        result['state'] = self.snapshot()
        return result

    # ── 작업 ──────────────────────────────────────────────
    def reset(self, v, progress):
        self.reset_state()
        return self.snapshot()

    def smart_pick(self, v, progress):
        chosen = self.pick_folder(self.smart.root or Path.home())
        if not chosen:
            return {'cancel': True}
        return self.smart.select(chosen)

    def refresh_space(self, v, progress):
        self.last_storage = None
        return self.snapshot(storage_view.measure([self.root]) if self.root else [])

    def folder_find(self, v, progress):
        if not self.root:
            raise ValueError('먼저 파일 정리에서 폴더를 선택하고 검사해 주세요.')
        return self.folder_compare.scan(self.root)

    def folder_bulk_remove(self, v, progress):
        return self.rescan_files(self.folder_compare.execute_bulk(v.get('token'), v.get('confirmed'), self.recycle))

    def folder_remove(self, v, progress):
        return self.rescan_files(
            self.folder_compare.move(v['token'], v.get('confirmed'), v.get('allow_unique'), self.recycle)
        )

    def grouping(self, v, progress):
        mode = v.get('word_mode', 'off')
        keyword = v.get('keyword', '')
        similar = v.get('similar', False)
        if type(similar) is not bool:
            raise ValueError('비슷한 이름 설정을 확인해 주세요.')
        word_groups([], mode, keyword, similar)  # 세션을 바꾸기 전에 입력 검증
        grouped = organize_rows(self.raw_rows, mode, keyword, similar, self.keeper_mode, {})
        self.word_mode, self.word_keyword, self.similar_names = mode, keyword.strip(), similar
        self.rows = grouped
        self.overrides.clear()
        self.keeper_stamps = {r.path: r.stamp for r in self.rows if r.kind == '같은 이름'}
        return self.snapshot()

    def keeper(self, v, progress):
        if 'mode' in v:
            if v['mode'] not in ('date', 'number', 'manual', 'version'):
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

    def scan(self, v, progress):
        self.across = bool(v.get('across', False))
        if v.get('pick') or (self.root is None and v['mode'] != 'junk'):
            chosen = self.pick_folder(self.root or Path.home())
            if not chosen:
                return {'cancel': True}
            target = Path(chosen).absolute()
            if target != self.root:
                self.rows, self.junks, self.index, self.stash = [], [], [], []
                self.refs.clear()
            self.root = target
        last_update = 0.0

        def report(message):  # 진행 메시지는 0.25초에 한 번만
            nonlocal last_update
            now = time.monotonic()
            if now - last_update >= 0.25:
                progress(message)
                last_update = now

        report('임시 파일을 확인하고 있어요.' if v['mode'] == 'junk' else '폴더 안의 파일을 확인하고 있어요.')
        self.collect(v['mode'], report)
        progress('검사 결과를 정리하고 있어요.')
        return self.snapshot()

    def empty_recycle(self, v, progress):
        if v.get('confirmed') is not True:
            raise ValueError('영구 삭제 확인이 필요해요.')
        error = None
        try:
            empty_recycle_bin(True)
        except OSError as e:
            error = str(e)
        self.last_storage = None
        return dict(state=self.snapshot(), remaining=storage_view.recycle_size(None), error=error)

    def rank(self, v, progress):
        for k in list(self.refs):
            if self.refs[k][0] == '폴더 용량':
                del self.refs[k]
        if not self.index:
            return []
        children, direct, totals = self.index[0]
        p = Path(v['path']) if v.get('path') else self.root
        if p not in children:
            raise ValueError('검사한 폴더를 선택해 주세요.')
        result = []
        for target in children[p] + [f for f, n in direct[p]]:
            if not target.exists():
                continue
            try:
                item = folder_ops.capture(self.root, target)
                note = '폴더 전체와 하위 파일을 함께 이동해요.' if item.folder else '선택한 파일만 이동해요.'
                row = self.pack(target, item.size, note, '폴더 용량', item)
                modified = target.stat().st_mtime
                row.update(folder=item.folder, modified=modified, date=stamp_text(modified * 1e9))
            except (OSError, ValueError) as e:
                row = dict(
                    id=secrets.token_hex(10),
                    path=str(target),
                    name=windows_ui.display_name(target),
                    size=totals.get(target, [0])[0],
                    folder=target.is_dir(),
                    modified=0,
                    date='확인 불가',
                    protected=True,
                    note=str(e),
                )
            result.append(row)
        return result

    def open_file(self, v, progress):
        ref = self.refs.get(v.get('id'))
        if not ref or ref[0] in ('보관함', '폴더 용량', '정크 파일'):
            raise ValueError('파일 정리 목록에서 파일을 골라 주세요.')
        p = ref[1].path
        if not p.is_file():
            raise ValueError('파일이 없거나 열 수 없어요. 다시 검사해 주세요.')
        if p.suffix.lower() in EXECUTABLE:
            subprocess.Popen(['explorer.exe', '/select,', str(p)])
            raise ValueError('실행될 수 있는 파일이라 바로 열지 않았어요. 탐색기에서 위치를 보여 드렸어요.')
        try:
            os.startfile(str(p))
        except OSError as e:
            raise ValueError('파일을 열지 못했어요. 연결 프로그램이나 파일 위치를 확인해 주세요.') from e
        return {}

    def reveal(self, v, progress):
        p = Path(v['path'])
        if not self.root or not p.is_relative_to(self.root):
            if not any(r.path == p for r in self.junks):
                raise ValueError('검사한 파일을 골라 주세요.')
        if not p.exists():
            raise ValueError('원래 위치에 파일이 없어요. 다시 검사해 주세요.')
        subprocess.Popen(['explorer.exe', '/select,', str(p)])
        return {}

    def setup(self, v, progress):
        chrome_link.pairing_key()
        chrome_link.launch('chrome://extensions/')
        return {'path': str(chrome_link.HELPER)}

    def chrome(self, v, progress):
        result = chrome_link.run_cleanup()
        try:
            (BASE / 'chrome-last-result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        except OSError:
            result['save_warning'] = '결과 저장에 실패했어요. 이 창에서 확인해 주세요.'
        return self.rescan_files(result) if self.root else result

    def apply(self, v, progress):
        """선택한 항목을 휴지통으로 보내거나(trash) 옛 보관함에서 되돌린다(restore)."""
        refs = self.refs
        ids = list(dict.fromkeys(v['ids']))
        op = v['op']
        if op not in ('trash', 'restore') or not ids or any(k not in refs for k in ids):
            raise ValueError('목록을 다시 확인해 주세요.')
        kinds = {refs[k][0] for k in ids}
        restore = op == 'restore'
        if (
            len(kinds) != 1
            or ('보관함' in kinds) != restore
            or ('정크 파일' in kinds and op != 'trash')
            or 'ZIP 확인' in kinds
        ):
            raise ValueError('같은 종류의 파일을 선택해 주세요.')
        selected = [refs[k][1] for k in ids]
        source = (lambda obj: obj[0]) if restore else (lambda obj: obj.path)
        paths = set() if restore else {r.path for r in selected}
        # 묶음마다 선택되지 않은 파일 하나를 남길 파일로 잡아 둔다.
        keep = {
            r.group: r.path
            for r in self.rows
            if r.group and r.kind in kinds and r.path not in paths and r.path.is_file()
        }
        ok, errors = [], {}
        progress(dict(done=0, total=len(ids), success=0, failed=0, file='파일 상태 확인 중'))
        kept_paths = {source(item) for key, (kind, item) in refs.items() if kind in kinds and key not in set(ids)}
        kept_paths.update(r.keep for r in selected if getattr(r, 'keep', None))
        report = CleanupResult(kept_paths)
        before_space = storage_view.measure([source(r) for r in selected])
        moved_sizes = {k: 0 for k in [*storage_view.TYPES, '기타']}
        for step, (key, obj) in enumerate(zip(ids, selected), 1):
            current = source(obj)
            progress(dict(done=step - 1, total=len(ids), success=len(ok), failed=len(errors), file=current.name))
            entry = describe(current)
            try:
                if restore:
                    relocate(self.root, *obj)
                    entry['path'], entry['name'] = str(obj[1]), obj[1].name
                elif '폴더 용량' in kinds:
                    folder_ops.validate(self.root, obj)
                    entry['size'] = obj.size
                    self.recycle(obj.path)
                elif '정크 파일' in kinds:
                    if (
                        not junk.allowed(obj.root, obj.path)
                        or signature(obj.path) != obj.stamp
                        or junk.reason(obj.path, obj.stamp, junk.user_temp()) != obj.reason
                    ):
                        raise ValueError('검사 후 바뀐 파일이에요. 다시 검사해 주세요.')
                    self.recycle(obj.path)
                else:
                    if obj.kind == '같은 이름':
                        if not obj.keep or obj.keep in paths:
                            raise ValueError('남길 파일을 지정한 뒤 다른 파일만 선택하세요.')
                        if signature(obj.keep) != self.keeper_stamps.get(obj.keep):
                            raise ValueError('남길 파일이 바뀌었어요. 다시 검사해 주세요.')
                    elif obj.group:
                        if obj.group not in keep:
                            raise ValueError('이 묶음에서 남길 파일 하나를 선택 해제하세요.')
                        obj = obj._replace(keep=keep[obj.group])
                    validate_row(self.root, obj)
                    self.recycle(obj.path)
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
        progress(
            dict(
                done=len(ids),
                total=len(ids),
                success=len(ok),
                failed=len(errors),
                file='결과와 디스크 용량을 확인하고 있어요.',
                phase='finalizing',
            )
        )
        self.forget(set() if restore else {refs[k][1].path for k in ok}, ok)
        if self.root and restore:
            try:
                self.stash = held(self.root)
            except OSError as e:
                self.logs.append(str(e))
        after_space = storage_view.measure([Path(x['volume']) for x in before_space])
        self.last_storage = storage_view.comparison(before_space, after_space, moved_sizes)
        result = report.finish()
        result['storage'] = self.last_storage
        return dict(ok=ok, errors=errors, state=self.snapshot(self.last_storage['after']), report=result)

    def forget(self, gone, ok):
        """옮긴 파일(과 옮긴 폴더 안의 파일)을 목록과 폴더 색인에서 뺀다."""

        def removed(path):
            return path in gone or any(parent in gone for parent in path.parents)

        self.raw_rows = [r for r in self.raw_rows if not removed(r.path)]
        self.rows = choose([r for r in self.rows if not removed(r.path)], self.keeper_mode, self.overrides)
        self.junks = [r for r in self.junks if not removed(r.path)]
        if ok and self.index:
            dirs = {d for d in self.index[0][0] if not removed(d)}
            files = {r.path: r.stamp for r in self.rows if r.kind == '전체 파일' and r.path.parent in dirs}
            self.index = [folder_index(self.root, dirs, files)] if self.root in dirs else []


def serve(app, browser):
    token = secrets.token_urlsafe(32)

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
            name = self.path.removeprefix('/' + token + '/')
            if self.headers.get('Host') != host or not self.path.startswith('/' + token + '/') or name not in ASSETS:
                return self.send_error(404)
            file, typ = ASSETS[name]
            self.response(200, (BASE / file).read_bytes(), typ)

        def do_POST(self):
            if (
                self.headers.get('Origin') != origin
                or self.headers.get('Host') != host
                or not self.path.startswith('/' + token + '/api/')
            ):
                return self.send_error(403)
            try:
                n = int(self.headers.get('Content-Length', 0))
                if not 0 <= n <= 8000000:
                    raise ValueError('요청이 너무 커요.')
                v = json.loads(self.rfile.read(n))
                action = self.path.rsplit('/', 1)[1]
                if action in STREAMED:
                    return self.stream(action, v)
                self.response(200, json.dumps(app.handle(action, v)).encode(), 'application/json')
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
                event({'result': app.handle(action, v, lambda p: event({'progress': p}))})
            except Exception as e:
                event({'error': str(e)})

    with HTTPServer(('127.0.0.1', 0), Handler) as server:
        host = f'127.0.0.1:{server.server_port}'
        origin = 'http://' + host
        server.timeout = 3
        subprocess.Popen([str(browser), '--app=' + origin + '/' + token + '/'])
        last = time.monotonic()
        while time.monotonic() - last < 180:  # 창이 닫혀 핑이 3분간 없으면 종료
            if select.select([server], [], [], 3)[0]:
                server.handle_request()
                last = time.monotonic()


def start():
    windows_ui.enable_dpi()
    os.environ['TCL_LIBRARY'] = str(BASE / 'python/tcl/tcl8.6')
    os.environ['TK_LIBRARY'] = str(BASE / 'python/tcl/tk8.6')
    try:
        browser = chrome_link.find_browser()
    except FileNotFoundError as e:
        raise RuntimeError(str(e))
    serve(App(), browser)


if __name__ == '__main__':
    try:
        if sys.version_info < (3, 9):
            raise RuntimeError('Python 3.9 이상이 필요해요.')
        start()
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(None, str(e), '쓱-싹 실행 안내', 16)
