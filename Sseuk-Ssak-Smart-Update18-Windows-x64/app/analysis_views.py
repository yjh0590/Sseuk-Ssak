import re
import unicodedata
from collections import defaultdict
from pathlib import Path

DOCUMENTS = set(".ppt .pptx .hwp .hwpx .doc .docx .pdf .xls .xlsx .txt .zip".split())
VIDEO = set(".mp4 .mkv .mov .avi .webm .m4v".split())
AUDIO = set(".mp3 .m4a .wav .aac .flac .ogg".split())
TEXT = set(".txt .md .srt .vtt .docx .hwp .hwpx".split())
VERSION = re.compile(r"(?:[ _.\-]+(?:v\d+(?:\.\d+)*|ver\s*\d+(?:\.\d+)*|최종(?:본)?|진짜최종|수정(?:본)?|초안|제출(?:본)?|final|draft|copy|복사본)\s*\d*|\s*\(\d+\))$",re.I)
ROLE = re.compile(r"(?:[ _.\-]+(?:스크립트|대본|자막|음성|원본|영상|녹음|오디오|변환본?|transcript|audio|video|subtitles?))$",re.I)

def normalized(s):
    return " ".join(unicodedata.normalize("NFC",s).casefold().split())

def version_base(stem):
    while True:
        base = VERSION.sub("",stem).strip()
        if base == stem:
            return base
        stem = base

def grouped(files):
    versions, conversions = defaultdict(list), defaultdict(list)
    for p in files:
        ext,stem = p.suffix.lower(),normalized(p.stem)
        if ext in DOCUMENTS:
            base = version_base(stem)
            if base:
                versions[p.parent,base,ext].append(p)
        role = "영상" if ext in VIDEO else "음성" if ext in AUDIO else "대본 후보" if ext in TEXT else None
        base = ROLE.sub("",stem).strip()
        if role and base:
            conversions[p.parent,base].append((p,role))
    for (parent,base,ext), paths in versions.items():
        if len(paths)<2 or not any(normalized(p.stem)!=base for p in paths):
            continue
        group = parent/(base+ext)
        latest = max(files[p][1] for p in paths)
        for p in paths:
            note = "최근 수정" if files[p][1]==latest else "이전 수정"
            yield "작업 버전",p,group,note
    for (parent,base),items in conversions.items():
        roles = {role for p,role in items}
        if len(roles)<2:
            continue
        for p,role in items:
            note = "음성 · 중간 파일 후보" if role=="음성" and len(roles)==3 else role
            yield "변환 파일",p,parent/base,note

def folder_index(root, dirs, files):
    children = {d:[] for d in dirs}
    direct = defaultdict(list)
    totals = {d:[0,0] for d in dirs}
    for path,stamp in files.items():
        direct[path.parent].append((path,stamp[0]))
        totals[path.parent][0] += stamp[0]
        totals[path.parent][1] += 1
    for d in sorted(dirs,key=lambda p:len(p.parts),reverse=True):
        if d != root:
            children[d.parent].append(d)
            totals[d.parent][0] += totals[d][0]
            totals[d.parent][1] += totals[d][1]
    return children,direct,totals

def folder_window(parent,root,index,fmt):
    import tkinter as tk
    from tkinter import ttk
    import subprocess
    children,direct,totals = index
    current = root
    locations = {}
    win = tk.Toplevel(parent)
    import visual as ui
    win.title("쓱-싹 · 폴더별 용량 순위")
    win.geometry("880x520")
    win.configure(bg=ui.BG,padx=14,pady=10)
    pane = ui.card(win,grow=True)
    ui.label(pane,"폴더별 용량 순위",16,bold=True).pack(anchor="w")
    heading = tk.StringVar()
    ttk.Label(pane,textvariable=heading,wraplength=810).pack(anchor="w",pady=5)
    actions = ttk.Frame(pane)
    actions.pack(fill="x",pady=5)
    up = ttk.Button(actions,text="상위 폴더",command=lambda:render(current.parent))
    up.pack(side="left")
    ttk.Button(actions,text="탐색기로 열기",command=lambda:subprocess.Popen(["explorer.exe",str(current)])).pack(side="left",padx=4)
    ttk.Label(actions,text="폴더를 더블클릭하면 그 안의 용량 순위를 볼 수 있어요.").pack(side="left",padx=5)
    table = ttk.Treeview(pane,columns=("name","type","size","count"),show="headings",selectmode="browse")
    for col,title,width in zip(table["columns"],("이름","종류","용량","파일 수"),(400,75,95,90)):
        table.heading(col,text=title)
        table.column(col,width=width)
    scroll=ttk.Scrollbar(pane,command=table.yview)
    scroll.pack(side="right",fill="y")
    table.configure(yscrollcommand=scroll.set)
    table.pack(fill="both",expand=True)
    def render(path):
        nonlocal current
        current=path
        locations.clear()
        table.delete(*table.get_children())
        up.state(["disabled"] if current==root else ["!disabled"])
        heading.set(f"{path}  ·  {fmt(totals[path][0])}  ·  검사한 파일 {totals[path][1]:,}개")
        rows=[(d,"폴더",*totals[d]) for d in children[path]]
        rows.extend((p,"파일",size,1) for p,size in direct[path])
        for p,kind,size,count in sorted(rows,key=lambda r:(r[1]!="폴더",-r[2],r[0].name.casefold())):
            row=table.insert("","end",values=(p.name,kind,fmt(size),f"{count:,}"))
            if kind=="폴더": locations[row]=p
    def drill(event):
        row=table.identify_row(event.y)
        if row in locations: render(locations[row])
    table.bind("<Double-1>",drill)
    render(root)
