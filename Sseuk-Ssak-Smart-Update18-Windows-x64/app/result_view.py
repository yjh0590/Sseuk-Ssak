"""Describe the files involved in one completed cleanup."""
import os
import stat
import time
from pathlib import Path


def describe(path):
    row = dict(name=path.name, path=str(path), date='—', size=None,
               kind=(path.suffix[1:].upper() + ' 파일') if path.suffix else '파일')
    try:
        info = path.stat()
        row['date'] = time.strftime('%Y-%m-%d %H:%M', time.localtime(info.st_mtime))
        if stat.S_ISDIR(info.st_mode):
            row['kind'] = '폴더'
        else:
            row['size'] = info.st_size
    except (OSError, ValueError, OverflowError):
        pass
    return row


class CleanupResult:
    def __init__(self, kept):
        self.kept = set(kept)
        self.moved = []
        self.failed = []

    def finish(self):
        remaining = [describe(p) for p in sorted(self.kept) if os.path.exists(p)]
        return dict(remaining=remaining, moved=self.moved, failed=self.failed)
