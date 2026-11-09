"""Local scanner and reversible staging area. Python 3.9+."""
from analysis_views import grouped, folder_index
import hashlib
import re
import os
import stat
import uuid
import zipfile
import zlib
from collections import defaultdict, namedtuple
from pathlib import Path

HOLD = "_ODDZ_정리보관함"
Row = namedtuple("Row", "kind path size stamp detail keep group", defaults=(None,None))
APP = Path(__file__).resolve().parent
CHUNK = 1024 * 1024
DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in "0123456789¹²³"
}

def plain(path):
    s = path.lstat()
    return not (stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400)

def safe(root, p):
    if not p.is_relative_to(root) or p == root:
        return False
    return all(plain(a) for a in (p, *p.parents) if a.is_relative_to(root))

def digest(stream):
    h = hashlib.sha256()
    for buf in iter(lambda: stream.read(CHUNK), b""):
        h.update(buf)
    return h.digest()

def signature(p):
    s = p.stat()
    return (s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino)

def filehash(p):
    with p.open("rb") as f:
        return digest(f)

def zipcheck(root, p):
    folder = p.with_suffix("")
    if not folder.is_dir() or not safe(root, folder):
        return None
    with zipfile.ZipFile(p) as z:
        infos = z.infolist()
        if len(infos) > 20000 or sum(i.file_size for i in infos) > 8 * 1024**3:
            return False, "검사 한도 초과", folder
        count = 0
        seen = set()
        for i in infos:
            parts = i.filename.rstrip("/").split("/")
            if (any(not x or x in {".", ".."} or x.endswith((" ", ".")) or
                    any(c in x for c in '\\:<>"|?*') or x.split('.')[0].rstrip().upper() in DEVICES for x in parts)
                    or stat.S_ISLNK(i.external_attr >> 16) or i.flag_bits & 1):
                return False, "특수 경로 또는 암호화 항목", folder
            key = tuple(x.casefold() for x in parts)
            if key in seen:
                return False, "내부 경로 중복", folder
            seen.add(key)
            dest = folder.joinpath(*parts)
            if not dest.exists() or not safe(root, dest):
                return False, "폴더에 없거나 확인 불가 · " + i.filename, folder
            if i.is_dir():
                if not dest.is_dir():
                    return False, "폴더 구조 다름", folder
                continue
            if not dest.is_file() or dest.stat().st_size != i.file_size:
                return False, "내용 다름 · " + i.filename, folder
            with z.open(i) as src:
                if digest(src) != filehash(dest):
                    return False, "내용 다름 · " + i.filename, folder
            count += 1
        return bool(count), f"ZIP 안의 파일 {count}개가 폴더에 모두 있음", folder

