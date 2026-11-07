"""Offline integration: real cable, original-first captions, translation patches."""
from pathlib import Path
from dataclasses import asdict
import json
import socket
import time
import traceback
import tkinter as tk
import numpy as np
import sounddevice as sd
from version import __version__


def self_test(wav: Path, report: Path, language="en"):
    result = {"version": __version__, "language": language, "passed": False, "cycles": []}
    root = None
    original_connect = socket.socket.connect
    def offline_connect(*args, **kwargs):
        raise RuntimeError("Network access is disabled during the offline test")
    socket.socket.connect = offline_connect
    try:
        from app import GameTranslatorApp, LANGUAGES
        from audio_pipeline import load_pcm_wav_as_16khz_mono
        root = tk.Tk()
        ui = GameTranslatorApp(root)
        rendered = []
        original_show_rows = ui.overlay.show_rows
        def observe_rows(rows):
            snapshot = list(rows)
            original_show_rows(snapshot)
            rendered.append((time.monotonic(), snapshot))
        ui.overlay.show_rows = observe_rows
        ui.language_choice.set(next(k for k,v in LANGUAGES.items() if v == language))
        root.update()
        result["capture"] = ui.input_choice.get()
        result["playback"] = ui.output_choice.get()
        assert "CABLE Output" in result["capture"], result
        apis = sd.query_hostapis()
        cable = next(i for i, d in enumerate(sd.query_devices())
                     if "CABLE Input" in d["name"] and apis[d["hostapi"]]["name"] == "Windows WASAPI")
        mono = load_pcm_wav_as_16khz_mono(wav)
        result["sample_seconds"] = len(mono)/16000
        audio = np.repeat(mono, 3)
        audio = np.concatenate([np.zeros(24000, dtype=np.float32), audio, np.zeros(48000, dtype=np.float32)])
        audio = np.repeat(audio[:, None], 2, axis=1)
        for cycle in range(2):
            rendered.clear()
            ui.start_live_audio()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                root.update()
                if ui.captioner and ui.captioner.ready.is_set(): break
                if "錯誤" in ui.status.get() or "失敗" in ui.status.get():
                    raise RuntimeError(ui.status.get())
                time.sleep(0.01)
            assert ui.captioner and ui.captioner.ready.is_set(), ui.status.get()
            observations, seen = [], set()
            first_source = first_chinese = None
            source_only_visible = False
            started = time.monotonic()
            sd.play(audio, samplerate=48000, device=cable)
            deadline = started + len(audio)/48000 + 15
            peak = 0.0
            while time.monotonic() < deadline:
                root.update()
                elapsed = time.monotonic() - started
                peak = max(peak, ui.router.level if ui.router else 0)
                rows = list(ui.caption_store.rows.values())
                for row in rows:
                    key = (row.segment_id, row.revision, row.state)
                    if key not in seen:
                        seen.add(key)
                        observations.append({"at_seconds": round(elapsed,3), **asdict(row)})
                    if row.source_text and first_source is None: first_source = elapsed
                    if row.traditional_chinese_text and first_chinese is None: first_chinese = elapsed
                    if row.source_text and not row.traditional_chinese_text:
                        source_only_visible = bool(ui.overlay.window.winfo_ismapped())
                if elapsed >= len(audio)/48000 + 1 and rows and all(r.is_final and r.state in ('translated','skipped','error') for r in rows):
                    break
                time.sleep(0.01)
            first_source = next((at-started for at,rs in rendered if any(r.source_text for r in rs)), None)
            first_chinese = next((at-started for at,rs in rendered if any(r.traditional_chinese_text for r in rs)), None)
            source_only_visible = any(r.source_text and not r.traditional_chinese_text for _,rs in rendered for r in rs)
            rows = list(ui.caption_store.rows.values())
            row = {"cycle": cycle+1, "first_source_seconds": first_source,
                   "first_translation_seconds": first_chinese,
                   "source_visible_before_translation": source_only_visible,
                   "captions": [asdict(r) for r in rows], "observations": observations, "backend": ui.captioner.backend,
                   "overlay_mapped": bool(ui.overlay.window.winfo_ismapped()), "peak_rms": peak,
                   "captured_frames": ui.router.captured_frames if ui.router else 0,
                   "played_frames": ui.router.played_frames if ui.router else 0}
            result["cycles"].append(row)
            assert first_source is not None and first_chinese is not None, row
            assert first_source < first_chinese and source_only_visible, row
            assert row["overlay_mapped"] and row["played_frames"] > 0, row
            assert any(r.state == "translated" and r.traditional_chinese_text for r in rows), row
            assert all(r.is_final and r.state == "translated" for r in rows), row
            assert list(ui.caption_store.rows) == sorted(ui.caption_store.rows), row
            if language == "ja":
                assert any(any('\u3040' <= ch <= '\u30ff' for ch in r.source_text) for r in rows), row
            sd.stop()
            ui.stop_preview()
            root.update()
            assert str(ui.live_button.cget("state")) == "normal"
            assert str(ui.language_select.cget("state")) == "readonly"
            assert not ui.overlay.window.winfo_ismapped()
        ui.close()
        root = None
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        raise
    finally:
        socket.socket.connect = original_connect
        sd.stop()
        if root:
            try: ui.close()
            except Exception: root.destroy()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
