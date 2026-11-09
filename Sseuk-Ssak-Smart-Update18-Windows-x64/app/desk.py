import ctypes
import math
import time
import tkinter as tk
from tkinter import font
from visual import rounded

BG, WHITE, INK, SUB, RED, PINK, LINE = "#F6F7F9","#FFFFFF","#191F28","#59636E","#C93645","#FCECEF","#E7EAED"
FONT="맑은 고딕"
def load_typeface():
    """Expose the bundled static instance to this Windows process only."""
    import os
    if os.name != "nt":
        return
    import atexit
    from pathlib import Path
    path = str(Path(__file__).with_name("fonts") / "SseukSsakDance.ttf")
    gdi = ctypes.windll.gdi32
    for fn in (gdi.AddFontResourceExW, gdi.RemoveFontResourceExW):
        fn.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p)
    if gdi.AddFontResourceExW(path, 0x10, None):
        global FONT
        FONT = "Sseuk Ssak Dance"
        atexit.register(gdi.RemoveFontResourceExW, path, 0x10, None)

def card(master, *, padding=(24,18), width=None, **pack):
    shell = tk.Frame(master, bg=BG, bd=0)
    shell.pack(**pack)
    surface = tk.Canvas(shell, bg=BG, bd=0, highlightthickness=0)
    surface.place(x=0, y=0, relwidth=1, relheight=1)
    def draw(e):
        surface.delete("all")
        rounded(surface,0,0,e.width,e.height,24,"#EAECEF")
        rounded(surface,1,1,e.width-2,e.height-2,23,WHITE)
    surface.bind("<Configure>",draw)
    inside = tk.Frame(shell,bg=WHITE,bd=0)
    inside.pack(fill="both",expand=True,padx=padding[0],pady=padding[1])
    if width:
        shell.configure(width=width)
        shell.pack_propagate(False)
    return inside

def nav_item(parent,text,action):
    b=tk.Canvas(parent,bg=WHITE,height=46,width=1,bd=0,highlightthickness=0,
                cursor="hand2",takefocus=1)
    def paint(active):
        b.active=active
        b.delete("all")
        if active or b.focus_get()==b:
            rounded(b,0,1,b.winfo_width(),44,18,PINK if active else BG)
        b.create_text(15,23,text=text,anchor="w",fill=RED if active else SUB,font=face(16,active))
    b.active=False
    b.bind("<Configure>",lambda e:paint(b.active))
    for event in ("<Button-1>","<Return>","<space>"):
        b.bind(event,lambda e:action())
    for event in ("<FocusIn>","<FocusOut>"):
        b.bind(event,lambda e:paint(b.active))
    b.pack(fill="x",pady=2)
    return paint

def face(px,bold=False): return (FONT,-px,"bold" if bold else "normal")
def label(parent,text,px=16,color=INK,bold=False,bg=WHITE,**kw):
    return tk.Label(parent,text=text,font=face(px,bold),fg=color,bg=bg,bd=0,anchor="w",justify="left",**kw)
def button(parent,text,cmd,primary=False):
    f=font.Font(font=face(16,True)); w=f.measure(text)+36
    bg=parent.cget("bg")
    b=tk.Canvas(parent,width=w,height=48,bg=bg,highlightthickness=0,takefocus=1,cursor="hand2")
    def paint(hover=False):
        b.delete("all")
        rounded(b,0,0,w,48,16,("#B0303D" if hover else RED) if primary else ("#E8EBEE" if hover else "#F0F2F4"))
        b.create_text(w/2,24,text=text,fill=WHITE if primary else INK,font=face(16,True))
        if b.focus_get()==b:b.create_line(14,42,w-14,42,fill=WHITE if primary else SUB)
    paint()
    b.bind("<Enter>",lambda _:paint(True));b.bind("<Leave>",lambda _:paint())
    b.bind("<FocusIn>",lambda _:paint());b.bind("<FocusOut>",lambda _:paint())
    for ev in ("<Button-1>","<Return>","<space>"):b.bind(ev,lambda _:cmd())
    return b
def reduced():
    enabled=ctypes.c_int(1)
    try: return bool(ctypes.windll.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(enabled),0)) and not enabled.value
    except AttributeError: return False

