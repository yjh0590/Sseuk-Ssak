import os
import queue
from result_view import CleanupResult, describe
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
import chrome_link
import junk
import desk as ui
from engine import HOLD, held, relocate, scan, stage, newbatch, validate_row, signature
from recycle import recycle

FILTERS=("복사본","풀어둔 ZIP","같은 이름","작업 버전","변환 파일","큰 파일","ZIP 확인")
MENU=("파일 정리","정크 파일","폴더 용량","보관함","크롬 기록")
TITLES=("어떤 파일을 정리할까요?","오래된 임시 파일을 살펴보세요.","어느 폴더가 가장 클까요?","어떤 파일을 되돌릴까요?","다운로드 기록을 지울까요?")
def size(n):
    for u in ("B","KB","MB","GB","TB"):
        if n<1024 or u=="TB":return f"{n:,.0f} {u}" if u=="B" else f"{n:,.1f} {u}"
        n/=1024

class App:
    def __init__(self,win):
        self.win=win;win.title("쓱-싹 · 파일 정리");win.geometry("1140x760");win.minsize(840,610)
        win.configure(bg=ui.BG)
        self.icon=tk.PhotoImage(file=str(Path(__file__).with_name("mark.png")))
        if os.name=="nt":
            win.iconbitmap(default=str(Path(__file__).with_name("Sseuk-Ssak.ico")))
        else:
            win.iconphoto(True,self.icon)
        self.page=0;self.root=None;self.rank_path=None;self.index=[];self.files=[];self.junks=[];self.stash=[]
        self.checked_junk=False;self.filtered=tk.StringVar(value=FILTERS[0]);self.note=tk.StringVar()
        self.logs=[];self.busy=False;self.events=queue.Queue();self.errors={};self.selected=set()
        self.manual=tk.BooleanVar(value=ui.reduced())
        self.nav=ui.card(win,width=174,padding=(12,24),side="left",fill="y",padx=(12,0),pady=12)
        brand=tk.Frame(self.nav,bg=ui.WHITE)
        brand.pack(anchor="w",padx=4,pady=(0,32))
        tk.Label(brand,image=self.icon,bg=ui.WHITE,bd=0).pack(side="left",padx=(0,8))
        ui.label(brand,"쓱-싹",28,ui.RED,True).pack(side="left")
        self.navlabels=[]
        for i,n in enumerate(MENU):
            self.navlabels.append(ui.nav_item(self.nav,n,lambda i=i:self.switch(i)))
        tk.Checkbutton(self.nav,text="모션 줄이기",variable=self.manual,bg=ui.WHITE,fg=ui.SUB,activebackground=ui.WHITE,font=ui.face(14),bd=0).pack(side="bottom",anchor="w")
        self.panel=tk.Frame(win,bg=ui.BG,bd=0)
        self.panel.pack(fill="both",expand=True,padx=12,pady=12)
        heading=ui.card(self.panel,fill="x",pady=(0,12))
        self.title=ui.label(heading,"",28,bold=True);self.title.pack(fill="x")
        self.subtitle=ui.label(heading,"",16,ui.SUB,wraplength=690);self.subtitle.pack(fill="x",pady=(8,0))
        result=ui.card(self.panel,fill="both",expand=True,pady=(0,12))
        self.controls=tk.Frame(result,bg=ui.WHITE);self.controls.pack(fill="x")
        self.body=tk.Frame(result,bg=ui.WHITE);self.body.pack(fill="both",expand=True,pady=(12,0))
        self.foot=ui.card(self.panel,fill="x",padding=(24,14))
        self.draw();win.after(50,self.poll);win.protocol("WM_DELETE_WINDOW",self.close)
    def close(self):
        if self.busy:messagebox.showinfo("작업 중","현재 작업이 끝나면 창을 닫을 수 있어요.")
        else:self.win.destroy()
    def switch(self,p):
        if self.busy:return
        self.page=p;self.selected.clear();self.note.set("");self.draw()
    def work(self,fn,callback):
        self.busy=True
        def run():
            try:self.events.put((callback,fn(),None))
            except Exception as e:self.events.put((callback,None,str(e)))
        threading.Thread(target=run,daemon=True).start()
    def poll(self):
        try:
            while True:
                cb,out,err=self.events.get_nowait()
                if err:
                    self.busy=False;self.note.set(err+" · 다시 시도해 주세요.");self.draw()
                else:cb(out)
        except queue.Empty:pass
        self.win.after(50,self.poll)
    def clear(self,frame):
        for c in frame.winfo_children():c.destroy()
    def add(self,parent,text,fn,primary=False):
        b=ui.button(parent,text,lambda:None if self.busy else fn(),primary);b.pack(side="left",padx=(0,8));return b
    def model(self):
        def row(obj,p,n,note,selectable=True,name=None,path=None):
            return dict(key=str(p),obj=obj,name=name or p.name,path=str(path or p),size=size(n),amount=n,note=note,selectable=selectable)
        if self.page==0:
            group=[r for r in self.files if r.kind==self.filtered.get()]
            group.sort(key=lambda r:(str(r.group or ""),-r.size,str(r.path)))
            return [row(r,r.path,r.size,(f"{r.group.name}  ·  " if r.group else "")+r.detail+"  ·  "+datetime.fromtimestamp(r.stamp[1]/1e9).strftime("%Y-%m-%d"),r.kind!="ZIP 확인") for r in group]
        if self.page==1:return [row(r,r.path,r.stamp[0],r.reason) for r in self.junks]
        if self.page==3:
            result=[]
            for p,d in self.stash:
                try:result.append(row((p,d),p,p.stat().st_size,"복원할 위치",path=d))
                except OSError:pass
            return result
        if self.page==2 and self.index:
            children,direct,totals=self.index[0];p=self.rank_path
            rows=[row(d,d,totals[d][0],f"파일 {totals[d][1]:,}개 · 더블클릭해 폴더 열기",False) for d in children[p]]
            rows.extend(row(f,f,n,"파일 · 더블클릭해 위치 열기",False) for f,n in direct[p])
            return sorted(rows,key=lambda r:-r["amount"])
        return []
    def draw(self):
        for i,paint in enumerate(self.navlabels):paint(i==self.page)
        for f in (self.controls,self.body,self.foot):self.clear(f)
        self.title.configure(text=TITLES[self.page])
        desc=("파일명과 경로를 비교한 뒤 정리할 항목을 고르세요.","수정한 지 7일이 지난 임시 파일과 캐시를 찾아요.","하위 폴더의 파일 크기를 합산해 큰 순서대로 보여줘요.","선택한 파일을 보관하기 전 위치로 되돌려요.","원래 위치에 파일이 없는 다운로드 완료 기록을 찾아요.")
        self.subtitle.configure(text=desc[self.page])
        if self.page==4:
            ui.label(self.controls,"정리 범위",16,bold=True).pack(anchor="w")
            ui.label(self.body,"크롬 다운로드 목록",20,bold=True).pack(anchor="w")
            ui.label(self.body,"기록만 지워요. 컴퓨터에 저장된 파일은 그대로 남아요.\n다른 폴더로 옮긴 파일의 기록도 포함될 수 있어요.",16,ui.SUB,wraplength=660).pack(anchor="w",pady=(8,32))
            self.add(self.body,"연결 도우미 등록",self.setup)
        else:
            path=self.rank_path if self.page==2 else self.root
            self.scope=ui.label(self.controls,str(path or ("사용자 Temp" if self.page==1 else "폴더를 선택해 주세요.")),14,ui.SUB,wraplength=600)
            self.scope.pack(anchor="w")
            bar=tk.Frame(self.controls,bg=ui.WHITE);bar.pack(fill="x",pady=(8,0))
            if self.page==0:
                cb=ttk.Combobox(bar,state="readonly",values=FILTERS,textvariable=self.filtered,width=12,font=ui.face(16));cb.pack(side="left",padx=(0,12))
                if self.busy:cb.configure(state="disabled")
                cb.bind("<<ComboboxSelected>>",lambda e:self.switch(0))
            if self.root or self.page==1:self.add(bar,"폴더 바꾸기" if self.root else "폴더 고르기",self.pick)
            if self.page==2 and self.rank_path and self.rank_path!=self.root:self.add(bar,"상위 폴더 열기",lambda:self.folder(self.rank_path.parent))
            if self.logs:self.add(bar,"검사 기록 보기",lambda:messagebox.showinfo("검사 기록","\n".join(self.logs[:35])))
            items=self.model()
            self.list=ui.FileList(self.body,self.changed,self.open_row)
            self.list.rows=items;self.list.selected=self.selected;self.list.errors=self.errors;self.list.locked=self.busy
            sc=ttk.Scrollbar(self.body,command=self.list.scroll);self.list.configure(yscrollcommand=sc.set)
            sc.pack(side="right",fill="y");self.list.pack(fill="both",expand=True)
            if not items:
                ui.label(self.list,"아직 찾은 파일이 없어요." if not self.root and not self.checked_junk else "표시할 항목이 없어요.",16,ui.SUB).place(x=10,y=18)
        self.footer()
    def footer(self):
        self.clear(self.foot)
        if self.page==4:
            n=0
        else:n=len(self.selected)
        info=self.note.get() or ("선택한 파일 "+str(n)+"개 · "+size(sum(r["amount"] for r in self.list.rows if r["key"] in self.selected)) if n else "")
        ui.label(self.foot,info,14,ui.SUB,wraplength=710).pack(anchor="w")
        bar=tk.Frame(self.foot,bg=ui.WHITE);bar.pack(fill="x",pady=(8,0))
        if self.page==4:self.add(bar,"기록 지우기",self.chrome,True)
        elif n:
            self.add(bar,"원래 위치로 복원" if self.page==3 else "휴지통으로 이동",self.main_action,True)
            if self.page==0:self.add(bar,"보관함으로 이동",lambda:self.main_action(True))
            if any(k in self.errors for k in self.selected):self.add(bar,"실패 이유 보기",lambda:messagebox.showinfo("남은 파일","\n\n".join(k+"\n"+self.errors[k] for k in self.selected if k in self.errors)))
            if n==1 and not any(k in self.errors for k in self.selected):self.add(bar,"파일 위치 열기",lambda:self.open_row(next(r for r in self.list.rows if r["key"] in self.selected)))
        else:
            self.add(bar,"정크 파일 찾기" if self.page==1 else "파일 다시 찾기" if self.root else "파일 찾기",self.search,True)
        if self.page==0 and n==1:
            row=next((r["obj"] for r in self.list.rows if r["key"] in self.selected),None)
            if row and row.keep:self.add(bar,"비교 위치 열기",lambda:self.open_row({"key":str(row.keep)}))
        if self.page in (0,1,3) and self.list.rows:self.add(bar,"선택 해제" if n else "전체 선택",self.select_all)
    def changed(self):
        self.note.set("");self.list.paint();self.footer()
    def select_all(self):
        if self.selected:self.selected.clear()
        else:self.selected.update(r["key"] for r in self.list.rows if r["selectable"])
        self.changed()
    def folder(self,p):
        self.rank_path=p;self.draw()
    def open_row(self,r):
        p=Path(r["key"])
        if self.busy:return
        if self.page==2 and self.index and p in self.index[0][0]:self.folder(p)
        elif p.exists():subprocess.Popen(["explorer.exe","/select,",str(p)])
        else:self.note.set("파일 경로가 바뀌었어요. 다시 찾아 주세요.");self.footer()
    def pick(self):
        path=filedialog.askdirectory(parent=self.win,initialdir=self.root or Path.home())
        if path:
            self.root=Path(path).absolute();self.rank_path=self.root
            self.files=[];self.index=[];self.stash=[];self.junks=[];self.checked_junk=False
            self.search()
    def search(self):
        if self.page!=1 and not self.root:return self.pick()
        self.selected.clear();self.note.set("파일을 찾고 있어요…");self.busy=True;self.draw()
        def go():
            if self.page==1:return junk.collect(self.root,junk.user_temp())
            idx=[];rows,_,logs=scan(self.root,folder_data=idx)
            return rows,held(self.root),idx,logs
        def done(out):
            if self.page==1:self.junks,self.logs=out;self.checked_junk=True
            else:self.files,self.stash,self.index,self.logs=out;self.rank_path=self.root
            self.errors.clear();self.busy=False;self.note.set(f"검사 완료 · 현재 목록 {len(self.model()):,}개");self.draw()
        self.work(go,done)
    def setup(self):
        try:
            chrome_link.pairing_key();self.win.clipboard_clear();self.win.clipboard_append(str(chrome_link.HELPER))
            chrome_link.launch("chrome://extensions/")
            self.note.set("개발자 모드 → 압축해제된 확장 프로그램 로드 → 복사된 도우미 폴더 경로를 붙여 넣으세요.")
        except Exception as e:self.note.set(str(e))
        self.footer()
    def chrome(self):
        if not ui.confirm(self.win,"기록 지우기","다운로드 기록을 지울까요?","원래 위치에 없는 파일의 완료 기록만 지워요. 컴퓨터에 저장된 실제 파일은 그대로 남아요."):return
        self.note.set("크롬에서 기록을 확인하고 있어요.");self.footer()
        def done(n):
            self.busy=False;self.note.set(f"다운로드 기록 {n:,}개를 지웠어요.");self.footer()
        self.work(chrome_link.run_cleanup,done)
    def main_action(self,archive=False):
        chosen=[r for r in self.list.rows if r["key"] in self.selected]
        if not chosen:return
        restore=self.page==3
        action="복원" if restore else "보관함으로 이동" if archive else "휴지통으로 이동"
        chosen_keys=set(self.selected)
        keep={r["obj"].group:r["obj"].path for r in self.list.rows if self.page==0 and r["key"] not in chosen_keys and r["obj"].path.is_file()}
        if self.page==0 and any(r["obj"].group and r["obj"].group not in keep for r in chosen):
            self.note.set("각 묶음에서 남길 파일 하나를 선택 해제해 주세요.");self.footer();return
        descriptions = {"휴지통으로 이동":"이동한 파일은 Windows 휴지통에서 복원할 수 있어요.", "보관함으로 이동":"파일을 같은 드라이브의 보관함으로 옮겨요.", "복원":"파일이 있던 원래 폴더로 되돌려요."}
        if not ui.confirm(self.win,action,f"선택한 파일 {len(chosen):,}개를 {action}할까요?",f"{size(sum(r['amount'] for r in chosen))} · {descriptions[action]}"):return
        moving=not restore and not archive
        self.busy=True;self.list.locked=True
        for box in self.controls.winfo_children():
            for child in box.winfo_children():
                if isinstance(child,ttk.Combobox):child.configure(state="disabled")
        self.note.set("파일 상태를 다시 확인하고 있어요.");self.footer()
        def go():
            ok=set();errors={};batch=newbatch()
            kept=set()
            for row in self.list.rows:
                item=row["obj"]
                if row["key"] not in chosen_keys:
                    kept.add(item[0] if restore else item.path)
                elif getattr(item,"keep",None):
                    kept.add(item.keep)
            report=CleanupResult(kept)
            for r in chosen:
                k,obj=r["key"],r["obj"]
                entry=describe(obj[0] if restore else obj.path)
                try:
                    if restore:relocate(self.root,*obj)
                    elif self.page==1:
                        if not junk.allowed(obj.root,obj.path) or signature(obj.path)!=obj.stamp or junk.reason(obj.path,obj.stamp,junk.user_temp())!=obj.reason:
                            raise ValueError("검사 후 변경됐어요. 파일을 다시 찾아 주세요.")
                        recycle(obj.path)
                    else:
                        if obj.group:obj=obj._replace(keep=keep[obj.group])
                        if archive:stage(self.root,obj,batch)
                        else:validate_row(self.root,obj);recycle(obj.path)
                    if restore:entry.update(path=str(obj[1]),name=obj[1].name)
                    report.moved.append(entry)
                    ok.add(k)
                except Exception as e:
                    report.failed.append(dict(entry,reason=str(e)))
                    errors[k]=str(e)+" · 파일 위치를 확인한 뒤 다시 시도하세요."
            return ok,errors,report.finish()
        def result(out):
            ok,errors,report=out
            self.errors.update(errors)
            def finish():
                self.selected.clear();self.selected.update(errors)
                self.files=[r for r in self.files if str(r.path) not in ok]
                self.junks=[r for r in self.junks if str(r.path) not in ok]
                if ok:self.index=[];self.rank_path=self.root
                if self.root:
                    try:self.stash=held(self.root)
                    except OSError as e:self.logs.append(str(e))
                self.busy=False
                self.note.set(f"{action} {len(ok):,}개 · 실패 {len(errors):,}개"+(" · 남은 행에서 이유를 확인하세요." if errors else ""))
                self.draw()
                window=tk.Toplevel(self.win)
                window.title("정리 결과")
                tabs=ttk.Notebook(window)
                tabs.pack(fill="both",expand=True)
                for key,label in (("remaining","남은 항목"),("moved",action),("failed","실패")):
                    frame=ttk.Frame(tabs)
                    tabs.add(frame,text=f"{label} {len(report[key])}개")
                    table=ttk.Treeview(frame,columns=("name","date","kind","size","path","reason"),show="headings")
                    scroll=ttk.Scrollbar(frame,command=table.yview)
                    table.configure(yscrollcommand=scroll.set)
                    scroll.pack(side="right",fill="y")
                    table.pack(fill="both",expand=True)
                    for col,title,width in zip(table["columns"],("이름","수정한 날짜","유형","크기","경로","실패 이유"),(170,135,80,80,360,160)):
                        table.heading(col,text=title)
                        table.column(col,width=width)
                    sizes={}
                    for row in report[key]:
                        item=table.insert("","end",values=(row["name"],row["date"],row["kind"],size(row["size"]) if row["size"] is not None else "—",row["path"],row.get("reason","")))
                        sizes[item]=row["size"]
                    def sort_size(view,values,descending):
                        order=sorted(values,key=lambda i:(values[i] is None,(-1 if descending else 1)*(values[i] or 0)))
                        for position,item in enumerate(order):
                            view.move(item,"",position)
                        view.heading("size",text="크기 ▼" if descending else "크기 ▲",
                                     command=lambda:sort_size(view,values,not descending))
                    sort_size(table,sizes,True)
            if moving:self.list.animate(chosen_keys,ok,"sweep",finish,self.reduce)
            else:finish()
        def begin():self.work(go,result)
        if moving:self.list.animate(chosen_keys,set(),"gather",begin,self.reduce)
        else:begin()
    def reduce(self):return self.manual.get() or ui.reduced()

if __name__=="__main__":
    if os.name=="nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Oddz.SseukSsak")
    ui.load_typeface()
    win=tk.Tk()
    win.option_add("*TCombobox*Listbox.font",ui.face(16))
    App(win);win.mainloop()
