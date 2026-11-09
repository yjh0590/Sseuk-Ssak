"""Conservative candidates; all deletion requests go through Windows Shell."""
import ctypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from engine import APP, HOLD, plain, safe, signature

PROTECTED = {"bin", ".git", "node_modules", ".venv", "windows", "program files",
             "program files (x86)", "programdata", "$recycle.bin", HOLD.casefold()}
CACHE = {"thumbs.db": (bytes.fromhex("d0cf11e0a1b11ae1"), "Windows 미리보기 캐시"),
         ".ds_store": (b"\x00\x00\x00\x01Bud1", "macOS 폴더 표시 정보")}
WEEK = 7 * 24 * 3600

@dataclass(frozen=True)
class Candidate:
    root: Path
    path: Path
    stamp: tuple
    reason: str

def user_temp():
    local = os.environ.get("LOCALAPPDATA")
    return Path(local).absolute() / "Temp" if local else None

def protected(p):
    return p.is_relative_to(APP) or any(part.casefold() in PROTECTED for part in p.parts)

def allowed(root, p):
    if protected(p) or root == Path(root.anchor) or not safe(root, p):
        return False
    return all(plain(parent) for parent in root.parents) and p.is_file()

def reason(p, stamp, temp):
    if time.time() - stamp[1]/1e9 < WEEK:
        return None
    item = CACHE.get(p.name.casefold())
    if item:
        magic, label = item
        with p.open("rb") as f:
            if f.read(len(magic)) == magic:
                return label + " · 7일 이상 경과"
    if temp and p.is_relative_to(temp) and p.suffix.casefold() == ".tmp":
        return "사용자 Temp의 .tmp · 7일 이상 경과"
    return None

def collect(folder, temp):
    rows, errors = {}, []
    for root in dict.fromkeys(r for r in (temp, folder) if r):
        if not root.is_dir() or protected(root) or root == Path(root.anchor) or not all(plain(a) for a in (root, *root.parents)):
            continue
        for base, dirs, files in os.walk(root, onerror=lambda e: errors.append(str(e))):
            base = Path(base)
            good = []
            for d in dirs:
                try:
                    if not protected(base/d) and plain(base/d):
                        good.append(d)
                except OSError as e:
                    errors.append(str(e))
            dirs[:] = good
            for name in files:
                p = base/name
                if p in rows or (name.casefold() not in CACHE and p.suffix.lower() != ".tmp"):
                    continue
                try:
                    if allowed(root, p):
                        stamp = signature(p)
                        label = reason(p, stamp, temp)
                        if label:
                            rows[p] = Candidate(root, p, stamp, label)
                except OSError as e:
                    errors.append(str(e))
    return sorted(rows.values(),key=lambda r:-r.stamp[0]),errors

def recycle_files(paths):
    from ctypes import wintypes as w
    class Operation(ctypes.Structure):
        if ctypes.sizeof(ctypes.c_void_p) == 4:
            _pack_ = 1
        _fields_ = [("window",w.HWND),("func",w.UINT),("source",w.LPCWSTR),
                    ("dest",w.LPCWSTR),("flags",w.WORD),("aborted",w.BOOL),
                    ("mapping",w.HANDLE),("title",w.LPCWSTR)]
    for p in paths:
        if not p.is_absolute() or any(c in str(p) for c in "*?") or len(str(p).encode("utf-16-le"))//2 >= 260 or ctypes.windll.kernel32.GetDriveTypeW(str(p.anchor)) != 3:
            raise ValueError("로컬 고정 드라이브의 일반 경로만 휴지통으로 보낼 수 있어요.")
    src = ctypes.create_unicode_buffer("\0".join(map(str, paths))+"\0")
    op = Operation()
    op.func = 3  # FO_DELETE
    op.source = ctypes.cast(src,w.LPCWSTR)
    op.flags = 0x0040 | 0x4000 | 0x0010 | 0x1000  # allow undo, permanent warning, no routine confirmation, no recursion
    call = ctypes.windll.shell32.SHFileOperationW
    call.argtypes,call.restype = [ctypes.POINTER(Operation)],ctypes.c_int
    code = call(ctypes.byref(op))
    if code or op.aborted:
        raise OSError(f"일부 파일이 사용 중이거나 작업이 취소됐어요. Windows 결과 {code}")

def clean(rows, temp, send=recycle_files, completed=None):
    ready, errors = [], []
    for r in rows:
        try:
            if not allowed(r.root,r.path) or signature(r.path)!=r.stamp or reason(r.path,r.stamp,temp)!=r.reason:
                raise ValueError("검사 후 변경되어 제외")
            ready.append(r.path)
        except (ValueError,OSError) as e:
            errors.append(f"{r.path} · {e}")
    if ready:
        try: send(ready)
        except (OSError,ValueError) as e: errors.append(str(e))
    moved = [p for p in ready if not os.path.lexists(p)]
    if completed is not None: completed.extend(moved)
    return len(moved), errors
