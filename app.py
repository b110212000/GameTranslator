"""Windows controls and bilingual overlay for local live translation.

Worker results reach the Tk event loop through a queue. All widget updates,
including ``set_subtitle_text``, run on the UI thread.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from queue import Empty, Queue, Full
from time import perf_counter

from audio_devices import AudioDevice, list_input_devices, list_output_devices, read_settings, save_settings, choose_device, update_settings
from version import __version__
import logging
from pathlib import Path
import sys
from audio_router import AudioRoute, AudioRouter
from live_captioner import LiveCaptioner
from captions import CaptionStore, translation_line
from subtitle_overlay import SubtitleOverlay


PREVIEW_SUBTITLE = "字幕預覽：原文先顯示，翻譯隨後補上。"
LANGUAGES = {"中英混合（建議）": "mixed", "純英文": "en", "日文": "ja"}
LANGUAGE_NAMES = {'mixed':'中／英文','en':'英文','ja':'日文'}


class GameTranslatorApp:
    """Audio routing controls, live translation status, and subtitle preview."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"GameTranslator v{__version__}")
        self.root.resizable(False, False)
        self.settings = read_settings()
        self.overlay = SubtitleOverlay(root, self.settings.get("subtitle_position"),
                                       self.save_subtitle_position, self.position_editing_changed)
        self.is_previewing = False
        self.router: AudioRouter | None = None
        self.captioner: LiveCaptioner | None = None
        self.events = Queue(maxsize=256)
        self.retiring = []
        self.model_manager = None
        self.started_at = 0
        self.last_sound_at = 0
        self.generation = 0
        self.caption_store = CaptionStore(limit=6)
        self.closed = False
        self.input_devices: list[AudioDevice] = []
        self.output_devices: list[AudioDevice] = []

        container = ttk.Frame(root, padding=24)
        container.grid()

        ttk.Label(container, text=f"GameTranslator v{__version__}", font=("Microsoft JhengHei UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(container, text="中英混合／日文 → 繁中｜原文先出・翻譯隨後補上", foreground="#555555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 18)
        )

        ttk.Label(container, text="狀態：").grid(row=2, column=0, sticky="w")
        self.status = tk.StringVar(value="待機")
        ttk.Label(container, textvariable=self.status, wraplength=350, font=("Microsoft JhengHei UI", 11, "bold")).grid(
            row=2, column=1, sticky="w"
        )

        self.start_button = ttk.Button(container, text="開始預覽", command=self.start_preview)
        self.start_button.grid(row=3, column=0, sticky="ew", pady=(20, 0), padx=(0, 8))
        self.stop_button = ttk.Button(container, text="停止", command=self.stop_preview, state="disabled")
        self.stop_button.grid(row=3, column=1, sticky="ew", pady=(20, 0))

        ttk.Separator(container).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(20, 12))
        ttk.Label(container, text="接收聲音：選 CABLE Output（Discord 輸出選 CABLE Input）").grid(row=5, column=0, columnspan=2, sticky="w")
        self.input_choice = tk.StringVar()
        self.input_select = ttk.Combobox(container, textvariable=self.input_choice, width=68, state="readonly")
        self.input_select.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        ttk.Label(container, text="耳機輸出（保留隊友原音）：").grid(row=7, column=0, columnspan=2, sticky="w")
        self.output_choice = tk.StringVar()
        self.output_select = ttk.Combobox(container, textvariable=self.output_choice, width=55, state="readonly")
        self.output_select.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 6))
        self.refresh_button = ttk.Button(container, text="重新掃描裝置", command=self.refresh_audio_devices)
        self.refresh_button.grid(row=9, column=0, sticky="w")
        self.live_button = ttk.Button(container, text="開始即時音訊", command=self.start_live_audio)
        self.live_button.grid(row=9, column=1, sticky="e")

        ttk.Label(container, text="字幕預覽文字（單行透明字幕，更新後 3 秒隱藏）：").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(20, 4)
        )
        self.subtitle_input = tk.StringVar(value=PREVIEW_SUBTITLE)
        self.entry = ttk.Entry(container, textvariable=self.subtitle_input, width=38)
        self.entry.grid(row=11, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda _event: self.set_subtitle_text(self.subtitle_input.get()))
        position_controls = ttk.Frame(container)
        position_controls.grid(row=11, column=1, sticky="e")
        self.position_button = ttk.Button(position_controls, text="調整字幕位置", command=self.toggle_positioning)
        self.position_button.pack(side="left")
        ttk.Button(position_controls, text="重設位置", command=self.overlay.reset_position).pack(side="left", padx=(6, 0))

        self.level = tk.DoubleVar(value=0)
        ttk.Progressbar(container, variable=self.level, maximum=100).grid(row=12, column=0, columnspan=2, sticky="ew", pady=(16, 4))
        self.signal = tk.StringVar(value="輸入音量｜尚未開始")
        ttk.Label(container, textvariable=self.signal).grid(row=13, column=0, columnspan=2, sticky="w")
        ttk.Label(container, text="語音語言：").grid(row=14, column=0, sticky="w", pady=(12, 4))
        saved_language = self.settings.get("language", "mixed")
        self.language_choice = tk.StringVar(value=next((k for k,v in LANGUAGES.items() if v == saved_language), "中英混合（建議）"))
        language_controls = ttk.Frame(container)
        language_controls.grid(row=14,column=1,sticky='w',pady=(12,4))
        self.language_select = ttk.Combobox(language_controls, textvariable=self.language_choice,
                                           values=list(LANGUAGES), state="readonly", width=16)
        self.language_select.pack(side='left')
        ttk.Button(language_controls,text='模型管理',command=self.open_model_manager).pack(side='left',padx=(8,0))
        from help_viewer import open_help
        ttk.Button(language_controls,text='使用教學',command=lambda:open_help(self.root)).pack(side='left',padx=(6,0))
        self.language_select.bind("<<ComboboxSelected>>", self.save_audio_selection)
        ttk.Label(container, text="最近字幕｜原文持續更新，中文補在同一段下方").grid(
            row=15, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self.history = tk.Text(container, width=60, height=8, wrap="word", state="disabled",
                               font=("Microsoft JhengHei UI", 10), background="#f7f7f7", relief="flat")
        self.history.grid(row=16, column=0, columnspan=2, sticky="ew")
        self.health = tk.StringVar(value='夾雜中文請選「中英混合」，中文會保留並轉成繁體。')
        ttk.Label(container,textvariable=self.health,wraplength=500,foreground='#555555').grid(
            row=17,column=0,columnspan=2,sticky='w',pady=(8,0))
        ttk.Label(container, text='遊戲內字幕請使用「視窗化全螢幕／無邊框」模式。\n'
                  '按「調整字幕位置」拖曳字幕，完成後恢復滑鼠穿透；主視窗可最小化。',
                  wraplength=500,foreground='#555555').grid(
            row=18,column=0,columnspan=2,sticky='w',pady=(8,0))
        self.input_select.bind("<<ComboboxSelected>>", self.save_audio_selection)
        self.output_select.bind("<<ComboboxSelected>>", self.save_audio_selection)

        self.refresh_audio_devices()
        self.root.after(50, self.poll_live_captions)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def toggle_positioning(self):
        if self.overlay.editing:
            self.overlay.finish_positioning()
        else:
            self.overlay.begin_positioning()

    def position_editing_changed(self, editing):
        self.position_button.configure(text="完成定位" if editing else "調整字幕位置")

    def save_subtitle_position(self, position):
        try:
            self.settings = update_settings(subtitle_position=position)
        except OSError as error:
            self.status.set(f"字幕已移動，但無法儲存位置：{error}")

    def open_model_manager(self, first_run=False):
        if self.model_manager and not self.model_manager.closed:
            self.model_manager.window.lift()
            return
        from model_manager import ModelManager
        self.model_manager = ModelManager(self.root,self.settings,self.save_model_choices,
            is_busy=lambda:self.router is not None or any(worker.is_alive for worker in self.retiring),first_run=first_run)

    def save_model_choices(self,choices):
        self.settings = update_settings(**choices)
        if 'language' in choices and self.router is None:
            self.language_choice.set(next(k for k,v in LANGUAGES.items() if v==choices['language']))
        self.health.set('模型選擇已儲存；停止後重新開始即可套用。')

    def _post_event(self,event):
        try: self.events.put_nowait(event)
        except Full:
            try: self.events.get_nowait()
            except Empty: pass
            try: self.events.put_nowait(event)
            except Full: pass

    def refresh_audio_devices(self) -> None:
        """Populate routing selectors without changing Windows audio settings."""
        try:
            self.input_devices = list_input_devices()
            self.output_devices = list_output_devices()
        except Exception as error:
            self.status.set(f"無法讀取音訊裝置：{error}")
            return
        self.input_select["values"] = [device.label for device in self.input_devices]
        self.output_select["values"] = [device.label for device in self.output_devices]
        for devices, choice, key, capture in ((self.input_devices, self.input_choice, "capture", True),
                                              (self.output_devices, self.output_choice, "playback", False)):
            device = choose_device(devices, self.settings.get(key, {}), capture)
            choice.set(device.label if device else "")

    def save_audio_selection(self, _event=None):
        capture = next((d for d in self.input_devices if d.label == self.input_choice.get()), None)
        playback = next((d for d in self.output_devices if d.label == self.output_choice.get()), None)
        if capture and playback:
            try:
                save_settings(capture, playback, LANGUAGES[self.language_choice.get()])
                self.settings = read_settings()
            except OSError as error:
                self.status.set(f"無法儲存設定：{error}")

    def set_running_controls(self, running):
        self.live_button.configure(state="disabled" if running else "normal")
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        for selector in (self.input_select, self.output_select, self.language_select):
            selector.configure(state="disabled" if running else "readonly")
        self.refresh_button.configure(state="disabled" if running else "normal")

    def selected_audio_device_indexes(self) -> tuple[int | None, int | None]:
        """Return selected capture and headphone endpoint indexes for the router."""
        return self._selected_index(self.input_choice.get()), self._selected_index(self.output_choice.get())

    @staticmethod
    def _selected_index(label: str) -> int | None:
        if not label.startswith("[") or "]" not in label:
            return None
        return int(label[1 : label.index("]")])

    def start_preview(self) -> None:
        self.is_previewing = True
        self.status.set("預覽中")
        self.start_button.configure(state="normal", text="再次預覽")
        self.stop_button.configure(state="normal")
        self.set_subtitle_text(self.subtitle_input.get() or PREVIEW_SUBTITLE)

    def start_live_audio(self) -> None:
        if any(worker.is_alive for worker in self.retiring):
            self.status.set('上一輪模型正在結束，稍後可重新開始…')
            return
        if self.router is not None:
            return
        capture, playback = self.selected_audio_device_indexes()
        if capture is None or playback is None:
            self.status.set("請先選擇輸入與耳機輸出裝置")
            return
        try:
            if self.overlay.editing:
                self.overlay.finish_positioning()
            self.overlay.hide()
            self.save_audio_selection()
            self.caption_store.clear()
            self.render_history()
            self.generation += 1
            run = self.generation
            language=LANGUAGES[self.language_choice.get()]
            model_name=self.settings.get('speech_'+language,'auto')
            allowed=('auto','tiny.en','base.en','small','turbo') if language=='en' else ('auto','small','turbo')
            if model_name not in allowed: model_name='auto'
            translation=self.settings.get('translation','auto')
            if translation not in ('auto','direct','argos'): translation='auto'
            self.captioner = LiveCaptioner(
                lambda caption: self._post_event((run, "caption", caption)),
                lambda error: self._post_event((run, "error", str(error))),
                lambda: self._post_event((run, "ready", None)),
                language=language, model_name=None if model_name=='auto' else model_name,
                translation=translation,device=self.settings.get('device','auto'),
            )
            self.router = AudioRouter(AudioRoute(capture, playback), self.captioner.submit)
            self.router.start()
            self.started_at=perf_counter()
            self.last_sound_at=self.started_at
            self.captioner.start()
        except Exception as error:
            self.stop_preview()
            logging.exception("Audio start failed")
            self.status.set(f"音訊啟動失敗：{error}")
            return
        self.is_previewing = True
        self.status.set("原音直通中｜模型載入與暖機…")
        self.set_running_controls(True)
        self.overlay.show_subtitle("本機模型準備中，原音已送往耳機…")

    def stop_preview(self) -> None:
        self.generation += 1
        if self.router is not None:
            self.router.stop()
            self.router = None
        if self.captioner is not None:
            self.captioner.stop()
            self.retiring.append(self.captioner)
            self.captioner = None
        self.is_previewing = False
        self.status.set("待機")
        self.set_running_controls(False)
        self.start_button.configure(text="開始預覽")
        if any(worker.is_alive for worker in self.retiring):
            self.live_button.configure(state='disabled')
        self.level.set(0)
        self.signal.set("輸入音量｜已停止")
        self.overlay.hide()

    def poll_live_captions(self) -> None:
        if self.closed:
            return
        self.retiring=[worker for worker in self.retiring if worker.is_alive]
        if not self.retiring and not self.router:
            self.live_button.configure(state='normal')
        try:
            while True:
                run, kind, value = self.events.get_nowait()
                if run != self.generation:
                    continue
                if kind == "ready":
                    self.status.set(f"即時翻譯中｜{self.captioner.backend} 模型已就緒")
                    language = LANGUAGES[self.language_choice.get()]
                    self.overlay.show_subtitle(f"等待{LANGUAGE_NAMES[language]}語音…")
                    self.health.set(self.captioner.translation_route+'｜字幕不攔截滑鼠')
                elif kind == "caption":
                    if not self.caption_store.apply(value):
                        continue
                    self.overlay.show_rows(self.caption_store.rows.values())
                    self.render_history()
                    if value.state == "translated":
                        self.status.set(f"{self.captioner.backend} 辨識 {value.recognition_seconds:.2f} 秒｜翻譯 {value.translation_seconds:.2f} 秒")
                    elif value.state in ("partial", "recognized"):
                        self.status.set("原文已顯示｜" + ("持續辨識中…" if value.state == "partial" else "中文翻譯中…"))
                elif kind == "error":
                    self.stop_preview()
                    self.status.set(f"即時翻譯錯誤：{value}")
        except Empty:
            pass
        if self.router:
            if perf_counter()-self.started_at > 3 and (not self.router.is_running or
                    perf_counter()-(self.router.last_capture_at or self.started_at) > 3):
                self.stop_preview()
                self.status.set('音訊裝置已中斷，請重新掃描並選擇裝置後開始。')
                self.root.after(50,self.poll_live_captions)
                return
            self.level.set(min(100, self.router.level * 500))
            self.signal.set("輸入音量｜收到聲音" if self.router.level >= 0.002 else "輸入音量｜安靜／尚未收到聲音")
            if self.router.level >= 0.002:
                self.last_sound_at=perf_counter()
            if self.captioner and self.captioner.ready.is_set():
                stats=self.captioner.snapshot()
                skipped=stats['skipped_segments']
                warning=f'｜忙碌，已略過 {skipped} 段' if skipped else ''
                fallback='｜GPU 已回退 CPU' if stats['gpu_fallbacks'] else ''
                self.health.set(f'{self.captioner.translation_route}｜排隊 {stats["recognition_queue"]}/{stats["translation_queue"]}{warning}{fallback}')
                if perf_counter()-self.last_sound_at > 8:
                    self.health.set('沒有收到聲音：請確認來源 App 輸出為 CABLE Input。測試自己說話時，接收裝置要選麥克風。')
        self.root.after(50, self.poll_live_captions)

    def render_history(self):
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        for row in self.caption_store.rows.values():
            self.history.insert("end", f"{row.source_text}\n{translation_line(row)}\n\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def set_subtitle_text(self, text: str, english_text: str = "") -> None:
        """Update subtitles on the UI thread."""
        if self.is_previewing:
            self.overlay.show_subtitle(text, english_text)

    def close(self) -> None:
        if self.closed: return
        self.closed = True
        if self.model_manager and not self.model_manager.closed: self.model_manager.close()
        self.stop_preview()
        self.status.set('正在結束模型，稍候關閉…')
        self._finish_close()

    def _finish_close(self):
        if any(worker.is_alive for worker in self.retiring):
            self.root.after(50,self._finish_close)
            return
        self.overlay.window.destroy()
        self.root.destroy()


def main() -> None:
    import argparse
    import multiprocessing
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--self-test", type=Path)
    parser.add_argument("--test-wav", type=Path)
    parser.add_argument('--headless',action='store_true',help='Silent self-test without desktop windows')
    parser.add_argument('--check-overlay', type=Path, help='Check hidden subtitle widgets, timers and positioning')
    parser.add_argument('--check-setup', type=Path, help='Check hidden first-run/model-directory controls')
    parser.add_argument('--test-translation',choices=('auto','direct','argos'),default='auto')
    parser.add_argument("--language", choices=("en", "ja", "mixed"))
    args = parser.parse_args()
    if args.self_test and not args.test_wav:
        parser.error("--self-test requires --test-wav")
    if args.headless and not args.self_test:
        parser.error('--headless requires --self-test')
    log_path = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent) / "GameTranslator.log"
    logging.basicConfig(filename=log_path, level=logging.WARNING, encoding="utf-8")
    if args.check_setup:
        from setup_diagnostics import check_setup
        try: check_setup(args.check_setup)
        except Exception:
            logging.exception('Hidden first-run check failed')
            raise SystemExit(1)
        return
    if args.check_overlay:
        from overlay_diagnostics import check_overlay
        try:
            check_overlay(args.check_overlay)
        except Exception:
            logging.exception('Hidden overlay check failed')
            raise SystemExit(1)
        return
    if args.self_test:
        if args.headless:
            from diagnostics import headless_test
            try:
                headless_test(args.test_wav,args.self_test,args.language or 'en',args.test_translation)
            except Exception:
                logging.exception('Headless self-test failed')
                raise SystemExit(1)  # A background test must not show an error dialog.
        else:
            from diagnostics import self_test
            self_test(args.test_wav, args.self_test, args.language or "en")
        return
    root = tk.Tk()
    ui = GameTranslatorApp(root)
    if not ui.settings.get('setup_completed') and (ui.settings.get('model_directory') or not ui.settings):
        root.after(300,lambda:ui.open_model_manager(first_run=True))
    if args.language:
        ui.language_choice.set(next(k for k,v in LANGUAGES.items() if v == args.language))
    if args.start:
        root.after(150, ui.start_live_audio)
    root.mainloop()


if __name__ == "__main__":
    main()
