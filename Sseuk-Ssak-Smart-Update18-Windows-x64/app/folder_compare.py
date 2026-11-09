"""Conservative sibling-folder discovery and byte-content comparison."""
import hashlib
import re
import os
import secrets
from pathlib import Path
from download_versions import parse,word_tokens
import folder_ops
from engine import HOLD,APP,plain

class FolderCompare:
    def __init__(self):
        self.items={};self.comparisons={};self.root=None

    def scan(self, root):
        root=Path(root);self.root=root;self.items={};self.comparisons={};self.bulk={}
        groups={};errors=[]
        # Inspect immediate children only, so parent and child cannot both be selected.
        for p in sorted(root.iterdir(),key=lambda p:p.name.casefold()):
            if not p.is_dir():continue
            try:
                if not plain(p) or p==APP or APP.is_relative_to(p) or HOLD.casefold() in [v.casefold() for v in p.parts]:continue
                # Directory names may contain dots; append a dummy extension for parsing.
                key,version=parse(p.with_name(p.name+'.folder'))
                update=re.search(r'(?i)(?<![a-z0-9])update[ _-]?(\d+)(?![a-z0-9])',re.sub(r'\s*\(\d+\)$','',p.name))
                if update:
                    stem=re.sub(r'\s*\(\d+\)$','',p.name)
                    key=(stem[:update.start()]+'Update{version}'+stem[update.end():]).casefold()
                    version=(int(update[1]),0,0,0)
                token=secrets.token_hex(12)
                self.items[token]={'path':p,'version':version}
                groups.setdefault(key,[]).append({'id':token,'name':p.name,'path':str(p),'version':'.'.join(map(str,version)) if version else '버전 표기 없음'})
            except (ValueError,OSError) as e:errors.append({'path':str(p),'message':str(e)})
        visible=[{'name':key.replace('{version}','버전 비교'),'items':items} for key,items in groups.items() if len(items)>1]
        for group in visible:
            for entry in group['items']:
                try:
                    captured=folder_ops.capture(root,Path(entry['path']))
                    entry['size']=captured.size
                    entry['modified']=captured.path.stat().st_mtime
                    entry['measure_error']=''
                except (OSError,ValueError) as exc:
                    entry['size']=None;entry['modified']=None;entry['measure_error']=str(exc)
        return {'groups':visible,'errors':errors,'root':str(root)}

    def manifest(self,item):
        paths={};dirs=set()
        for rel,(isdir,stamp) in item.tree.items():
            if isdir:
                dirs.add(rel);continue
            path=item.path/rel
            h=hashlib.sha256()
            with path.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            paths[rel]=h.hexdigest()
        return paths,dirs

    def compare(self, source_id, reference_id):
        if source_id==reference_id:raise ValueError('비교할 폴더를 서로 다르게 선택해 주세요.')
        if source_id not in self.items or reference_id not in self.items:raise ValueError('폴더를 다시 찾아 주세요.')
        src=folder_ops.capture(self.root,self.items[source_id]['path']);ref=folder_ops.capture(self.root,self.items[reference_id]['path'])
        a,ad=self.manifest(src);b,bd=self.manifest(ref)
        folder_ops.validate(self.root,src);folder_ops.validate(self.root,ref)
        only_source=sorted(a.keys()-b.keys());only_reference=sorted(b.keys()-a.keys());different=sorted(k for k in a.keys()&b.keys() if a[k]!=b[k]);same=sum(a[k]==b[k] for k in a.keys()&b.keys())
        token=secrets.token_hex(16);self.comparisons[token]=(src,ref,only_source,different,ad-bd)
        return {'token':token,'source':str(src.path),'reference':str(ref.path),'only_source':only_source,'only_reference':only_reference,'different':different,'same':same,'only_source_dirs':sorted(ad-bd),'size':src.size,'subset':not only_source and not different and not(ad-bd)}

    def move(self,token,confirmed,allow_unique,recycle):
        if confirmed is not True:raise ValueError('휴지통 이동 확인이 필요합니다.')
        if token not in self.comparisons:raise ValueError('폴더 내용을 다시 비교해 주세요.')
        src,ref,only,different,dirs=self.comparisons[token]
        if (only or different or dirs) and allow_unique is not True:raise ValueError('이 폴더에만 있는 파일과 차이를 확인해 주세요.')
        folder_ops.validate(self.root,src);folder_ops.validate(self.root,ref)
        # Rehash as well: timestamps alone cannot establish unchanged content.
        a,ad=self.manifest(src);b,bd=self.manifest(ref)
        if sorted(a.keys()-b.keys())!=only or sorted(k for k in a.keys()&b.keys() if a[k]!=b[k])!=different or ad-bd!=dirs:raise ValueError('비교 결과가 달라졌습니다. 다시 비교해 주세요.')
        folder_ops.validate(self.root,src);folder_ops.validate(self.root,ref)
        recycle(src.path);self.comparisons.clear()
        return {'message':'선택한 폴더를 휴지통으로 이동했습니다. 기준 폴더는 유지했습니다.'}


    def prepare_bulk(self, ids):
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or any(k not in self.items for k in ids):
            raise ValueError('목록에서 정리할 폴더를 다시 선택해 주세요.')
        captured=[folder_ops.capture(self.root,self.items[k]['path']) for k in ids]
        token=secrets.token_hex(16)
        if not hasattr(self,'bulk'):self.bulk={}
        self.bulk={token:(self.root,captured)}
        return {'token':token,'paths':[str(x.path) for x in captured],'size':sum(x.size for x in captured)}

    def execute_bulk(self, token, confirmed, recycle):
        if confirmed is not True:raise ValueError('휴지통 이동 확인이 필요합니다.')
        root,items=getattr(self,'bulk',{}).pop(token,(None,None))
        if items is None or root!=self.root:raise ValueError('목록에서 폴더를 다시 선택해 주세요.')
        for item in items:folder_ops.validate(root,item)
        moved=[];failed=[]
        for item in items:
            try:
                folder_ops.validate(root,item);recycle(item.path);moved.append(str(item.path))
            except Exception as e:failed.append({'path':str(item.path),'message':str(e)})
        self.comparisons.clear()
        return {'moved':moved,'failed':failed}
