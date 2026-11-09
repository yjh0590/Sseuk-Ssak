import re
import unicodedata
from collections import defaultdict

DOCUMENTS = set(".ppt .pptx .hwp .hwpx .doc .docx .pdf .xls .xlsx .txt .zip".split())
VIDEO = set(".mp4 .mkv .mov .avi .webm .m4v".split())
AUDIO = set(".mp3 .m4a .wav .aac .flac .ogg".split())
TEXT = set(".txt .md .srt .vtt .docx .hwp .hwpx".split())
VERSION = re.compile(
    r"(?:[ _.\-]+(?:v\d+(?:\.\d+)*|ver\s*\d+(?:\.\d+)*|최종(?:본)?|진짜최종|수정(?:본)?|초안|제출(?:본)?|final|draft|copy|복사본)\s*\d*|\s*\(\d+\))$",
    re.I,
)
ROLE = re.compile(
    r"(?:[ _.\-]+(?:스크립트|대본|자막|음성|원본|영상|녹음|오디오|변환본?|transcript|audio|video|subtitles?))$", re.I
)


def normalized(s):
    return " ".join(unicodedata.normalize("NFC", s).casefold().split())


def version_base(stem):
    while True:
        base = VERSION.sub("", stem).strip()
        if base == stem:
            return base
        stem = base


def grouped(files):
    versions, conversions = defaultdict(list), defaultdict(list)
    for p in files:
        ext, stem = p.suffix.lower(), normalized(p.stem)
        if ext in DOCUMENTS:
            base = version_base(stem)
            if base:
                versions[p.parent, base, ext].append(p)
        role = "영상" if ext in VIDEO else "음성" if ext in AUDIO else "대본 후보" if ext in TEXT else None
        base = ROLE.sub("", stem).strip()
        if role and base:
            conversions[p.parent, base].append((p, role))
    for (parent, base, ext), paths in versions.items():
        if len(paths) < 2 or not any(normalized(p.stem) != base for p in paths):
            continue
        group = parent / (base + ext)
        latest = max(files[p][1] for p in paths)
        for p in paths:
            note = "최근 수정" if files[p][1] == latest else "이전 수정"
            yield "작업 버전", p, group, note
    for (parent, base), items in conversions.items():
        roles = {role for p, role in items}
        if len(roles) < 2:
            continue
        for p, role in items:
            note = "음성 · 중간 파일 후보" if role == "음성" and len(roles) == 3 else role
            yield "변환 파일", p, parent / base, note


def folder_index(root, dirs, files):
    children = {d: [] for d in dirs}
    direct = defaultdict(list)
    totals = {d: [0, 0] for d in dirs}
    for path, stamp in files.items():
        direct[path.parent].append((path, stamp[0]))
        totals[path.parent][0] += stamp[0]
        totals[path.parent][1] += 1
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        if d != root:
            children[d.parent].append(d)
            totals[d.parent][0] += totals[d][0]
            totals[d.parent][1] += totals[d][1]
    return children, direct, totals
