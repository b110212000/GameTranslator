"""GameTranslator MVP 1: Windows preview window and subtitle overlay.

Run this file directly to open the preview UI.  Future audio/translation code can
call ``GameTranslatorApp.set_subtitle_text`` from any thread; the UI update is
scheduled safely on Tk's event loop.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from audio_devices import AudioDevice, list_input_devices, list_output_devices


PREVIEW_SUBTITLE = "隊友正在 A 點佈防，小心右側！"
OVERLAY_TRANSPARENT_COLOR = "#ff00ff"


class SubtitleOverlay:
    """A single-line, borderless, always-on-top subtitle window."""

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

        self.text = tk.StringVar(value="")
        self.label = tk.Label(
            self.window,
            textvariable=self.text,
            font=("Microsoft JhengHei UI", 20, "bold"),
            foreground="white",
            background="#1d1d1d",
            padx=22,
            pady=12,
        )
        self.label.pack(padx=12, pady=12)

    def show_subtitle(self, text: str) -> None:
        """Show one line of subtitle text, replacing the current text."""
        cleaned = " ".join(text.splitlines()).strip()
        if not cleaned:
            self.hide()
            return

        self.text.set(cleaned)
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
        self.text.set("")
        self.window.withdraw()


class GameTranslatorApp:
    """Small control window for the subtitle preview mode."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GameTranslator")
        self.root.resizable(False, False)
        self.overlay = SubtitleOverlay(root)
        self.is_previewing = False
        self.input_devices: list[AudioDevice] = []
        self.output_devices: list[AudioDevice] = []

        container = ttk.Frame(root, padding=24)
        container.grid()

        ttk.Label(container, text="GameTranslator", font=("Microsoft JhengHei UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(container, text="預覽模式：字幕顯示流程驗證", foreground="#555555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 18)
        )

        ttk.Label(container, text="狀態：").grid(row=2, column=0, sticky="w")
        self.status = tk.StringVar(value="待機")
        ttk.Label(container, textvariable=self.status, font=("Microsoft JhengHei UI", 11, "bold")).grid(
            row=2, column=1, sticky="w"
        )

        self.start_button = ttk.Button(container, text="開始預覽", command=self.start_preview)
        self.start_button.grid(row=3, column=0, sticky="ew", pady=(20, 0), padx=(0, 8))
        self.stop_button = ttk.Button(container, text="停止預覽", command=self.stop_preview, state="disabled")
        self.stop_button.grid(row=3, column=1, sticky="ew", pady=(20, 0))

        ttk.Separator(container).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(20, 12))
        ttk.Label(container, text="語音輸入（遊戲請指定輸出到 CABLE Input）：").grid(row=5, column=0, columnspan=2, sticky="w")
        self.input_choice = tk.StringVar()
        self.input_select = ttk.Combobox(container, textvariable=self.input_choice, width=55, state="readonly")
        self.input_select.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        ttk.Label(container, text="耳機輸出（保留隊友原音）：").grid(row=7, column=0, columnspan=2, sticky="w")
        self.output_choice = tk.StringVar()
        self.output_select = ttk.Combobox(container, textvariable=self.output_choice, width=55, state="readonly")
        self.output_select.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(4, 6))
        ttk.Button(container, text="重新掃描裝置", command=self.refresh_audio_devices).grid(row=9, column=0, columnspan=2, sticky="w")

        ttk.Label(container, text="字幕文字入口（供後續音訊／翻譯模組呼叫）：").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(20, 4)
        )
        self.subtitle_input = tk.StringVar(value=PREVIEW_SUBTITLE)
        self.entry = ttk.Entry(container, textvariable=self.subtitle_input, width=38)
        self.entry.grid(row=11, column=0, columnspan=2, sticky="ew")
        self.entry.bind("<Return>", lambda _event: self.set_subtitle_text(self.subtitle_input.get()))

        self.refresh_audio_devices()
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
        if self.input_devices and not self.input_choice.get():
            cable_input = next((device for device in self.input_devices if "CABLE Output" in device.name), self.input_devices[0])
            self.input_choice.set(cable_input.label)
        if self.output_devices and not self.output_choice.get():
            self.output_choice.set(self.output_devices[0].label)

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

    def stop_preview(self) -> None:
        self.is_previewing = False
        self.status.set("待機")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.overlay.hide()

    def set_subtitle_text(self, text: str) -> None:
        """Public subtitle entry point for future recognition/translation code."""
        if self.is_previewing:
            self.root.after(0, self.overlay.show_subtitle, text)

    def close(self) -> None:
        self.overlay.window.destroy()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    GameTranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
