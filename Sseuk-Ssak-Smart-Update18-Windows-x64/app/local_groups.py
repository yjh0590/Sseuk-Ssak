"""Pure grouping for ordinary scanned files. Does not move or write files."""

from collections import Counter
from download_versions import word_groups, choose_downloads


def organize_rows(scanned, word_mode='off', keyword='', similar=False, keeper_mode='date', overrides=None):
    originals = [r for r in scanned if r.path.is_file()]
    if word_mode == 'off' and not similar:
        return choose_keepers(originals, keeper_mode, overrides or {})
    unique = {r.path: r for r in originals if r.kind == '전체 파일'}
    grouped = word_groups(
        [r._replace(kind='같은 이름', keep=None) for r in unique.values()], word_mode, keyword, similar
    )
    counts = Counter(r.group for r in grouped)
    grouped = [r for r in grouped if counts[r.group] > 1]
    # Other classifications remain unchanged; replace same-name classification only.
    return choose_keepers([r for r in originals if r.kind != '같은 이름'] + grouped, keeper_mode, overrides or {})


def choose_keepers(rows, mode='date', overrides=None):
    same = [r for r in rows if r.kind == '같은 이름']
    updated = {r.path: r for r in choose_downloads(same, mode, overrides or {})}
    return [updated.get(r.path, r) if r.kind == '같은 이름' else r for r in rows]
