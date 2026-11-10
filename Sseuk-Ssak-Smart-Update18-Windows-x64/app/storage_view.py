"""Measured volume space and separate logical file-type totals."""

import ctypes as c
import os
import shutil
from pathlib import Path

TYPES = {
    '문서': '.pdf .hwp .hwpx .doc .docx .xls .xlsx .ppt .pptx .txt .md .csv',
    '사진': '.jpg .jpeg .png .gif .webp .heic .bmp .svg',
    '영상': '.mp4 .mov .mkv .avi .webm',
    '음악': '.mp3 .wav .m4a .flac .aac',
    '압축파일': '.zip .7z .rar .tar .gz',
}


def category(path):
    return next((k for k, v in TYPES.items() if Path(path).suffix.lower() in v.split()), '기타')


def recycle_size(volume):
    if os.name != 'nt':
        return None

    class Info(c.Structure):
        if c.sizeof(c.c_void_p) == 4:
            _pack_ = 1
        _fields_ = [('cbSize', c.c_uint32), ('i64Size', c.c_int64), ('i64NumItems', c.c_int64)]

    info = Info()
    info.cbSize = c.sizeof(info)
    call = c.WinDLL('shell32').SHQueryRecycleBinW
    call.argtypes = [c.c_wchar_p, c.POINTER(Info)]
    call.restype = c.c_int32
    return max(0, info.i64Size) if call(volume, c.byref(info)) >= 0 else None


def measure(paths):
    volumes = {}
    for path in paths:
        p = Path(path)
        volume = p.anchor
        if not volume or volume in volumes:
            continue
        try:
            disk = shutil.disk_usage(volume)
            volumes[volume] = dict(
                volume=volume, total=disk.total, used=disk.used, free=disk.free, recycle=recycle_size(volume)
            )
        except OSError:
            volumes[volume] = dict(volume=volume, error='드라이브 용량을 측정하지 못했어요.')
    return list(volumes.values())


def comparison(before, after, moved):
    return dict(before=before, after=after, moved=moved)
