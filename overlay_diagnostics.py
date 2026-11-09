"""Exercise real Tk widgets while every application window remains withdrawn."""
import json
import time
import tkinter as tk
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from captions import CaptionUpdate
from subtitle_overlay import SubtitleOverlay, TRANSPARENT_COLOR
from subtitle_layout import DISPLAY_MS, normalized_position
from windows_overlay import PassiveWindow, REQUIRED_STYLE, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE
from version import __version__


def check_overlay(report):
    result = {'version':__version__, 'passed':False,
              'mode':'withdrawn Tk widgets; no visible windows, audio, game or physical mouse interaction'}
    root = tk.Tk()
    root.withdraw()
    overlay = None
    saved = []
    def pump(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            assert not root.winfo_ismapped()
            if overlay is not None:
                assert not overlay.window.winfo_ismapped()
            time.sleep(.01)
    # Skip only mapping and topmost maintenance. Real widgets, geometry, font
    # metrics, event handlers, timers and native style changes are exercised.
    try:
        with patch.object(PassiveWindow, 'show', lambda native: native.apply()), \
                patch.object(PassiveWindow, 'keep_on_top', lambda native: None):
            overlay = SubtitleOverlay(root, on_position=saved.append)
            source = CaptionUpdate(1, 1, 'Hold the position')
            overlay.show_rows([source])
            pump(.05)
            assert overlay.visible and overlay.english_text.get() == source.source_text
            assert overlay.canvas.cget('background') == TRANSPARENT_COLOR
            assert overlay.passive.flags() & REQUIRED_STYLE == REQUIRED_STYLE
            pump(.7)
            translated = replace(source, traditional_chinese_text='守住這個位置', state='translated')
            overlay.show_rows([translated])
            began = time.monotonic()
            pump(2.4)
            assert overlay.visible, 'Translation did not get its own reading time'
            pump(.7)
            assert not overlay.visible and not overlay.canvas.find_all()
            result['expiry_checked_after_seconds'] = round(time.monotonic()-began, 3)
            overlay.show_rows([translated])
            assert not overlay.visible, 'An unchanged expired row was resurrected'
            newer = CaptionUpdate(2, 1, 'Move now', traditional_chinese_text='現在移動')
            overlay.show_rows([translated, newer])
            expiry = overlay._expiry
            overlay.show_rows([replace(translated, traditional_chinese_text='舊翻譯'), newer])
            assert overlay._expiry == expiry, 'An older translation extended the newest caption'
            overlay.show_subtitle('守住這個位置 ' * 80, 'Hold this position ' * 80)
            pump(.05)
            items = overlay.canvas.find_withtag('caption')
            assert len(items) == 3
            assert len({overlay.canvas.coords(item)[1] for item in items}) == 1
            assert overlay.canvas.winfo_reqwidth() <= min(1000, root.winfo_screenwidth()-32)
            assert overlay.canvas.winfo_reqheight() < 80
            result['long_caption_size'] = [overlay.canvas.winfo_reqwidth(), overlay.canvas.winfo_reqheight()]
            overlay.begin_positioning()
            pump(DISPLAY_MS/1000+.1)
            assert overlay.visible and overlay.editing and overlay._expiry is None
            flags = overlay.passive.flags()
            assert not flags & WS_EX_TRANSPARENT and flags & WS_EX_NOACTIVATE
            old_position = dict(overlay.position)
            overlay._begin_drag(SimpleNamespace(x_root=500,y_root=500))
            overlay._drag(SimpleNamespace(x_root=200,y_root=200))
            overlay._end_drag(None)
            pump(.05)
            assert overlay.position != old_position and saved[-1] == overlay.position
            overlay.finish_positioning()
            assert not overlay.editing
            assert overlay.passive.flags() & REQUIRED_STYLE == REQUIRED_STYLE
            restored = SubtitleOverlay(root, position=saved[-1])
            assert restored.position == overlay.position
            restored.window.destroy()
            overlay.reset_position()
            assert saved[-1] == normalized_position(None)
            overlay.hide()
            assert overlay._expiry is None and not overlay.visible
            # Simulate the same ids after stopping and starting a new session.
            overlay.show_rows([source])
            assert overlay.visible
            overlay.hide()
            from app import GameTranslatorApp
            with patch('app.list_input_devices', return_value=[]), \
                    patch('app.list_output_devices', return_value=[]), \
                    patch('app.choose_device', return_value=None), \
                    patch('app.read_settings', return_value={'subtitle_position':saved[-1]}), \
                    patch('app.update_settings', side_effect=lambda **updates: updates):
                ui = GameTranslatorApp(root)
                ui.position_button.invoke()
                pump(.05)
                assert ui.overlay.editing and ui.position_button.cget('text') == '完成定位'
                assert not ui.overlay.window.winfo_ismapped()
                ui.position_button.invoke()
                assert not ui.overlay.editing and ui.position_button.cget('text') == '調整字幕位置'
                assert 'subtitle_position' in ui.settings
                ui.start_button.invoke()
                assert ui.start_button.cget('text') == '再次預覽'
                assert str(ui.start_button.cget('state')) == 'normal'
                ui.stop_preview()
                assert not ui.overlay.visible
                root.update_idletasks()
                result['main_window_requested_size'] = [root.winfo_reqwidth(), root.winfo_reqheight()]
                ui.closed = True
                ui.overlay.window.destroy()
            result['checks'] = ['three-second expiry', 'translation reading time', 'no stale resurrection',
                'single bilingual line', 'transparent canvas', 'persistent edit preview',
                'drag and save', 'position restore and reset', 'native click-through restore', 'session restart',
                'main-window positioning controls and repeat preview']
            result['passed'] = True
    finally:
        root.destroy()
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
