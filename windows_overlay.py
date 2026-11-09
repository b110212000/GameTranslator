"""Native layered overlay flags: pass pointer input through, never activate."""
import ctypes
from ctypes import wintypes
import sys

WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
REQUIRED_STYLE = WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE


def overlay_style(style, interactive=False):
    style |= REQUIRED_STYLE
    return style & ~WS_EX_TRANSPARENT if interactive else style


class PassiveWindow:
    def __init__(self, window):
        self.window = window
        self.hwnd = None
        self.interactive = False
        if sys.platform == 'win32':
            self.api = ctypes.WinDLL('user32', use_last_error=True)
            self.api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            self.api.GetAncestor.restype = wintypes.HWND
            self.get_style = self.api.GetWindowLongPtrW
            self.get_style.argtypes = [wintypes.HWND, ctypes.c_int]
            self.get_style.restype = ctypes.c_ssize_t
            self.set_style = self.api.SetWindowLongPtrW
            self.set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            self.set_style.restype = ctypes.c_ssize_t
            self.api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            self.api.SetWindowPos.restype = wintypes.BOOL
            self.api.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            self.api.ShowWindow.restype = wintypes.BOOL

    def apply(self):
        if sys.platform != 'win32': return
        self.window.update_idletasks()
        self.hwnd = self.api.GetAncestor(self.window.winfo_id(), 2)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        style = self.get_style(self.hwnd, -20)
        ctypes.set_last_error(0)
        previous = self.set_style(self.hwnd, -20, overlay_style(style, self.interactive))
        if previous == 0 and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        # Keep the subtitles visible when the control window is minimized.
        if self.get_style(self.hwnd, -8):
            ctypes.set_last_error(0)
            previous = self.set_style(self.hwnd, -8, 0)  # GWLP_HWNDPARENT
            if previous == 0 and ctypes.get_last_error():
                raise ctypes.WinError(ctypes.get_last_error())

    def set_interactive(self, enabled):
        self.interactive = enabled
        self.apply()

    def show(self):
        self.apply()  # Set NOACTIVATE before Tk maps the window.
        self.window.deiconify()
        if sys.platform == 'win32':
            self.apply()  # Tk may recreate its wrapper on a map transition.
            self.api.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
            self.keep_on_top()

    def keep_on_top(self):
        if sys.platform == 'win32' and self.hwnd:
            # NOACTIVATE: returning to a game must not give focus to captions.
            if not self.api.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0,
                    0x0010 | 0x0040 | 0x0001 | 0x0002):
                raise ctypes.WinError(ctypes.get_last_error())

    def flags(self):
        self.apply()
        return self.get_style(self.hwnd, -20) if self.hwnd else 0
