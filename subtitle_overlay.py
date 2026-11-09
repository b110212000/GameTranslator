"""One-line, outlined subtitles with expiry and an explicit drag-to-position mode."""
import tkinter as tk
from tkinter import font as tkfont

from subtitle_layout import DISPLAY_MS, LatestCaption, line_parts, normalized_position, window_position
from windows_overlay import PassiveWindow

TRANSPARENT_COLOR = "#ff00ff"
POSITION_PREVIEW = "拖曳這行字幕移動位置 · 雙擊完成"


class SubtitleOverlay:
    def __init__(self, root, position=None, on_position=None, on_editing=None):
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(background=TRANSPARENT_COLOR, takefocus=False)
        self.window.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.passive = PassiveWindow(self.window)
        self.position = normalized_position(position)
        self.on_position = on_position
        self.on_editing = on_editing
        self.font = tkfont.Font(self.window, family="Microsoft JhengHei UI", size=14, weight="bold")
        self.canvas = tk.Canvas(self.window, background=TRANSPARENT_COLOR,
                                highlightthickness=0, borderwidth=0, takefocus=False)
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._begin_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<Double-Button-1>", lambda _event: self.finish_positioning())
        self.english_text = tk.StringVar(self.window, value="")
        self.traditional_chinese_text = tk.StringVar(self.window, value="")
        self.visible = False
        self.editing = False
        self._drag_origin = None
        self._expiry = None
        self._latest = LatestCaption()
        self.window.after(1000, self._maintain_topmost)

    def _maintain_topmost(self):
        if self.visible:
            self.passive.keep_on_top()
        self.window.after(1000, self._maintain_topmost)

    def _cancel_expiry(self):
        if self._expiry is not None:
            self.window.after_cancel(self._expiry)
            self._expiry = None

    def _arm_expiry(self):
        self._cancel_expiry()
        if not self.editing:
            self._expiry = self.window.after(DISPLAY_MS, self._expire)

    def _expire(self):
        self._expiry = None
        self.hide(reset=False)

    def _draw(self, source, target):
        screen_width = self.window.winfo_screenwidth()
        padding = 8
        parts = line_parts(source, target, max(1, min(1000, screen_width - 32) - 2 * padding), self.font.measure)
        width = max(32, sum(self.font.measure(text) for text, _color in parts) + 2 * padding)
        height = self.font.metrics("linespace") + 12
        background = "#192a40" if self.editing else TRANSPARENT_COLOR
        self.canvas.configure(width=width, height=height, background=background,
                              cursor="fleur" if self.editing else "")
        self.canvas.delete("all")
        if self.editing:
            self.canvas.create_rectangle(1, 1, width - 1, height - 1, outline="#72b6ff")
        x, y = padding, height // 2
        for text, color in parts:
            # Outline only the glyphs: no panel obscures the game behind the text.
            for dx, dy in ((-1,-1), (0,-1), (1,-1), (-1,0), (1,0), (-1,1), (0,1), (1,1)):
                self.canvas.create_text(x+dx, y+dy, text=text, font=self.font,
                                        fill="#111111", anchor="w", tags="outline")
            self.canvas.create_text(x, y, text=text, font=self.font,
                                    fill=color, anchor="w", tags="caption")
            x += self.font.measure(text)
        x, y = window_position(self.position, screen_width, self.window.winfo_screenheight(), width, height)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.passive.show()
        self.visible = True

    def show_rows(self, rows):
        row = self._latest.changed_row(rows)
        if row is None or self.editing:
            return
        self.show_subtitle(row.traditional_chinese_text, row.source_text)

    def show_subtitle(self, traditional_chinese, english=""):
        if self.editing:
            return
        if not traditional_chinese.strip() and not english.strip():
            self.hide(reset=False)
            return
        self.english_text.set(english)
        self.traditional_chinese_text.set(traditional_chinese)
        self._draw(english, traditional_chinese)
        self._arm_expiry()

    def begin_positioning(self):
        self._cancel_expiry()
        self.editing = True
        self.passive.set_interactive(True)
        if self.on_editing:
            self.on_editing(True)
        self._draw("", POSITION_PREVIEW)

    def finish_positioning(self):
        if not self.editing:
            return
        self._drag_origin = None
        self.editing = False
        self.passive.set_interactive(False)
        if self.on_editing:
            self.on_editing(False)
        self._save_position()
        self.show_subtitle("字幕位置已設定", "Subtitle position saved")

    def reset_position(self):
        self.position = normalized_position(None)
        self._save_position()
        if self.editing:
            self._draw("", POSITION_PREVIEW)
        else:
            self.show_subtitle("字幕位置已重設", "Subtitle position reset")

    def _save_position(self):
        if self.on_position:
            self.on_position(dict(self.position))

    def _begin_drag(self, event):
        if self.editing:
            self._drag_origin = (event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())

    def _drag(self, event):
        if not self.editing or self._drag_origin is None:
            return
        start_x, start_y, left, top = self._drag_origin
        sw, sh = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        width, height = self.window.winfo_width(), self.window.winfo_height()
        x = max(0, min(sw-width, left + event.x_root - start_x))
        y = max(0, min(sh-height, top + event.y_root - start_y))
        self.position = {"x": (x + width/2)/sw, "y": (y + height/2)/sh}
        self.window.geometry(f"+{x}+{y}")

    def _end_drag(self, _event):
        if self._drag_origin is not None:
            self._drag_origin = None
            self._save_position()

    def hide(self, reset=True):
        self._cancel_expiry()
        self.visible = False
        self._drag_origin = None
        if self.editing:
            self.editing = False
            self.passive.set_interactive(False)
            if self.on_editing:
                self.on_editing(False)
        if reset:
            self._latest.reset()
        self.canvas.delete("all")
        self.english_text.set("")
        self.traditional_chinese_text.set("")
        self.window.withdraw()
