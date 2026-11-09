"""Open the bundled, offline Traditional Chinese guide on user request."""
import os
from pathlib import Path
import sys
from tkinter import messagebox


def guide_path():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    return root/'docs'/'使用教學.html'


def open_help(parent=None):
    try: os.startfile(str(guide_path()))
    except OSError as error: messagebox.showerror('無法開啟教學',str(error),parent=parent)
