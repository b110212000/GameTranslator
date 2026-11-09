"""General desktop UI used for visible click-through/focus acceptance testing."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

root=tk.Tk()
root.title('GameTranslator 一般應用驗證')
root.state('zoomed')
report=Path(__file__).resolve().parents[1]/'work/desktop-probe.json'
clicks=0
value=tk.StringVar()
status=tk.StringVar(value='點擊 0 次')
def save():
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps({'clicks':clicks,'text':value.get(),'entry_focused':root.focus_get()==entry},ensure_ascii=False,indent=2),encoding='utf-8')
def clicked():
    global clicks
    clicks+=1;status.set(f'點擊 {clicks} 次');save()
ttk.Label(root,text='一般應用測試：字幕出現時仍可輸入與點擊',font=('Microsoft JhengHei UI',20)).pack(pady=35)
ttk.Label(root,text='先在此輸入文字，字幕更新後繼續輸入，檢查焦點是否保留。').pack(pady=8)
entry=ttk.Entry(root,textvariable=value,font=('Segoe UI',20),width=40)
entry.pack(pady=12)
entry.bind('<KeyRelease>',lambda e:save())
ttk.Label(root,textvariable=status,font=('Microsoft JhengHei UI',22)).pack(pady=20)
tk.Button(root,text='字幕下方按鈕：點擊應穿透到這裡',command=clicked,
          font=('Microsoft JhengHei UI',20),height=8,background='#dce8f5').pack(side='bottom',fill='x',padx=50,pady=(0,50))
entry.focus_set()
root.after(100,save)
root.mainloop()
