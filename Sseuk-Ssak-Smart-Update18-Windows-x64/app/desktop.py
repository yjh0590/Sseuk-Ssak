"""Serve the desktop renderer on a private, short-lived loopback address."""
from local_groups import organize_rows, choose_keepers as choose
import windows_ui, folder_ops, storage_view
from smart_service import SmartService
from folder_compare import FolderCompare
from analysis_views import folder_index
import ctypes
import json
import os
import secrets
from result_view import CleanupResult, describe
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE=Path(__file__).resolve().parent
def start():
    windows_ui.enable_dpi()
    os.environ['TCL_LIBRARY'] = str(BASE / 'python/tcl/tcl8.6')
    os.environ['TK_LIBRARY'] = str(BASE / 'python/tcl/tk8.6')
    import tkinter as tk
    from tkinter import filedialog
    import chrome_link, junk, desk
    from engine import held, relocate, scan, signature, validate_row
    from recycle import recycle, empty_recycle_bin
    from organizer import FILTERS
    try:
        chrome = chrome_link.find_chrome()
    except FileNotFoundError:
        raise RuntimeError('이 버전은 Google Chrome이 필요해요. Chrome 설치 후 다시 실행해 주세요.')
    smart = SmartService()
    folder_compare = FolderCompare()
    raw_rows=[];word_mode='off';word_keyword='';similar_names=False
    across=False; keeper_stamps={}; keeper_mode="date"; overrides={}; last_storage=None
    root=None; rows=[];stash=[];index=[]; junks=[]; logs=[]; refs={};token=secrets.token_urlsafe(32)
    def pack(p,n,reason,kind,obj,group=None):
        key=secrets.token_hex(10)
        refs[key]=(kind,obj)
        return dict(id=key,path=str(p),name=windows_ui.display_name(p),size=n,note=reason,kind=kind,group=str(group or ''))
    def collect(kind, report):
        nonlocal root,rows,stash,index,junks,logs,keeper_stamps,last_storage,raw_rows
        if kind=='junk':
            junks,logs=junk.collect(root,junk.user_temp())
        else:
            index=[];last_storage=None
            rows,_,logs=scan(root,progress=report,folder_data=index,across=across)
            raw_rows=list(rows)
            rows=organize_rows(raw_rows,word_mode,word_keyword,similar_names,keeper_mode,overrides)
            stash=held(root)
            keeper_stamps={r.path:r.stamp for r in rows if r.kind=='같은 이름'}
            overrides.clear()
            rows=choose(rows,keeper_mode,overrides)
    def snapshot(space=None):
        refs.clear()
        files=[pack(r.path,r.size,r.detail,r.kind,r,r.group) | {'compare':str(r.keep or ''),'date':time.strftime('%Y.%m.%d %H:%M:%S',time.localtime(r.stamp[1]/1e9)), 'protected':r.kind=='같은 이름' and not r.keep} for r in rows]
        temp=[pack(r.path,r.stamp[0],r.reason,'정크 파일',r) for r in junks]
        saved=[]
        for p,d in stash:
            try:saved.append(pack(d,p.stat().st_size,'원래 위치로 복원할 수 있어요.','보관함',(p,d)) | {'reveal':str(p)})
            except OSError:pass
        return dict(root=str(root or ''),files=files,junk=temp,stash=saved,logs=logs,temp=str(junk.user_temp() or ''),filters=['같은 이름','전체 파일']+[f for f in FILTERS if f!='같은 이름'],chrome_report=chrome_history(),keeper_mode=keeper_mode,word_mode=word_mode,word_keyword=word_keyword,similar_names=similar_names,root_name=windows_ui.display_name(root) if root else '',extensions=sorted({r.path.suffix.lower().lstrip('.') for r in rows if r.kind=='전체 파일' and r.path.suffix}),storage_current=space if space is not None else (storage_view.measure([root]) if root else []),storage_comparison=last_storage)
    def chrome_history():
        try:return json.loads((BASE/'chrome-last-result.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):return None
    def dispatch(a,v,progress=lambda event: None):
        nonlocal root,rows,stash,index,junks,across,keeper_mode,last_storage,word_mode,word_keyword,similar_names,keeper_stamps,raw_rows,logs
        if a=='smart_pick':
            win=tk.Tk();win.withdraw();win.attributes('-topmost',True)
            try:chosen=filedialog.askdirectory(parent=win,initialdir=smart.root or Path.home())
            finally:win.destroy()
            if not chosen:return {'cancel':True}
            return smart.select(chosen)
        if a=='smart':return smart.handle(v)
        if a=='refresh_space':
            last_storage=None
            return snapshot(storage_view.measure([root]) if root else [])
        if a=='reset':
            root=None;rows=[];raw_rows=[];stash=[];index=[];junks=[];logs=[]
            across=False;keeper_mode='date';keeper_stamps={};last_storage=None
            word_mode='off';word_keyword='';similar_names=False;overrides.clear();refs.clear()
            return snapshot()
        if a=='init':return snapshot()
        if a=='folder_find':
            if not root:raise ValueError('먼저 파일 정리에서 폴더를 선택하고 검사해 주세요.')
            return folder_compare.scan(root)
        if a=='folder_bulk_prepare':return folder_compare.prepare_bulk(v.get('ids'))
        if a=='folder_bulk_remove':
            result=folder_compare.execute_bulk(v.get('token'),v.get('confirmed'),recycle)
            collect('files',lambda _:None)
            result['state']=snapshot()
            return result
        if a=='folder_compare':return folder_compare.compare(v['source'],v['reference'])
        if a=='folder_remove':
            result=folder_compare.move(v['token'],v.get('confirmed'),v.get('allow_unique'),recycle)
            collect('files',lambda _:None)
            result['state']=snapshot()
            return result
        if a=='grouping':
            mode=v.get('word_mode','off');keyword=v.get('keyword','');similar=v.get('similar',False)
            if type(similar) is not bool:raise ValueError('비슷한 이름 설정을 확인해 주세요.')
            from download_versions import word_groups
            word_groups([],mode,keyword,similar) # validate before changing session
            grouped=organize_rows(raw_rows,mode,keyword,similar,keeper_mode,{})
            word_mode,word_keyword,similar_names=mode,keyword.strip(),similar
            rows=grouped;overrides.clear()
            keeper_stamps={r.path:r.stamp for r in rows if r.kind=='같은 이름'}
            return snapshot()
        if a=='keeper':
            if 'mode' in v:
                if v['mode'] not in ('date','number','manual','version'):raise ValueError('남길 기준을 다시 선택해 주세요.')
                keeper_mode=v['mode'];overrides.clear()
            elif v.get('id') in refs and refs[v['id']][0]=='같은 이름':
                row=refs[v['id']][1]
                if signature(row.path)!=keeper_stamps.get(row.path):raise ValueError('파일이 바뀌었어요. 다시 검사해 주세요.')
                overrides[row.group]=row.path
            else:raise ValueError('같은 이름 목록에서 남길 파일을 골라 주세요.')
            rows=choose(rows,keeper_mode,overrides)
            return snapshot()
        if a=='scan':
            across=bool(v.get('across',False))
            if v.get('pick') or (root is None and v['mode']!='junk'):
                win=tk.Tk();win.withdraw();win.attributes('-topmost',True)
                try:chosen=filedialog.askdirectory(parent=win,initialdir=root or Path.home())
                finally:win.destroy()
                if not chosen:return {'cancel':True}
                target=Path(chosen).absolute()
                if target!=root:
                    rows=[];junks=[];index=[];stash=[];refs.clear()
                root=target
            last_update = 0.0
            def report(message):
                nonlocal last_update
                now = time.monotonic()
                if now - last_update >= 0.25:
                    progress(message)
                    last_update = now
            report('임시 파일을 확인하고 있어요.' if v['mode']=='junk' else '폴더 안의 파일을 확인하고 있어요.')
            collect(v['mode'], report)
            progress('검사 결과를 정리하고 있어요.')
            return snapshot()
        if a=='recycle_info':return {'size':storage_view.recycle_size(None)}
        if a=='empty_recycle':
            if v.get('confirmed') is not True:raise ValueError('영구 삭제 확인이 필요해요.')
            error=None
            try:empty_recycle_bin(True)
            except OSError as e:error=str(e)
            last_storage=None
            return dict(state=snapshot(),remaining=storage_view.recycle_size(None),error=error)
        if a=='repair_downloads':return windows_ui.restore_downloads_label(BASE/'display-backup')
        if a=='rank':
            for k in list(refs):
                if refs[k][0]=='폴더 용량':del refs[k]
            if not index:return []
            ch,di,tot=index[0];p=Path(v['path']) if v.get('path') else root
            if p not in ch:raise ValueError('검사한 폴더를 선택해 주세요.')
            result=[]
            for target in ch[p]+[f for f,n in di[p]]:
                if not target.exists():continue
                try:
                    item=folder_ops.capture(root,target)
                    row=pack(target,item.size,'폴더 전체와 하위 파일을 함께 이동해요.' if item.folder else '선택한 파일만 이동해요.','폴더 용량',item)
                    row.update(folder=item.folder,modified=target.stat().st_mtime,date=time.strftime('%Y.%m.%d %H:%M:%S',time.localtime(target.stat().st_mtime)))
                except (OSError,ValueError) as e:
                    row=dict(id=secrets.token_hex(10),path=str(target),name=windows_ui.display_name(target),size=tot.get(target,[0])[0],folder=target.is_dir(),modified=0,date='확인 불가',protected=True,note=str(e))
                result.append(row)
            return result
        if a=='open_file':
            ref=refs.get(v.get('id'))
            if not ref or ref[0] in ('보관함','폴더 용량','정크 파일'):
                raise ValueError('파일 정리 목록에서 파일을 골라 주세요.')
            p=ref[1].path
            if not p.is_file():raise ValueError('파일이 없거나 열 수 없어요. 다시 검사해 주세요.')
            try:os.startfile(str(p))
            except OSError as e:raise ValueError('파일을 열지 못했어요. 연결 프로그램이나 파일 위치를 확인해 주세요.') from e
            return {}
        if a=='reveal':
            p=Path(v['path'])
            if not root or not p.is_relative_to(root):
                if not any(r.path==p for r in junks):raise ValueError('검사한 파일을 골라 주세요.')
            if not p.exists():raise ValueError('원래 위치에 파일이 없어요. 다시 검사해 주세요.')
            subprocess.Popen(['explorer.exe','/select,',str(p)]);return {}
        if a=='setup':
            chrome_link.pairing_key();chrome_link.launch('chrome://extensions/')
            return {'path':str(chrome_link.HELPER)}
        if a=='chrome':
            result=chrome_link.run_cleanup()
            try:(BASE/'chrome-last-result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            except OSError:result['save_warning']='결과 저장에 실패했어요. 이 창에서 확인해 주세요.'
            if root:
                collect('files',lambda _:None)
                result['state']=snapshot()
            return result
        if a!='apply':raise ValueError('작업을 찾지 못했어요.')
        ids=list(dict.fromkeys(v['ids']));op=v['op']
        if op not in ('trash','restore') or not ids or any(k not in refs for k in ids):raise ValueError('목록을 다시 확인해 주세요.')
        kinds={refs[k][0] for k in ids}
        if len(kinds)!=1 or ('보관함' in kinds)!=(op=='restore') or ('정크 파일' in kinds and op!='trash') or 'ZIP 확인' in kinds:raise ValueError('같은 종류의 파일을 선택해 주세요.')
        selected=[refs[k][1] for k in ids];paths={r.path for r in selected} if op!='restore' else set()
        keep={r.group:r.path for r in rows if r.group and r.kind in kinds and r.path not in paths and r.path.is_file()}
        ok=[];errors={}
        progress(dict(done=0,total=len(ids),success=0,failed=0,file="파일 상태 확인 중"))
        set_ids=set(ids)
        kept_paths=set()
        for key,(kind,item) in refs.items():
            if kind in kinds and key not in set_ids:
                kept_paths.add(item[0] if op=='restore' else item.path)
        kept_paths.update(r.keep for r in selected if getattr(r,'keep',None))
        report=CleanupResult(kept_paths)
        before_space=storage_view.measure([r[0] if op=='restore' else r.path for r in selected])
        moved_sizes={k:0 for k in [*storage_view.TYPES,'기타']}
        for step,(key,obj) in enumerate(zip(ids,selected),1):
            current=obj[0] if op=="restore" else obj.path
            progress(dict(done=step-1,total=len(ids),success=len(ok),failed=len(errors),file=current.name))
            entry=describe(current)
            try:
                if op=='restore':relocate(root,*obj)
                elif '폴더 용량' in kinds:
                    folder_ops.validate(root,obj);entry['size']=obj.size;recycle(obj.path)
                elif '정크 파일' in kinds:
                    if not junk.allowed(obj.root,obj.path) or signature(obj.path)!=obj.stamp or junk.reason(obj.path,obj.stamp,junk.user_temp())!=obj.reason:raise ValueError('검사 후 바뀐 파일이에요. 다시 검사해 주세요.')
                    recycle(obj.path)
                else:
                    if obj.kind=='같은 이름':
                        if not obj.keep or obj.keep in paths:raise ValueError('남길 파일을 지정한 뒤 다른 파일만 선택하세요.')
                        if signature(obj.keep)!=keeper_stamps.get(obj.keep):raise ValueError('남길 파일이 바뀌었어요. 다시 검사해 주세요.')
                    if obj.group and obj.kind!='같은 이름':
                        if obj.group not in keep:raise ValueError('이 묶음에서 남길 파일 하나를 선택 해제하세요.')
                        obj=obj._replace(keep=keep[obj.group])
                    validate_row(root,obj);recycle(obj.path)
                if op=="restore":entry["path"]=str(obj[1]);entry["name"]=obj[1].name
                if op=='trash':
                    if getattr(obj,'folder',False):
                        for relative,(isdir,stamp) in obj.tree.items():
                            if not isdir:moved_sizes[storage_view.category(relative)]+=stamp[0]
                    else:moved_sizes[storage_view.category(current)]+=entry.get('size') or 0
                report.moved.append(entry)
                ok.append(key)
            except Exception as e:
                errors[key]=str(e)
                report.failed.append(dict(entry,reason=str(e)))
            progress(dict(done=step,total=len(ids),success=len(ok),failed=len(errors),file=current.name))
        progress(dict(done=len(ids),total=len(ids),success=len(ok),failed=len(errors),file='결과와 디스크 용량을 확인하고 있어요.',phase='finalizing'))
        gone={refs[k][1].path for k in ok} if op!='restore' else set()
        def removed(path):return path in gone or any(parent in gone for parent in path.parents)
        raw_rows=[r for r in raw_rows if not removed(r.path)]
        rows=[r for r in rows if not removed(r.path)];junks=[r for r in junks if not removed(r.path)]
        rows=choose(rows,keeper_mode,overrides)
        if ok and index:
            old_dirs=index[0][0]
            dirs={d for d in old_dirs if not removed(d)}
            files={r.path:r.stamp for r in rows if r.kind=='전체 파일' and r.path.parent in dirs}
            index=[folder_index(root,dirs,files)] if root in dirs else []
        if root and op=='restore':
            try:stash=held(root)
            except OSError as e:logs.append(str(e))
        last_storage=storage_view.comparison(before_space,storage_view.measure([Path(v['volume']) for v in before_space]),moved_sizes)
        result=report.finish();result['storage']=last_storage
        return dict(ok=ok,errors=errors,state=snapshot(last_storage['after']),report=result)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def response(self,code,data,typ):
            self.send_response(code);self.send_header('Content-Type',typ);self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Length',str(len(data)));self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            name=self.path.removeprefix('/'+token+'/')
            assets={'':'index.html','style.css':'style.css','ui.js':'ui.js','storage.js':'storage.js','layout_scale.js':'layout_scale.js','folder_ui.js':'folder_ui.js','smart_ui.js':'smart_ui.js','icon.ico':'Sseuk-Ssak.ico','mark.png':'mark.png','font.ttf':'fonts/SseukSsakDance.ttf'}
            if self.headers.get('Host')!=host or not self.path.startswith('/'+token+'/') or name not in assets:return self.send_error(404)
            typ={'':'text/html; charset=utf-8','style.css':'text/css','ui.js':'text/javascript','storage.js':'text/javascript','layout_scale.js':'text/javascript','folder_ui.js':'text/javascript','smart_ui.js':'text/javascript','font.ttf':'font/ttf','mark.png':'image/png','icon.ico':'image/x-icon'}[name]
            self.response(200,(BASE/assets[name]).read_bytes(),typ)
        def do_POST(self):
            if self.headers.get('Origin')!=origin or self.headers.get('Host')!=host or not self.path.startswith('/'+token+'/api/'):return self.send_error(403)
            try:
                n=int(self.headers.get('Content-Length',0))
                if not 0<=n<=8000000:raise ValueError('요청이 너무 커요.')
                v=json.loads(self.rfile.read(n));action=self.path.rsplit('/',1)[1]
                if action in ("apply", "scan"):
                    self.send_response(200)
                    self.send_header("Content-Type","application/x-ndjson; charset=utf-8")
                    self.send_header("Cache-Control","no-store")
                    self.send_header("X-Frame-Options","DENY")
                    self.end_headers()
                    self.close_connection=True
                    def event(value):
                        try:
                            self.wfile.write((json.dumps(value)+"\n").encode())
                            self.wfile.flush()
                        except (BrokenPipeError,ConnectionResetError):
                            pass
                    try:
                        result=dispatch(action,v,lambda p:event({"progress":p}))
                        event({"result":result})
                    except Exception as e:event({"error":str(e)})
                    return
                result={} if action=='ping' else dispatch(action,v)
                self.response(200,json.dumps(result).encode(),'application/json')
            except Exception as e:self.response(400,json.dumps({'error':str(e)}).encode(),'application/json')
    with HTTPServer(('127.0.0.1',0),Handler) as server:
        host=f'127.0.0.1:{server.server_port}';origin='http://'+host;server.timeout=3
        subprocess.Popen([str(chrome),'--app='+origin+'/'+token+'/'])
        last=time.monotonic()
        import select
        while time.monotonic()-last<180:
            if select.select([server],[],[],3)[0]:
                server.handle_request();last=time.monotonic()
if __name__=='__main__':
    try:
        if sys.version_info<(3,9):raise RuntimeError('Python 3.9 이상이 필요해요.')
        start()
    except Exception as e:ctypes.windll.user32.MessageBoxW(None,str(e),'쓱-싹 실행 안내',16)
