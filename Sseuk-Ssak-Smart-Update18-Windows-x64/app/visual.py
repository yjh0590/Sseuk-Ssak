import time
import tkinter as tk
from tkinter import ttk

BG = "#F5F5F7"
INK = "#22232B"
MUTED = "#60616C"
RED = "#BD3043"
BLUSH = "#FFEEF0"
WHITE = "#FFFFFF"
FONT = "맑은 고딕"

def configure(win):
    win.configure(bg=BG)
    style = ttk.Style(win)
    style.theme_use("clam")
    style.configure(".",font=(FONT,10),background=WHITE,foreground=INK)
    style.configure("TButton",padding=(11,6),relief="flat",borderwidth=0,background="#F2F2F5",foreground=INK)
    style.map("TButton",background=[("disabled","#F3F3F5"),("active","#E6E6EB")],foreground=[("disabled","#8B8D98")])
    style.configure("Primary.TButton",background=RED,foreground=WHITE,font=(FONT,10,"bold"))
    style.map("Primary.TButton",background=[("disabled","#EEEDEF"),("pressed","#932239"),("active","#A6273B")],foreground=[("disabled","#83838C"),("!disabled",WHITE)])
    style.configure("Treeview",background=WHITE,fieldbackground=WHITE,borderwidth=0,rowheight=32)
    style.map("Treeview",background=[("selected","#FFE1E5")],foreground=[("selected","#872438")])
    style.configure("Treeview.Heading",background="#F7F7F9",foreground=MUTED,relief="flat",padding=(5,6))
    style.configure("TNotebook",background=WHITE,borderwidth=0)
    style.configure("TNotebook.Tab",background=WHITE,padding=(7,6),borderwidth=0)
    style.map("TNotebook.Tab",background=[("selected",BLUSH)],foreground=[("selected",RED)])
    style.configure("TScrollbar",arrowsize=11,troughcolor=WHITE,background="#D4D4DA",borderwidth=0)

def rounded(c,x,y,w,h,r,color):
    r=min(r,w/2,h/2)
    pts=(x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y)
    return c.create_polygon(pts,fill=color,outline="",smooth=True,splinesteps=16)

def card(master, *, grow=False, pad=16):
    canvas=tk.Canvas(master,bg=BG,highlightthickness=0,height=1,width=1)
    canvas.pack(fill="both" if grow else "x",expand=grow,pady=(0,9))
    content=ttk.Frame(canvas)
    window=canvas.create_window(pad,10,window=content,anchor="nw")
    def redraw(event):
        canvas.delete("surface")
        shape=rounded(canvas,0,0,event.width,event.height,17,WHITE)
        canvas.addtag_withtag("surface",shape)
        canvas.tag_lower(shape)
        options={"width":max(1,event.width-2*pad)}
        if grow: options["height"]=max(1,event.height-20)
        canvas.itemconfigure(window,**options)
    canvas.bind("<Configure>",redraw)
    if not grow:
        def measure(event):
            required=content.winfo_reqheight()+20
            if int(canvas.cget("height"))!=required:canvas.configure(height=required)
        content.bind("<Configure>",measure)
    return content

def label(master,text,pt=10,color=INK,bold=False,bg=WHITE):
    return tk.Label(master,text=text,font=(FONT,pt,"bold" if bold else "normal"),fg=color,bg=bg,anchor="w",bd=0)

def motion_state(t,i):
    """Gather down to a stack, pause, then sweep the stack to the right."""
    gather=min(1,max(0,(t-i*.045)/.46))
    gather=1-(1-gather)**3
    slide=min(1,max(0,(t-.65)/.35))**2
    x=(-33+i*30)*(1-gather)+3*i*gather+390*slide
    y=(12+i*24)*(1-gather)+(91+i*3)*gather
    return x,y

def sweep(parent,names,count,verb):
    if not count or not parent.winfo_exists(): return
    c=tk.Canvas(parent,bg=WHITE,highlightthickness=1,highlightbackground="#EAC8CD",height=176,width=345)
    c.place(relx=.5,rely=.5,anchor="center")
    c.bind("<Button-1>",lambda e:c.destroy())
    start=time.monotonic()
    def draw():
        t=min(1,(time.monotonic()-start)/.95)
        c.delete("all")
        c.create_text(15,12,anchor="nw",text="쓱" if t<.65 else "싹",fill=RED,font=(FONT,14,"bold"))
        for i,name in enumerate(names[:3]):
            dx,y=motion_state(t,i)
            x=91+dx
            rounded(c,x,y,174,24,7,("#F4D2D8","#F8DDE2",BLUSH)[i])
            c.create_text(x+10,y+12,anchor="w",text=name if len(name)<20 else name[:17]+"…",fill="#7C2938",font=(FONT,9))
        c.create_text(173,151,text=f"{count:,}개 {verb}",fill=INK,font=(FONT,11,"bold"))
        if t<1:c.after(16,draw)
        else:c.after(210,c.destroy)
    draw()
