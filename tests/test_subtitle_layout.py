import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import audio_devices
from captions import CaptionUpdate
from subtitle_layout import LatestCaption, line_parts, normalized_position, window_position
from windows_overlay import overlay_style, REQUIRED_STYLE, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE


class SubtitleTests(unittest.TestCase):
    def test_old_translation_does_not_revive_latest_expired_caption(self):
        display = LatestCaption()
        old = CaptionUpdate(1, 1, 'first')
        latest = CaptionUpdate(2, 1, 'second')
        self.assertEqual(display.changed_row([old]), old)
        self.assertEqual(display.changed_row([old, latest]), latest)
        old = replace(old, traditional_chinese_text='第一句', state='translated')
        self.assertIsNone(display.changed_row([old, latest]))
        self.assertIsNone(display.changed_row([old]))
        translated = replace(latest, traditional_chinese_text='第二句', state='translated')
        self.assertEqual(display.changed_row([old, translated]), translated)
        self.assertIsNone(display.changed_row([old, replace(translated, is_final=True)]))
        display.reset()
        self.assertEqual(display.changed_row([old]), old)

    def test_bilingual_text_fits_one_line_and_retains_both_languages(self):
        parts = line_parts('Hold\nthe position ' * 20, '守住\n這個位置' * 20, 72, len)
        self.assertLessEqual(sum(len(text) for text, _ in parts), 72)
        self.assertTrue(parts[0][0].startswith('Hold the'))
        self.assertTrue(parts[-1][0].startswith('守住 這個'))
        self.assertTrue(parts[0][0].endswith('…'))
        self.assertTrue(parts[-1][0].endswith('…'))
        self.assertTrue(all('\n' not in text for text, _ in parts))

    def test_short_language_lends_space_to_longer_one(self):
        parts = line_parts('OK', '守住這個位置' * 20, 40, len)
        self.assertEqual(parts[0][0], 'OK')
        self.assertEqual(sum(len(text) for text, _ in parts), 40)
        self.assertEqual(line_parts('集合', '集合', 40, len), [('集合', 'white')])

    def test_positions_clamp_and_scale_to_new_resolution(self):
        self.assertEqual(normalized_position({'x':float('nan'),'y':.5}), normalized_position(None))
        self.assertEqual(normalized_position({'x':-1,'y':2}), {'x':0,'y':1})
        for sw, sh in ((1920,1080),(1280,720),(800,600)):
            for position in ({'x':0,'y':0},{'x':1,'y':1},{'x':.4,'y':.25}):
                x, y = window_position(position, sw, sh, 600, 40)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x+600, sw)
                self.assertLessEqual(y+40, sh)
        self.assertEqual(window_position({'x':.4,'y':.25},1280,720,600,40),(212,160))

    def test_position_save_preserves_devices_models_and_language(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(audio_devices, 'SETTINGS_PATH', Path(folder)/'settings.json'):
            original = dict(language='mixed', speech_mixed='turbo', capture={'name':'Cable'}, playback={'name':'Headphones'})
            audio_devices.update_settings(**original)
            audio_devices.update_settings(subtitle_position={'x':.2,'y':.3})
            saved = audio_devices.read_settings()
            for key, value in original.items():
                self.assertEqual(saved[key], value)
            self.assertEqual(saved['subtitle_position'], {'x':.2,'y':.3})

    def test_editing_accepts_mouse_without_changing_focus_flags(self):
        unrelated = 0x100
        edit = overlay_style(unrelated, True)
        self.assertFalse(edit & WS_EX_TRANSPARENT)
        self.assertTrue(edit & WS_EX_NOACTIVATE)
        passive = overlay_style(edit, False)
        self.assertEqual(passive & REQUIRED_STYLE, REQUIRED_STYLE)
        self.assertTrue(passive & unrelated)
