"""Run the MVP recorded-audio pipeline, optionally through the subtitle UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Sequence

from app import GameTranslatorApp
from audio_pipeline import CaptionResult, RecordedAudioPipeline


DEFAULT_WAVS = (
    Path("samples/watch_right.wav"),
    Path("samples/two_at_a.wav"),
    Path("samples/rotate_b.wav"),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recognize English WAV files and display Traditional Chinese captions.")
    parser.add_argument("wav", nargs="*", type=Path, help="Completed English WAV files to process in order.")
    parser.add_argument("--model", default="base.en", help="faster-whisper model name (default: base.en).")
    parser.add_argument("--preview", action="store_true", help="Show captions in the GameTranslator preview window.")
    return parser.parse_args(argv)


def process_to_console(wavs: list[Path], model_name: str) -> int:
    pipeline = RecordedAudioPipeline(model_name)
    pipeline.process_paths(wavs, lambda caption: print(json.dumps(caption.to_dict(), ensure_ascii=False)))
    return 0


def process_to_preview(wavs: list[Path], model_name: str) -> int:
    import tkinter as tk

    root = tk.Tk()
    ui = GameTranslatorApp(root)
    ui.start_preview()
    captions: Queue[CaptionResult] = Queue()
    errors: Queue[Exception] = Queue()

    def worker() -> None:
        try:
            RecordedAudioPipeline(model_name).process_paths(wavs, captions.put)
        except Exception as error:  # surfaced in the window status and console
            errors.put(error)

    def poll_results() -> None:
        try:
            while True:
                caption = captions.get_nowait()
                print(json.dumps(caption.to_dict(), ensure_ascii=False))
                ui.set_subtitle_text(caption.traditional_chinese_text)
        except Empty:
            pass

        try:
            error = errors.get_nowait()
        except Empty:
            root.after(50, poll_results)
        else:
            ui.status.set(f"預覽失敗：{error}")
            print(f"ERROR: {error}")

    Thread(target=worker, name="recorded-audio-pipeline", daemon=True).start()
    root.after(50, poll_results)
    root.mainloop()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    wavs = args.wav or list(DEFAULT_WAVS)
    missing = [str(path) for path in wavs if not path.is_file()]
    if missing:
        raise SystemExit("Missing WAV file(s): " + ", ".join(missing) + ". Run scripts\\generate_sample_audio.ps1 first.")
    return process_to_preview(wavs, args.model) if args.preview else process_to_console(wavs, args.model)


if __name__ == "__main__":
    raise SystemExit(main())
