"""Capture explicit folder selections and refuse changes since preview."""
import os
from dataclasses import dataclass
from pathlib import Path
from engine import APP,HOLD,plain,safe,signature

@dataclass(frozen=True)
class FolderItem:
    path: Path
    size: int
    stamp: tuple
    tree: dict
    folder: bool


def _check_location(root,path):
    if not safe(root,path) or path.is_relative_to(APP) or APP.is_relative_to(path) or HOLD.casefold() in [v.casefold() for v in path.parts]:
        raise ValueError('앱·보관함·연결 경로는 이 화면에서 정리하지 않아요.')


def capture(root,path):
    """Walk the disk now and record every entry below path."""
    _check_location(root,path)
    tree={}
    if path.is_dir():
        def error(e):raise e
        for base,dirs,files in os.walk(path,onerror=error,followlinks=False):
            base=Path(base)
            for p in [base,*[base/n for n in dirs+files]]:
                if not plain(p) or HOLD.casefold() in [v.casefold() for v in p.parts] or p==APP:
                    raise ValueError('연결 경로 또는 보관함을 포함해 자동 정리할 수 없어요.')
                tree[str(p.relative_to(path))]=(p.is_dir(),signature(p))
        size=sum(stamp[0] for isdir,stamp in tree.values() if not isdir)
    else:
        if path.name.casefold()=='desktop.ini':raise ValueError('Windows 폴더 표시 설정 파일은 보호해요.')
        size=path.stat().st_size
    return FolderItem(path,size,signature(path),tree,path.is_dir())


def from_scan(root,path,files,dirs):
    """Build a preview from scan data instead of re-walking the subtree.

    files: {path: signature} of scanned files below path; dirs: scanned folders below path.
    validate() later compares this outline with the disk once, right before moving.
    """
    _check_location(root,path)
    tree={'.':(True,None)}
    for d in dirs:tree[str(d.relative_to(path))]=(True,None)
    for f,stamp in files.items():tree[str(f.relative_to(path))]=(False,stamp)
    size=sum(stamp[0] for isdir,stamp in tree.values() if not isdir)
    return FolderItem(path,size,None,tree,True)


def _outline(item):
    # Folder timestamps change with their contents, which the file entries already cover.
    # desktop.ini is skipped by the scanner, so it is left out on both sides.
    return {rel:(isdir,None if isdir else stamp) for rel,(isdir,stamp) in item.tree.items()
            if Path(rel).name.casefold()!='desktop.ini'}


def validate(root,item):
    current=capture(root,item.path)
    same=(current.path==item.path and current.folder==item.folder and _outline(current)==_outline(item)
          and (item.folder or current.stamp==item.stamp))
    if not same:raise ValueError('목록을 연 뒤 파일 또는 폴더 내용이 바뀌었어요. 다시 검사해 주세요.')
