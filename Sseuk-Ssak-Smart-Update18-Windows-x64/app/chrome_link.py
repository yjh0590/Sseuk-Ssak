"""One-shot localhost bridge between the desktop app and Chrome."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
HELPER = APP_DIR.parent / "크롬 다운로드 연결 도우미"


def pairing_key():
    p = HELPER / "pair.json"
    if not p.exists():
        try:
            with p.open("x", encoding="utf-8") as f:
                json.dump(secrets.token_hex(32), f)
        except FileExistsError:
            pass
    return bytes.fromhex(json.loads(p.read_text(encoding="utf-8")))


def find_chrome():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as k:
                exe = Path(winreg.QueryValueEx(k, None)[0].strip('"'))
            if exe.is_file():
                return exe
        except OSError:
            pass
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if env in os.environ:
            exe = Path(os.environ[env]) / "Google/Chrome/Application/chrome.exe"
            if exe.is_file():
                return exe
    raise FileNotFoundError("Google Chrome 설치 위치를 찾지 못했어요.")


def launch(url):
    subprocess.Popen([str(find_chrome()), url])


def run_cleanup(open_browser=launch, timeout=900):
    key = pairing_key()
    public = json.loads((HELPER / "manifest.json").read_text(encoding="utf-8"))["key"]
    hex_id = hashlib.sha256(base64.b64decode(public)).hexdigest()[:32]
    extension = "".join(chr(97 + int(c, 16)) for c in hex_id)
    path = "/oddz-clean/" + secrets.token_hex(24)
    report = []
    from chrome_files import Session
    from recycle import recycle
    session=Session()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def valid(self):
            return self.headers.get("Host") == host and self.path == path

        def do_GET(self):
            if not self.valid():
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(page.encode())

        def do_POST(self):
            if not self.valid() or self.headers.get('Origin') != origin:return self.send_error(403)
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 1<=length<=16000000:raise ValueError('요청이 너무 커요.')
                value=json.loads(self.rfile.read(length));action=value.get('action')
                if action=='inspect':result=session.inspect(value['items'])
                elif action=='policy':result=session.policy(value)
                elif action=='start':result=session.start(value['ids'])
                elif action=='move':
                    result=session.move(value['id'],recycle)
                    payload=','.join(map(str,sorted(result['recordIds'])))
                    result['eraseProof']=hmac.new(key,f'{url}|{expires}|{payload}'.encode(),'sha256').hexdigest()
                    try:(APP_DIR/'chrome-last-result.json').write_text(json.dumps(session.finish(),ensure_ascii=False),encoding='utf-8')
                    except OSError:pass
                elif action=='finish':
                    result=session.finish(value.get('record_failed',[]));report.append(result)
                else:raise ValueError('작업을 확인해 주세요.')
                self.send_response(200)
            except Exception as e:
                result={'error':str(e)};self.send_response(400)
            data=json.dumps(result).encode()
            self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        host = f"127.0.0.1:{server.server_port}"
        origin = "http://" + host
        url = origin + path
        expires = int(time.time()) + timeout
        proof = hmac.new(key, f"{url}|{expires}".encode(), "sha256").hexdigest()
        data = json.dumps(dict(task="preview", expires=expires, proof=proof))
        page = (APP_DIR / "chrome-progress.html").read_text(encoding="utf-8").replace("EXTENSION_ID",extension).replace("REQUEST_DATA",data).replace("STORAGE_SCRIPT",(APP_DIR/"storage.js").read_text(encoding="utf-8"))
        open_browser(url)
        server.timeout = 0.4
        deadline = time.monotonic() + timeout
        while not report and time.monotonic() < deadline:
            server.handle_request()
    if not report and session.started:return session.finish([{'name':'기록 정리','path':'','reason':'탭이 닫혔거나 연결 시간이 끝났어요. 실제 파일 결과를 확인하고 기록은 다시 확인하세요.'}])
    if not report:
        raise RuntimeError("크롬의 응답을 받지 못했어요. 열린 탭과 확장 연결을 확인해 주세요.")
    if report[0] == "setup":
        raise RuntimeError("이 크롬 프로필에 연결 도우미를 등록해 주세요. 앱의 ‘처음 연결’을 누르세요.")
    if report[0] == "error":
        raise RuntimeError("크롬에서 정리를 완료하지 못했어요. 열린 탭에서 안내를 확인하세요.")
    return report[0]