class FileList(tk.Canvas):
    height_row=94
    def __init__(self,parent,click,open_at):
        super().__init__(parent,bg=WHITE,bd=0,highlightthickness=0,takefocus=1)
        self.rows=[];self.selected=set();self.errors={};self.offsets={};self.locked=False
        self.click=click;self.open_at=open_at;self.cursor_row=0
        self.fonts={n:font.Font(font=face(n,n==16)) for n in (14,16)}
        self.bind("<Configure>",lambda e:self.paint())
        self.bind("<MouseWheel>",lambda e:self.scroll("scroll",-int(e.delta/120),"units"))
        self.bind("<Button-1>",self.pick)
        self.bind("<Double-1>",lambda e:self.activate(int(self.canvasy(e.y)//self.height_row)))
        self.bind("<space>",lambda _:self.toggle(self.cursor_row))
        self.bind("<Return>",lambda _:self.activate(self.cursor_row))
        for key,d in (("Up",-1),("Down",1)):self.bind("<"+key+">",lambda e,d=d:self.step(d))
    def activate(self,i):
        if not self.locked and 0<=i<len(self.rows):self.open_at(self.rows[i])
    def scroll(self,*args):
        if not self.locked:self.yview(*args);self.paint()
    def step(self,d):
        if self.locked or not self.rows:return
        self.cursor_row=max(0,min(len(self.rows)-1,self.cursor_row+d))
        self.yview_moveto(self.cursor_row/len(self.rows));self.paint()
    def toggle(self,i):
        if self.locked or not 0<=i<len(self.rows):return
        r=self.rows[i]
        if not r.get("selectable",True):return
        key=r["key"];self.selected.symmetric_difference_update({key});self.click()
    def pick(self,e):
        if self.locked:return
        self.focus_set();self.cursor_row=int(self.canvasy(e.y)//self.height_row);self.toggle(self.cursor_row)
    def fit(self,s,width,n):
        f=self.fonts[n]
        if f.measure(s)<=width:return s
        lo,hi=0,len(s)
        while lo<hi:
            mid=(lo+hi+1)//2
            if f.measure(s[:mid]+"…")<=width:lo=mid
            else:hi=mid-1
        return s[:lo]+"…"
    def paint(self):
        self.delete("all");w=self.winfo_width();h=self.height_row
        self.configure(scrollregion=(0,0,w,len(self.rows)*h),yscrollincrement=26)
        first=max(0,int(self.canvasy(0)//h))
        last=min(len(self.rows),math.ceil(self.canvasy(self.winfo_height())/h)+1)
        for i in sorted(range(first,last),key=lambda j:self.rows[j]["key"] in self.offsets):
            r=self.rows[i];k=r["key"];x,dy=self.offsets.get(k,(0,0));y=i*h+dy
            selected=k in self.selected
            rounded(self,x+1,y+3,max(1,w-2),h-6,14,PINK if selected else WHITE)
            self.create_line(x+12,y+h-1,x+w-12,y+h-1,fill=LINE)
            if r.get("selectable",True):
                rounded(self,x+8,y+22,20,20,5,RED if selected else "#D5DADF")
                if selected:self.create_line(x+12,y+32,x+17,y+36,x+24,y+27,fill=WHITE,width=2)
            a=x+42
            self.create_text(a,y+10,text=self.fit(r["name"],max(40,w-180),16),font=face(16,True),anchor="nw",fill=INK)
            self.create_text(a,y+34,text=self.fit(r["path"],max(40,w-145),14),font=face(14),anchor="nw",fill=SUB)
            self.create_text(a,y+58,text=self.fit(self.errors.get(k,r["note"]),max(40,w-70),14),font=face(14),anchor="nw",fill=RED if k in self.errors else SUB)
            self.create_text(x+w-16,y+12,text=r["size"],font=face(16,True),anchor="ne",fill=INK)
    def animate(self,keys,success,phase,done,skip):
        if skip():self.offsets.clear();self.paint();done();return
        h=self.height_row
        top=self.canvasy(0);bottom=top+self.winfo_height()
        visible=[(i,r["key"]) for i,r in enumerate(self.rows) if r["key"] in keys and i*h<bottom and (i+1)*h>top]
        start=dict(self.offsets);target=max(top,bottom-h*.65)
        ts=time.monotonic()
        def frame():
            t=min(1,(time.monotonic()-ts)/(.38 if phase=="gather" else .33))
            if skip():t=1
            for j,(i,k) in enumerate(visible):
                if phase=="gather":
                    self.offsets[k]=(0,max(0,target-i*h-j*2)*(1-(1-t)**3))
                else:
                    _,y=start.get(k,(0,0))
                    self.offsets[k]=((self.winfo_width()+20)*t*t,y) if k in success else (0,y*(1-t))
            self.paint()
            if t<1:self.after(16,frame)
            else:done()
        frame()

def confirm(parent,action,question,description):
    dialog=tk.Toplevel(parent);dialog.title(action);dialog.transient(parent)
    dialog.configure(bg=WHITE,padx=32,pady=32);dialog.resizable(False,False)
    approved=False
    label(dialog,question,24,bold=True,wraplength=500).pack(anchor="w")
    label(dialog,description,16,SUB,wraplength=480).pack(anchor="w",pady=(8,32))
    bar=tk.Frame(dialog,bg=WHITE);bar.pack(anchor="w")
    def accept():
        nonlocal approved
        approved=True;dialog.destroy()
    cancel=button(bar,"취소",dialog.destroy);cancel.pack(side="left",padx=(0,8))
    button(bar,action,accept,True).pack(side="left")
    dialog.bind("<Escape>",lambda e:dialog.destroy())
    dialog.update_idletasks()
    dialog.geometry("+%d+%d"%(parent.winfo_rootx()+max(0,(parent.winfo_width()-dialog.winfo_reqwidth())//2),
                              parent.winfo_rooty()+max(0,(parent.winfo_height()-dialog.winfo_reqheight())//2)))
    dialog.grab_set();cancel.focus_set();parent.wait_window(dialog)
    return approved