def scan(root, progress=lambda s: None, folder_data=None, across=False):
    root = Path(root).absolute()
    if root == Path(root.anchor) or not plain(root) or root.is_relative_to(APP) or HOLD in root.parts:
        raise ValueError("다운로드나 문서처럼 검사할 개인 폴더를 선택해 주세요.")
    files, errors, rows = {}, [], []
    sizes, names = defaultdict(list), defaultdict(list)
    def onerror(e):
        errors.append(str(e))
    visited = []
    for folder, dirs, leaves in os.walk(root, onerror=onerror):
        base = Path(folder)
        visited.append(base)
        good = []
        for d in dirs:
            try:
                if d.casefold() != HOLD.casefold() and base/d != APP and plain(base/d):
                    good.append(d)
            except OSError as e:
                onerror(e)
        dirs[:] = good
        for n in leaves:
            if n.casefold()=="desktop.ini":continue
            p = base/n
            try:
                if not plain(p) or not p.is_file():
                    continue
                sig = signature(p)
                files[p] = sig
                sizes[sig[0]].append(p)
                names[(None if across else base, re.sub(r"\s*\(\d+\)$", "", p.stem).casefold(), p.suffix.casefold())].append(p)
            except OSError as e:
                onerror(e)
        progress(f"목록 확인 중 · {len(files):,}개")
    def add(kind, p, note, keep=None):
        rows.append(Row(kind, p, files[p][0], files[p], note, keep))
    def newest(group):
        return sorted(group, key=lambda p: (-files[p][1], str(p).casefold(), str(p)))
    for group in sizes.values():
        if len(group) < 2:
            continue
        same = defaultdict(list)
        for p in group:
            progress("내용 비교 · " + p.name)
            try:
                same[filehash(p)].append(p)
            except OSError as e:
                onerror(e)
        for g in same.values():
            keep, *others = newest(g)
            for p in others:
                add("복사본", p, "동일 내용 · 남길 파일 " + str(keep.relative_to(root)), keep)
    for g in names.values():
        if len(g) > 1:
            keep, *others = newest(g)
            tied = files[keep][1] == files[others[0]][1]
            group = str(keep)
            for p in newest(g):
                note = "날짜가 같아 직접 확인이 필요해요" if tied else ("남길 최신 파일" if p == keep else "오래된 파일 · 남길 파일 " + str(keep))
                rows.append(Row("같은 이름", p, files[p][0], files[p], note, None if tied or p == keep else keep, group))
    for p in files:
        add("전체 파일", p, "직접 선택한 파일만 휴지통으로 이동해요")
    for p in files:
        if p.suffix.lower() == ".zip":
            progress("압축 비교 · " + p.name)
            try:
                result = zipcheck(root, p)
                if result:
                    matched, note, folder = result
                    add("풀어둔 ZIP" if matched else "ZIP 확인", p, note, folder)
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, EOFError, zlib.error) as e:
                errors.append(f"{p}: {e}")
    for p in sorted(files, key=lambda p: -files[p][0])[:30]:
        add("큰 파일", p, "크기순 상위 30개 · 직접 검토")
    for kind,p,group,reason in grouped(files):
        rows.append(Row(kind,p,files[p][0],files[p],reason,None,group))
    if folder_data is not None and root in visited:
        folder_data.append(folder_index(root,visited,files))
    return rows, len(files), errors

def validate_row(root, row):
    p = row.path
    if p.name.casefold()=="desktop.ini":raise ValueError("Windows 폴더 표시 설정 파일은 보호해요.")
    if (not safe(root, p) or not p.is_file() or signature(p) != row.stamp
            or row.kind == "ZIP 확인"):
        raise ValueError("파일이 바뀌었거나 보관할 수 없는 항목입니다.")
    if row.keep and not safe(root, row.keep):
        raise ValueError("남길 파일 경로를 확인할 수 없습니다.")
    if row.group is not None and (not row.keep or not row.keep.is_file()):
        raise ValueError("묶음에 남길 파일을 확인할 수 없습니다.")
    if row.kind == "복사본" and filehash(p) != filehash(row.keep):
        raise ValueError("남길 파일 내용이 바뀌었습니다.")
    if row.kind == "같은 이름" and (not row.keep or not row.keep.is_file()):
        raise ValueError("남길 파일을 다시 확인해 주세요.")
    if row.kind == "풀어둔 ZIP":
        check = zipcheck(root, p)
        if not check or not check[0]:
            raise ValueError("압축 내용이 달라졌습니다.")

def stage(root, row, batch):
    validate_row(root,row)
    p = row.path
    dest = root/HOLD/batch/p.relative_to(root)
    relocate(root, p, dest)

def relocate(root, src, dest):
    if not safe(root, src) or not src.is_file():
        raise ValueError("원본 경로를 확인할 수 없습니다.")
    for parent in reversed(dest.parents):
        if parent.is_relative_to(root) and parent != root:
            if not parent.exists():
                parent.mkdir()
            if not plain(parent) or not parent.is_dir():
                raise ValueError("대상 폴더 경로를 확인할 수 없습니다.")
    if os.path.lexists(dest):
        raise FileExistsError("같은 경로에 파일이 있어 덮어쓰지 않았습니다.")
    # On Windows rename fails if another file appears at dest.
    src.rename(dest)

def held(root):
    folder = root/HOLD
    if not folder.exists() or not safe(root, folder):
        return []
    items = []
    for base, dirs, names in os.walk(folder):
        b = Path(base)
        dirs[:] = [d for d in dirs if plain(b/d)]
        for n in names:
            p = b/n
            parts = p.relative_to(folder).parts
            if len(parts) >= 2 and len(parts[0]) == 32 and all(c in "0123456789abcdef" for c in parts[0]) and safe(root, p):
                items.append((p, root.joinpath(*parts[1:])))
    return items

def newbatch():
    return uuid.uuid4().hex
