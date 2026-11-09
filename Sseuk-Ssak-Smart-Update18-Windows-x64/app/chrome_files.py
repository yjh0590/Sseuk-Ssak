"""Files referenced by Chrome: explicit version groups and native recycle only."""
import re
import secrets
import time
from pathlib import Path
from collections import defaultdict
from engine import Row,signature,safe,APP,HOLD
from download_versions import choose_downloads as choose, group_key, parse, word_groups
from storage_view import measure,category

class Session:
    def __init__(self):
        self.rows=[];self.ids={};self.records={};self.stamps={};self.overrides={};self.mode='version';self.similar=False;self.word_mode='off';self.keyword='';self.skipped=[];self.moved=[];self.failed=[];self.record_failed=[];self.before=[];self.after=[];self.attempted=set();self.started=False
    def inspect(self,items):
        if self.started:raise ValueError('작업이 시작됐어요. 앱에서 다시 열어 주세요.')
        self.rows=[];self.ids={};self.records={};self.skipped=[];self.overrides={};groups=defaultdict(list)
        if not isinstance(items,list) or len(items)>100000:raise ValueError('다운로드 목록이 너무 커요.')
        for record in items:
            try:
                p=Path(record['path'])
                if not p.is_absolute() or '..' in p.parts or not p.is_file():raise ValueError('원래 위치에 파일이 없어요. 기록을 남겼어요.')
                if p.name.casefold()=='desktop.ini' or p.is_relative_to(APP) or HOLD.casefold() in [x.casefold() for x in p.parts] or not safe(Path(p.anchor),p):raise ValueError('보호된 파일 또는 연결 경로예요.')
                if type(record['id']) is not int:raise ValueError('올바르지 않은 기록이에요.')
                if p in self.records:self.records[p].append(record['id']);continue
                self.records[p]=[record['id']]
                sig=signature(p);self.stamps[p]=sig
                group=group_key(p,self.similar)
                row=Row('같은 이름',p,sig[0],sig,'',None,group);groups[group].append(row)
            except (OSError,ValueError,KeyError,TypeError) as e:
                self.skipped.append(dict(name=str(record.get('name','확인 불가')),path=str(record.get('path','')),reason=str(e),size=record.get('size'),date=record.get('date','')))
        for group in groups.values():self.rows.extend(group)
        self.rows=word_groups(self.rows,self.word_mode,self.keyword,self.similar)
        self.rows=choose(self.rows,self.mode,self.overrides)
        self.ids={secrets.token_hex(12):r.path for r in self.rows}
        return self.snapshot()
    def policy(self,value):
        if self.started:raise ValueError('작업 중에는 기준을 바꿀 수 없어요.')
        if 'word_mode' in value or 'keyword' in value:
            mode=value.get('word_mode',self.word_mode)
            keyword=value.get('keyword',self.keyword)
            rows=word_groups(self.rows,mode,keyword,self.similar)
            self.word_mode,self.keyword=mode,keyword.strip()
            self.overrides.clear();self.rows=choose(rows,self.mode,self.overrides)
            return self.snapshot()
        if 'similar' in value:
            if type(value['similar']) is not bool:raise ValueError('비슷한 이름 보기 설정이 올바르지 않아요.')
            self.similar=value['similar'];self.overrides.clear()
            self.rows=word_groups(self.rows,self.word_mode,self.keyword,self.similar)
            self.rows=choose(self.rows,self.mode,self.overrides)
            return self.snapshot()
        if 'mode' in value:
            if value['mode'] not in ('version','date','number'):raise ValueError('남길 기준을 선택해 주세요.')
            self.mode=value['mode'];self.overrides.clear()
        else:
            p=self.ids.get(value.get('id'));r=next((r for r in self.rows if r.path==p),None)
            if not r:raise ValueError('목록을 다시 확인해 주세요.')
            self.overrides[r.group]=p
        self.rows=choose(self.rows,self.mode,self.overrides);return self.snapshot()
    def snapshot(self):
        inverse={p:k for k,p in self.ids.items()}
        return dict(mode=self.mode,similar=self.similar,word_mode=self.word_mode,keyword=self.keyword,items=[dict(id=inverse[r.path],name=r.path.name,path=str(r.path),size=r.size,modified=r.stamp[1],date=time.strftime('%Y.%m.%d %H:%M:%S',time.localtime(r.stamp[1]/1e9)),group=r.group,note=r.detail.replace('남길 파일을 직접 지정하세요','정리할 파일을 직접 선택하세요').replace('남길 파일을 직접 지정해 주세요','정리할 파일을 직접 선택하세요'),protected=not bool(r.keep)) for r in self.rows],skipped=self.skipped)
    def start(self,ids):
        if self.started:raise ValueError('이미 시작한 작업이에요.')
        ids=list(dict.fromkeys(ids))
        if not ids or any(k not in self.ids for k in ids):raise ValueError('정리할 파일을 선택하세요.')
        selected={self.ids[k] for k in ids}
        self.selected_paths=selected
        self.allowed=set(ids);self.before=measure(selected);self.started=True
        return dict(total=len(ids))
    def move(self,key,send):
        if not self.started or key not in self.allowed or key in self.attempted:raise ValueError('허용되지 않거나 이미 처리한 파일이에요.')
        self.attempted.add(key);p=self.ids[key];r=next(r for r in self.rows if r.path==p)
        entry=dict(id=key,name=p.name,path=str(p),size=r.size,date=time.strftime('%Y.%m.%d %H:%M:%S',time.localtime(r.stamp[1]/1e9)))
        try:
            if not safe(Path(p.anchor),p) or signature(p)!=r.stamp:raise ValueError('파일이 바뀌었어요. 다시 확인해 주세요.')
            if r.keep and r.keep not in self.selected_paths:
                if not safe(Path(r.keep.anchor),r.keep) or signature(r.keep)!=self.stamps[r.keep]:raise ValueError('남길 파일이 바뀌었어요. 다시 확인해 주세요.')
            send(p);self.moved.append(entry)
            return dict(ok=True,recordIds=self.records[p],entry=entry)
        except Exception as e:
            self.failed.append(dict(entry,reason=str(e)));return dict(ok=False,error=str(e),recordIds=[])
    def finish(self,record_failed=None):
        self.record_failed=record_failed or []
        paths=[r.path for r in self.rows]
        self.after=measure([Path(v['volume']) for v in self.before])
        gone={e['path'] for e in self.moved};failed={e['path'] for e in self.failed}
        remaining=[dict(name=r.path.name,path=str(r.path),size=r.size,date='',reason='남김') for r in self.rows if str(r.path) not in gone|failed]+self.skipped
        moved={k:0 for k in ['문서','사진','영상','음악','압축파일','기타']}
        for entry in self.moved:moved[category(entry['path'])]+=entry['size']
        return dict(deleted=self.moved,failed=self.failed,remaining=remaining,record_failed=self.record_failed,storage=dict(before=self.before,after=self.after,moved=moved),file_cleanup=True)
