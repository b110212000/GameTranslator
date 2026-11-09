"""Tk model management dialog; workers communicate through a bounded queue."""
from queue import Empty, Full, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk, filedialog
from model_catalog import MODELS, DownloadCancelled, download_model, inventory, local_model_path, legacy_model_path
from model_storage import model_directory, writable_directory, import_model
from help_viewer import open_help

PROFILES = {
    '通用：中英混合＋日文（約 800 MB）': (('base.en','small','en-zh','ja-en'), 'small'),
    '純英文：較快、較省空間（約 220 MB）': (('base.en','en-zh'), 'base.en'),
    '多語高準確：建議 NVIDIA GPU（約 2.4 GB）': (('base.en','small','turbo','en-zh','ja-en'), 'turbo'),
}

SPEECH_LABELS = {'auto':'自動選擇（建議）','tiny.en':'英文快速 tiny.en',
                 'base.en':'英文標準 base.en','small':'多語輕量 small','turbo':'多語高準確 turbo'}
TRANSLATION_LABELS = {'auto':'自動（Argos，較快）','direct':'NLLB 直譯實驗版（非商用）','argos':'Argos 低耗能轉譯'}
DEVICE_LABELS = {'auto':'自動（優先使用 GPU）','cpu':'CPU（減少 GPU 使用）'}


