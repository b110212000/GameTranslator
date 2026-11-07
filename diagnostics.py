"""Explicit integration test: generated WAV -> cable -> live engine -> overlay."""
from pathlib import Path
import json
import socket
import time
import traceback
import tkinter as tk
import numpy as np
import sounddevice as sd
from version import __version__


def self_test(wav: Path, report: Path):
    result = {"version": __version__, "passed": False, "cycles": []}
    root = None
    original_connect = socket.socket.connect
    def offline_connect(*args, **kwargs):
        raise RuntimeError("Network access is disabled during the offline test")
    socket.socket.connect = offline_connect
    try:
        from app import GameTranslatorApp
        from audio_pipeline import load_pcm_wav_as_16khz_mono
        root = tk.Tk()
        ui = GameTranslatorApp(root)
        root.update()
        result["capture"] = ui.input_choice.get()
        result["playback"] = ui.output_choice.get()
        assert "CABLE Output" in result["capture"], result
        apis = sd.query_hostapis()
        cable = next(i for i, d in enumerate(sd.query_devices())
                     if "CABLE Input" in d["name"] and apis[d["hostapi"]]["name"] == "Windows WASAPI")
        mono = load_pcm_wav_as_16khz_mono(wav)
        audio = np.repeat(mono, 3)
        audio = np.concatenate([np.zeros(24000, dtype=np.float32), audio, np.zeros(48000, dtype=np.float32)])
        audio = np.repeat(audio[:, None], 2, axis=1)
        for cycle in range(2):
            ui.start_live_audio()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                root.update()
                if ui.captioner and ui.captioner.ready.is_set():
                    break
                if "錯誤" in ui.status.get() or "失敗" in ui.status.get():
                    raise RuntimeError(ui.status.get())
                time.sleep(0.02)
            assert ui.captioner and ui.captioner.ready.is_set(), ui.status.get()
            sd.play(audio, samplerate=48000, device=cable)
            deadline = time.monotonic() + 20
            peak = 0.0
            while time.monotonic() < deadline:
                root.update()
                peak = max(peak, ui.router.level if ui.router else 0)
                if ui.overlay.english_text.get():
                    break
                time.sleep(0.02)
            row = {"cycle": cycle + 1, "english": ui.overlay.english_text.get(),
                   "chinese": ui.overlay.traditional_chinese_text.get(),
                   "overlay_mapped": bool(ui.overlay.window.winfo_ismapped()),
                   "status": ui.status.get(), "peak_rms": peak,
                   "captured_frames": ui.router.captured_frames if ui.router else 0,
                   "played_frames": ui.router.played_frames if ui.router else 0}
            result["cycles"].append(row)
            assert "right" in row["english"].lower(), row
            assert row["chinese"] and row["overlay_mapped"] and row["played_frames"] > 0, row
            sd.stop()
            ui.stop_preview()
            root.update()
            assert str(ui.live_button.cget("state")) == "normal"
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
            try:
                ui.close()
            except Exception:
                root.destroy()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
