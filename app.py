"""Windows controls and bilingual overlay for local live translation.

Worker results reach the Tk event loop through a queue. All widget updates,
including ``set_subtitle_text``, run on the UI thread.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from queue import Empty, Queue

from audio_devices import AudioDevice, list_input_devices, list_output_devices, read_settings, save_settings, choose_device
from version import __version__
import logging
from pathlib import Path
import sys
from audio_router import AudioRoute, AudioRouter
from live_captioner import LiveCaptioner


PREVIEW_SUBTITLE = "隊友正在 A 點佈防，小心右側！"
OVERLAY_TRANSPARENT_COLOR = "#ff00ff"


class SubtitleOverlay:
    """A bilingual, borderless, always-on-top subtitle window."""

    def __init__(self, root: tk.Tk) -> None:
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(background=OVERLAY_TRANSPARENT_COLOR)

        # Windows supports a colour-key transparency region.  If a different
        # Tk backend does not, the readable dark subtitle panel still works.
        try:
            self.window.attributes("-transparentcolor", OVERLAY_TRANSPARENT_COLOR)
        except tk.TclError:
            pass

        self.english_text = tk.StringVar(value="")
        self.traditional_chinese_text = tk.StringVar(value="")
        self.english_label = tk.Label(
            self.window,
            textvariable=self.english_text,
            font=("Segoe UI", 12),
            foreground="#d7d7d7",
            background="#1d1d1d",
            padx=22,
            pady=2,
        )
        self.english_label.pack(padx=12, pady=(12, 0))
        self.label = tk.Label(
            self.window,
            textvariable=self.traditional_chinese_text,
            font=("Microsoft JhengHei UI", 20, "bold"),
            foreground="white",
            background="#1d1d1d",
            padx=22,
            pady=10,
        )
        self.label.pack(padx=12, pady=(0, 12))

    def show_subtitle(self, traditional_chinese: str, english: str = "") -> None:
        """Show an English original with its Traditional Chinese translation."""
        chinese_line = " ".join(traditional_chinese.splitlines()).strip()
        english_line = " ".join(english.splitlines()).strip()
        if not chinese_line:
            self.hide()
            return

        self.english_text.set(english_line)
        self.traditional_chinese_text.set(chinese_line)
        self.english_label.pack_forget()
        if english_line:
            self.english_label.pack(padx=12, pady=(12, 0), before=self.label)
        self.window.deiconify()
        self.window.lift()
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, screen_height - height - 120)
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def hide(self) -> None:
        self.english_text.set("")
        self.traditional_chinese_text.set("")
        self.window.withdraw()


class GameTranslatorApp:
    """Audio routing controls, live translation status, and subtitle preview."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"GameTranslator v{__version__}")
        self.root.resizable(False, False)
        self.overlay = SubtitleOverlay(root)
        self.is_previewing = False
        self.router: AudioRouter | None = None
        self.captioner: LiveCaptioner | None = None
        self.events = Queue()
        self.generation = 0
        self.settings = read_settings()
        self.closed = False
        self.input_devices: list[AudioDevice] = []
        self.output_devices: list[AudioDevice] = []

        container = ttk.Frame(root, padding=24)
        container.grid()

        ttk.Label(container, text=f"GameTranslator v{__version__}", font=("Microsoft JhengHei UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(container, text="全本機英文 → 繁中｜雙語字幕・原音直通", foreground="#555555").grid(
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

        ttk.Label(container, text="字幕預覽文字：").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(20, 4)
        )
        self.subtitle_input = tk.StringVar(value=PREVIEW_SUBTITLE)
        self.entry = ttk.Entry(container, textvariable=self.subtitle_input, width=38)
        self.entry.grid(row=11, column=0, columnspan=2, sticky="ew")
        self.entry.bind("<Return>", lambda _event: self.set_subtitle_text(self.subtitle_input.get()))

        self.level = tk.DoubleVar(value=0)
        ttk.Progressbar(container, variable=self.level, maximum=100).grid(row=12, column=0, columnspan=2, sticky="ew", pady=(16, 4))
        self.signal = tk.StringVar(value="輸入音量｜尚未開始")
        ttk.Label(container, textvariable=self.signal).grid(row=13, column=0, columnspan=2, sticky="w")
        self.input_select.bind("<<ComboboxSelected>>", self.save_audio_selection)
        self.output_select.bind("<<ComboboxSelected>>", self.save_audio_selection)

        self.refresh_audio_devices()
        self.root.after(50, self.poll_live_captions)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

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
                save_settings(capture, playback)
                self.settings = read_settings()
            except OSError as error:
                self.status.set(f"無法儲存設定：{error}")

    def set_running_controls(self, running):
        self.live_button.configure(state="disabled" if running else "normal")
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        for selector in (self.input_select, self.output_select):
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
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.set_subtitle_text(self.subtitle_input.get() or PREVIEW_SUBTITLE)

    def start_live_audio(self) -> None:
        if self.router is not None:
            return
        capture, playback = self.selected_audio_device_indexes()
        if capture is None or playback is None:
            self.status.set("請先選擇輸入與耳機輸出裝置")
            return
        try:
            self.save_audio_selection()
            self.generation += 1
            run = self.generation
            self.captioner = LiveCaptioner(
                lambda caption: self.events.put((run, "caption", caption)),
                lambda error: self.events.put((run, "error", str(error))),
                lambda: self.events.put((run, "ready", None)),
            )
            self.router = AudioRouter(AudioRoute(capture, playback), self.captioner.submit)
            self.router.start()
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
            self.captioner = None
        self.is_previewing = False
        self.status.set("待機")
        self.set_running_controls(False)
        self.level.set(0)
        self.signal.set("輸入音量｜已停止")
        self.overlay.hide()

    def poll_live_captions(self) -> None:
        if self.closed:
            return
        try:
            while True:
                run, kind, value = self.events.get_nowait()
                if run != self.generation:
                    continue
                if kind == "ready":
                    self.status.set("即時翻譯中｜模型已就緒")
                    self.overlay.show_subtitle("等待英文語音…")
                elif kind == "caption":
                    self.set_subtitle_text(value.traditional_chinese_text, value.english_text)
                    self.status.set(f"即時翻譯中｜本段處理 {value.processing_latency_seconds:.2f} 秒")
                elif kind == "error":
                    self.stop_preview()
                    self.status.set(f"即時翻譯錯誤：{value}")
        except Empty:
            pass
        if self.router:
            self.level.set(min(100, self.router.level * 500))
            self.signal.set("輸入音量｜收到聲音" if self.router.level >= 0.002 else "輸入音量｜安靜／尚未收到聲音")
        self.root.after(50, self.poll_live_captions)

    def set_subtitle_text(self, text: str, english_text: str = "") -> None:
        """Update subtitles on the UI thread."""
        if self.is_previewing:
            self.overlay.show_subtitle(text, english_text)

    def close(self) -> None:
        self.closed = True
        self.stop_preview()
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
    args = parser.parse_args()
    if args.self_test and not args.test_wav:
        parser.error("--self-test requires --test-wav")
    log_path = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent) / "GameTranslator.log"
    logging.basicConfig(filename=log_path, level=logging.WARNING, encoding="utf-8")
    if args.self_test:
        from diagnostics import self_test
        self_test(args.test_wav, args.self_test)
        return
    root = tk.Tk()
    ui = GameTranslatorApp(root)
    if args.start:
        root.after(150, ui.start_live_audio)
    root.mainloop()


if __name__ == "__main__":
    main()
