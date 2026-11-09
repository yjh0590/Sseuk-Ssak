"""DPI setup and a narrowly scoped Downloads display-name repair."""

import functools
import ctypes as c
import os
import re
import uuid
from pathlib import Path


def enable_dpi():
    if os.name != 'nt':
        return
    user = c.WinDLL('user32', use_last_error=True)
    try:
        call = user.SetProcessDpiAwarenessContext
        call.argtypes = [c.c_void_p]
        call.restype = c.c_bool
        call(c.c_void_p(-4))
        # Embedded Python may already have a process default; set the UI thread too.
        thread = user.SetThreadDpiAwarenessContext
        thread.argtypes = [c.c_void_p]
        thread.restype = c.c_void_p
        if thread(c.c_void_p(-4)):
            return
    except AttributeError:
        pass
    try:
        shcore = c.WinDLL('shcore')
        shcore.SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        user.SetProcessDPIAware()


@functools.cache
def downloads_path():
    if os.name != 'nt':
        return None
    shell = c.WinDLL('shell32')
    ole = c.WinDLL('ole32')
    guid = (c.c_ubyte * 16).from_buffer_copy(uuid.UUID('374de290-123f-4565-9164-39c4925e467b').bytes_le)
    out = c.c_void_p()
    call = shell.SHGetKnownFolderPath
    call.argtypes = [c.c_void_p, c.c_uint32, c.c_void_p, c.POINTER(c.c_void_p)]
    call.restype = c.c_int32
    hr = call(c.byref(guid), 0, None, c.byref(out))
    if hr < 0:
        raise OSError('Windows 다운로드 폴더 위치를 확인하지 못했어요.')
    try:
        return Path(c.wstring_at(out)).absolute()
    finally:
        ole.CoTaskMemFree.argtypes = [c.c_void_p]
        ole.CoTaskMemFree(out)


def display_name(path):
    try:
        if Path(path) == downloads_path():
            return '다운로드'
    except OSError:
        pass
    return Path(path).name or str(path)


DOWNLOADS_NAME = r'@%SystemRoot%\system32\shell32.dll,-21798'
DOWNLOADS_ICON = r'%SystemRoot%\system32\imageres.dll,-184'


def localized_ini(text):
    # Replace only the name/icon fields in ShellClassInfo; retain other settings.
    values = {
        'localizedresourcename': ('LocalizedResourceName', DOWNLOADS_NAME),
        'iconresource': ('IconResource', DOWNLOADS_ICON),
    }
    output = []
    inside = False
    found = False
    written = set()

    def missing():
        for key, (name, value) in values.items():
            if key not in written:
                output.append(name + '=' + value)
                written.add(key)

    for line in text.splitlines():
        if re.match(r'^\s*\[.*\]\s*$', line):
            if inside:
                missing()
            inside = line.strip().casefold() == '[.shellclassinfo]'
            found = found or inside
        key = line.partition('=')[0].strip().casefold()
        if inside and '=' in line and key in values:
            if key not in written:
                name, value = values[key]
                output.append(name + '=' + value)
                written.add(key)
        elif inside and '=' in line and key in ('iconfile', 'iconindex'):
            continue
        else:
            output.append(line)
    if inside:
        missing()
    if not found:
        output.extend(['', '[.ShellClassInfo]'])
        missing()
    return '\r\n'.join(output) + '\r\n'


def restore_downloads_label(backup_root):
    from engine import plain

    folder = downloads_path()
    if not folder or not folder.is_dir() or not all(plain(p) for p in (folder, *folder.parents)):
        raise ValueError('일반 로컬 다운로드 폴더에서만 표시 이름을 복구할 수 있어요.')
    file = folder / 'desktop.ini'
    original = None
    backup = None
    if os.path.lexists(file):
        if not plain(file) or not file.is_file():
            raise ValueError('표시 설정 파일의 경로를 확인해 주세요.')
        original = file.read_bytes()
        if len(original) > 1024 * 1024:
            raise ValueError('표시 설정 파일이 너무 커서 자동 수정하지 않았어요.')
        if original.startswith((b'\xff\xfe', b'\xfe\xff')):
            text = original.decode('utf-16')
        else:
            try:
                text = original.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = original.decode('mbcs')
        backup_root = Path(backup_root)
        backup_root.mkdir(exist_ok=True)
        backup = backup_root / ('desktop-' + uuid.uuid4().hex + '.ini.bak')
        backup.write_bytes(original)
    else:
        text = ''
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileAttributesW.argtypes = [c.c_wchar_p]
    kernel.GetFileAttributesW.restype = c.c_uint32
    kernel.SetFileAttributesW.argtypes = [c.c_wchar_p, c.c_uint32]
    kernel.SetFileAttributesW.restype = c.c_bool

    def attrs(p):
        value = kernel.GetFileAttributesW(str(p))
        if value == 0xFFFFFFFF:
            raise c.WinError(c.get_last_error())
        return value

    def setattrs(p, value):
        if not kernel.SetFileAttributesW(str(p), value):
            raise c.WinError(c.get_last_error())

    folder_attrs = attrs(folder)
    file_attrs = attrs(file) if original is not None else 0x20
    try:
        if original is not None:
            setattrs(file, file_attrs & ~1)
        file.write_text(localized_ini(text), encoding='utf-16', newline='')
        setattrs(file, file_attrs | 2 | 4)
        setattrs(folder, folder_attrs | 1)
        if (
            file.read_text(encoding='utf-16') != localized_ini(text).replace('\r\n', '\n')
            or not attrs(folder) & 1
            or attrs(file) & 6 != 6
        ):
            raise OSError('표시 설정을 저장한 뒤 확인하지 못했어요.')
    except Exception:
        if original is not None:
            try:
                setattrs(file, file_attrs & ~1)
                file.write_bytes(original)
                setattrs(file, file_attrs)
            except OSError:
                pass
        else:
            try:
                if file.exists():
                    setattrs(file, 0x20)
                    file.unlink()
            except OSError:
                pass
        try:
            setattrs(folder, folder_attrs)
        except OSError:
            pass
        raise
    shell = c.WinDLL('shell32')
    shell.SHChangeNotify.argtypes = [c.c_long, c.c_uint32, c.c_void_p, c.c_void_p]
    shell.SHChangeNotify(0x1000, 0x0005, c.cast(c.c_wchar_p(str(folder)), c.c_void_p), None)
    return dict(
        path=str(folder),
        backup=str(backup or ''),
        message='다운로드의 기본 표시 이름·아이콘과 폴더 속성을 복구했어요.\n\n복구한 폴더: '
        + str(folder)
        + '\n백업: '
        + str(backup or '기존 설정 파일이 없어 새로 만들었어요.')
        + '\n\n탐색기 창을 닫고 다시 여세요. 여전히 Downloads로 보이면 작업 관리자 → Windows 탐색기 → 다시 시작을 선택하거나 PC를 재부팅해 주세요. 실제 폴더 경로와 안의 파일은 바꾸지 않았어요.',
    )
