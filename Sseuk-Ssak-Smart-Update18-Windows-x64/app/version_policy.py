"""Choose one keeper per download-version group without deleting files."""

import re
from collections import defaultdict


def number(path):
    match = re.search(r'\((\d+)\)$', path.stem)
    return int(match[1]) if match else 0


def choose(rows, mode='date', overrides=None):
    if mode not in ('date', 'number', 'manual'):
        raise ValueError('남길 기준을 다시 선택해 주세요.')
    overrides = overrides or {}
    groups = defaultdict(list)
    for row in rows:
        if row.kind == '같은 이름':
            groups[row.group].append(row)
    replacements = {}
    for group, items in groups.items():
        keep = next((r for r in items if r.path == overrides.get(group)), None)
        reason = '직접 지정'
        if keep is None and mode != 'manual':
            score = (lambda r: r.stamp[1]) if mode == 'date' else (lambda r: number(r.path))
            highest = max(map(score, items))
            leaders = [r for r in items if score(r) == highest]
            if len(leaders) == 1:
                keep = leaders[0]
            reason = '수정 날짜 기준' if mode == 'date' else '괄호 숫자 기준'
        for row in items:
            if keep is None:
                detail = (
                    '남길 파일을 직접 지정해 주세요'
                    if mode == 'manual'
                    else '최고 기준값이 같아요 · 남길 파일을 직접 지정해 주세요'
                )
            elif row.path == keep.path:
                detail = '남길 파일 · ' + reason
            else:
                detail = '정리 대상 · 남길 파일 ' + keep.path.name
            replacements[row.path] = row._replace(
                keep=keep.path if keep and row.path != keep.path else None, detail=detail
            )
    return [replacements[r.path] if r.kind == '같은 이름' else r for r in rows]