class ModelManager:
    def __init__(self, root, settings, on_save, is_busy=lambda: False, first_run=False):
        self.window = tk.Toplevel(root)
        self.window.title('GameTranslator｜首次設定' if first_run else '模型與下載位置')
        self.window.resizable(False,False)
        self.on_save = on_save
        self.is_busy = is_busy
        self.events, self.cancel = Queue(maxsize=8), Event()
        self.running = False
        self.closed = False
        body = ttk.Frame(self.window,padding=18)
        body.pack(fill='both',expand=True)
        ttk.Label(body,text='設定你的 GameTranslator' if first_run else '模型與下載位置',font=('Microsoft JhengHei UI',16,'bold')).pack(anchor='w')
        ttk.Label(body,text='① 選存放位置 → ② 下載模型 → ③ 設定音訊；下載完成後可離線翻譯。').pack(anchor='w',pady=(4,8))
        folder_row = ttk.Frame(body); folder_row.pack(fill='x', pady=(0,4))
        self.folder = tk.StringVar(value=str(model_directory()))
        ttk.Entry(folder_row, textvariable=self.folder, width=53).pack(side='left',fill='x',expand=True)
        ttk.Button(folder_row,text='瀏覽…',command=self.browse_directory).pack(side='left',padx=4)
        ttk.Button(folder_row,text='套用位置',command=self.apply_directory).pack(side='left')
        ttk.Label(body,text='更換位置後，請匯入已有模型或重新下載；原資料夾的檔案會保留。',foreground='#555555').pack(anchor='w')
        profile_row=ttk.Frame(body);profile_row.pack(fill='x',pady=8)
        try: selected_profile=min(2,max(0,int(settings.get('setup_profile',0))))
        except (TypeError,ValueError): selected_profile=0
        self.profile=tk.StringVar(value=list(PROFILES)[selected_profile])
        ttk.Combobox(profile_row,textvariable=self.profile,values=list(PROFILES),state='readonly',width=48).pack(side='left')
        self.recommended_button=ttk.Button(profile_row,text='下載建議模型',command=self.download_recommended)
        self.recommended_button.pack(side='right')
        self.tree = ttk.Treeview(body,columns=('purpose','size','state'),show='tree headings',height=7)
        self.tree.heading('#0',text='模型');self.tree.column('#0',width=205)
        for key,label,width in [('purpose','用途',145),('size','下載大小',100),('state','狀態',100)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=width)
        self.tree.pack(fill='x')
        self.description = tk.StringVar(value='選擇模型可查看授權及安裝狀態。')
        ttk.Label(body,textvariable=self.description,wraplength=540).pack(anchor='w',pady=7)
        self.tree.bind('<<TreeviewSelect>>',self.describe)
        controls = ttk.Frame(body);controls.pack(fill='x')
        self.download_button = ttk.Button(controls,text='下載／補齊選取模型',command=self.start_download)
        self.download_button.pack(side='left')
        self.cancel_button = ttk.Button(controls,text='取消下載',command=self.cancel_download,state='disabled')
        self.cancel_button.pack(side='left',padx=8)
        self.import_button=ttk.Button(controls,text='匯入選取模型…',command=self.start_import)
        self.import_button.pack(side='left')
        self.progress = tk.DoubleVar()
        ttk.Progressbar(body,maximum=100,variable=self.progress).pack(fill='x',pady=(10,4))
        self.status = tk.StringVar(value='待機')
        ttk.Label(body,textvariable=self.status,wraplength=540).pack(anchor='w')
        selection = ttk.LabelFrame(body,text='下次開始即時音訊時使用',padding=10)
        selection.pack(fill='x',pady=(14,8))
        self.choices = {}
        for row,(key,title,mapping,allowed) in enumerate([
            ('speech_en','英文辨識',SPEECH_LABELS,('auto','tiny.en','base.en','small','turbo')),
            ('speech_ja','日文辨識',SPEECH_LABELS,('auto','small','turbo')),
            ('speech_mixed','中英混合辨識',SPEECH_LABELS,('auto','small','turbo')),
            ('translation','日文翻譯',TRANSLATION_LABELS,tuple(TRANSLATION_LABELS)),
            ('device','運算裝置',DEVICE_LABELS,tuple(DEVICE_LABELS)),
        ]):
            value=settings.get(key,'auto')
            if value not in allowed: value='auto'
            var=tk.StringVar(value=mapping[value])
            ttk.Label(selection,text=title).grid(row=row,column=0,sticky='w',padx=(0,10),pady=4)
            ttk.Combobox(selection,textvariable=var,values=[mapping[k] for k in allowed],
                         state='readonly',width=36).grid(row=row,column=1,sticky='w')
            self.choices[key]=(var,{mapping[k]:k for k in allowed})
        footer=ttk.Frame(body);footer.pack(fill='x')
        ttk.Button(footer,text='使用教學',command=lambda:open_help(self.window)).pack(side='left')
        ttk.Button(footer,text='儲存模型選擇',command=self.save).pack(side='right')
        ttk.Button(footer,text='完成設定',command=self.finish_setup).pack(side='right',padx=8)
        self.refresh()
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.after(80,self.poll)

    def refresh(self):
        selected=self.tree.selection()
        for spec,path in inventory():
            values=(spec.purpose,spec.size,'已安裝' if path else '尚未下載')
            if self.tree.exists(spec.key): self.tree.item(spec.key,text=spec.name,values=values)
            else: self.tree.insert('','end',iid=spec.key,text=spec.name,values=values)
        if not selected: self.tree.selection_set('small')
        self.describe()

    def describe(self,_event=None):
        selection=self.tree.selection()
        if selection:
            spec=MODELS[selection[0]]
            self.description.set(f'{spec.name}｜{spec.license}')
            path=local_model_path(spec.key)
            if path: self.description.set(self.description.get()+'\n位置：'+str(path))
            if spec.key == 'nllb':
                self.description.set(self.description.get()+'\n實驗功能：部分句子仍可能嚴重誤譯，預設使用較快的 Argos。')

    def _post(self,event):
        try: self.events.put_nowait(event)
        except Full:
            try: self.events.get_nowait()
            except Empty: pass
            try: self.events.put_nowait(event)
            except Full: pass

    def browse_directory(self):
        value=filedialog.askdirectory(parent=self.window,title='選擇模型存放資料夾',initialdir=self.folder.get(),mustexist=False)
        if value: self.folder.set(value)

    def apply_directory(self):
        if self.running or self.is_busy():
            self.status.set('請先停止翻譯並等下載結束，再更換模型位置。')
            return False
        try:
            path=writable_directory(self.folder.get())
            self.on_save({'model_directory':str(path)})
            self.folder.set(str(path))
            self.refresh()
            self.status.set('模型位置已儲存；可下載或匯入模型。')
            return True
        except (OSError,ValueError) as error:
            self.status.set('無法使用這個位置：'+str(error))
            return False

    def download_recommended(self):
        if self.running or not self.apply_directory(): return
        keys, speech=PROFILES[self.profile.get()]
        selected_speech='auto' if speech=='turbo' else speech if speech!='base.en' else 'small'
        updates={'speech_en':'base.en','speech_mixed':selected_speech,
                 'speech_ja':selected_speech,
                 'language':'en' if speech=='base.en' else 'mixed','translation':'auto',
                 'setup_profile':list(PROFILES).index(self.profile.get())}
        try: self.on_save(updates)
        except OSError as error:
            self.status.set('無法儲存模型選擇：'+str(error));return
        for key in ('speech_en','speech_mixed','speech_ja'):
            self.choices[key][0].set(SPEECH_LABELS[updates[key]])
        self.choices['translation'][0].set(TRANSLATION_LABELS['auto'])
        self.run_downloads(keys)

    def start_download(self):
        selected=self.tree.selection()
        if self.running or not selected: return
        if not self.apply_directory(): return
        self.run_downloads(selected)

    def set_working(self, working):
        self.running=working
        for button in (self.download_button,self.recommended_button,self.import_button):
            button.configure(state='disabled' if working else 'normal')
        self.cancel_button.configure(state='normal' if working else 'disabled')

    def run_downloads(self, keys):
        self.running=True;self.cancel.clear();self.progress.set(0)
        self.status.set('準備下載…')
        self.set_working(True)
        def worker():
            try:
                for index,key in enumerate(keys):
                    download_model(key,lambda p,m:self._post(('progress',(index*100+p)/len(keys),f'{MODELS[key].name}｜{m}')),self.cancel)
                self._post(('done',100,'模型已就緒。按「完成設定」，再選擇收音與耳機裝置。'))
            except DownloadCancelled:
                self._post(('done',0,'已取消。辨識模型可使用快取接續；Argos 翻譯套件需重新下載。'))
            except Exception as error:
                self._post(('done',0,f'下載失敗，可重試：{error}'))
        Thread(target=worker,name='model-download',daemon=True).start()

    def start_import(self):
        selection=self.tree.selection()
        if self.running or not selection or self.is_busy():
            self.status.set('請先停止翻譯／下載，並選擇要匯入的模型。');return
        key=selection[0]
        legacy=legacy_model_path(key)
        source=filedialog.askdirectory(parent=self.window,title='選擇 '+MODELS[key].name+' 的模型資料夾',
                                       initialdir=str(legacy or model_directory()))
        if not source or not self.apply_directory(): return
        destination=model_directory()
        self.cancel.clear();self.set_working(True)
        self.status.set('正在複製模型，來源檔案會保留…')
        def check():
            if self.cancel.is_set(): raise DownloadCancelled()
        def worker():
            try:
                import_model(MODELS[key],source,destination,check)
                self._post(('done',100,'模型匯入完成。'))
            except DownloadCancelled: self._post(('done',0,'已取消匯入，來源檔案保留。'))
            except Exception as error: self._post(('done',0,'匯入失敗：'+str(error)))
        Thread(target=worker,name='model-import',daemon=True).start()

    def cancel_download(self):
        self.cancel.set();self.status.set('取消中，等待目前連線返回…')

    def poll(self):
        if self.closed: return
        try:
            while True:
                kind,percent,message=self.events.get_nowait()
                self.progress.set(percent);self.status.set(message)
                if kind=='done':
                    self.set_working(False)
                    self.refresh()
        except Empty: pass
        self.window.after(80,self.poll)

    def save(self):
        choices={key:mapping[var.get()] for key,(var,mapping) in self.choices.items()}
        try:
            self.on_save(choices)
            self.status.set('已儲存；下次開始音訊時生效')
        except OSError as error: self.status.set('無法儲存：'+str(error))

    def finish_setup(self):
        if self.running: self.status.set('請等下載／匯入完成。');return
        keys,_speech=PROFILES[self.profile.get()]
        missing=[MODELS[key].name for key in keys if local_model_path(key) is None]
        if missing:
            self.status.set('還缺少：'+'、'.join(missing)+'。請下載建議模型或匯入。');return
        try:
            self.on_save({'setup_completed':True})
        except OSError as error: self.status.set('無法儲存：'+str(error));return
        self.close()

    def close(self):
        self.closed=True;self.cancel.set();self.window.destroy()
