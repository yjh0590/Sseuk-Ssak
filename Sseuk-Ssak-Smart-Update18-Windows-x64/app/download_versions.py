"""Conservative explicit v-prefixed release comparison for Chrome downloads."""
import re
from pathlib import Path
from collections import defaultdict
from version_policy import choose

VERSION=re.compile(r'(?i)(?<![a-z0-9])v(\d+(?:\.\d+){1,3})(?![a-z0-9.]|\.\d)')
def parse(path):
    path=Path(path)
    stem=re.sub(r'\s*\(\d+\)$','',path.stem)
    matches=list(VERSION.finditer(stem))
    if len(matches)!=1:return stem.casefold(),None
    m=matches[0];version=tuple(map(int,m[1].split('.')))
    return (stem[:m.start()]+'{version}'+stem[m.end():]).casefold(),version+(0,)*(4-len(version))

def group_key(path, similar=True):
    name,_=parse(path) if similar else (re.sub(r'\s*\(\d+\)$','',path.stem).casefold(),None)
    return str(path.parent/(name+path.suffix.casefold()))

def choose_downloads(rows,mode,overrides):
    if mode!='version':return choose(rows,mode,overrides)
    groups=defaultdict(list)
    for row in rows:groups[row.group].append(row)
    result=[]
    for group,items in groups.items():
        versions=[parse(r.path)[1] for r in items]
        if not all(v is not None for v in versions):
            result.extend(choose(items,'date',overrides));continue
        keeper=next((r for r in items if r.path==overrides.get(group)),None)
        reason='직접 지정'
        if keeper is None:
            highest=max(versions);leaders=[r for r,v in zip(items,versions) if v==highest]
            reason='파일명 버전 기준'
            if len(leaders)>1:
                newest=max(r.stamp[1] for r in leaders)
                leaders=[r for r in leaders if r.stamp[1]==newest]
                reason='파일명 버전 → 같은 버전은 수정 날짜 기준'
            keeper=leaders[0] if len(leaders)==1 else None
        for row in items:
            note=('최고 버전 복사본이 여러 개예요 · 남길 파일을 직접 지정하세요' if keeper is None else
                  '남길 파일 · '+reason if row.path==keeper.path else '이전 버전·복사본 · 남길 파일 '+keeper.path.name)
            result.append(row._replace(keep=keeper.path if keeper and keeper.path!=row.path else None,detail=note))
    return result


# Shared words are discovery hints, not evidence of identical file contents.
STOP_WORDS = {'windows','win','mac','macos','linux','portable','setup','installer','install','download','downloads','release','final','최종','다운로드','설치','설치파일','파일','복사본'}
def word_tokens(path):
    stem = VERSION.sub(' ', re.sub(r'\s*\(\d+\)$', '', path.stem)).casefold()
    words = set(re.findall(r'[^\W_]+', stem, re.UNICODE))
    return sorted(w for w in words if len(w)>=2 and not w.isdecimal() and not re.fullmatch(r'(?:v?\d+|x(?:32|64|86)|arm64)',w) and w not in STOP_WORDS)[:24]

def word_groups(rows, mode='off', keyword='', similar=False):
    if mode not in {'off','auto','manual'}:
        raise ValueError('공통 단어 묶기 방식을 선택해 주세요.')
    if not isinstance(keyword,str) or len(keyword)>100:
        raise ValueError('묶을 문구는 100자 이하로 입력해 주세요.')
    keyword=keyword.strip().casefold()
    if mode=='manual' and not keyword:
        raise ValueError('직접 묶기에 사용할 단어나 문구를 입력해 주세요.')
    rows=[r._replace(group=group_key(r.path,similar)) for r in rows]
    if mode=='off':return rows
    # Separate unrelated locations, formats and CPU/platform targets.
    buckets=defaultdict(list)
    for i,r in enumerate(rows):
        tags=tuple(sorted(set(re.findall(r'(?i)(?<![a-z0-9])(windows|linux|macos|mac|x64|x86|arm64|32bit|64bit)(?![a-z0-9])',r.path.stem.casefold()))))
        buckets[(str(r.path.parent).casefold(),r.path.suffix.casefold(),tags)].append(i)
    from itertools import combinations
    for bucket,indices in sorted(buckets.items()):
        if mode=='manual':
            matches=[i for i in indices if keyword in rows[i].path.stem.casefold()]
            for i in matches:
                rows[i]=rows[i]._replace(group=str(rows[i].path.parent/('공통문구_'+keyword+rows[i].path.suffix.casefold()))+' | '+','.join(bucket[2]))
        else:
            pairs=defaultdict(set)
            for i in indices:
                for pair in combinations(word_tokens(rows[i].path),2):pairs[pair].add(i)
            assigned=set()
            # Deterministic groups share the SAME two words, avoiding A-B-C chains.
            for pair,members in sorted(pairs.items(),key=lambda x:(-len(x[1]),x[0])):
                available=members-assigned
                if len(available)<2:continue
                for i in available:
                    rows[i]=rows[i]._replace(group=str(rows[i].path.parent/('공통단어_'+'_'.join(pair)+rows[i].path.suffix.casefold()))+' | '+','.join(bucket[2]))
                assigned.update(available)
    return rows
