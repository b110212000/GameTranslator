"""Recorded-audio recognition and English-to-Traditional-Chinese translation.

The public ``process_wav`` function is deliberately file/chunk based so a later
live capture layer can pass each completed WAV chunk into the same pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable
import wave

from deep_translator import MyMemoryTranslator
from faster_whisper import WhisperModel
import numpy as np


@dataclass(frozen=True)
class CaptionResult:
    source_file: str
    english_text: str
    traditional_chinese_text: str
    segment_end_seconds: float
    processing_latency_seconds: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RecordedAudioPipeline:
    """Reusable CPU-friendly English WAV pipeline for the MVP prototype."""

    def __init__(self, model_name: str = "base.en") -> None:
        # The first construction downloads the selected model into the user's
        # Hugging Face cache. int8 keeps the Windows CPU footprint small.
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
        # MyMemory's public endpoint is sufficient for the three-line MVP
        # demo and does not need an API key. Its documented English code is
        # en-GB, even when processing US English speech.
        self.translator = MyMemoryTranslator(source="en-GB", target="zh-TW")

    def process_wav(self, wav_path: Path) -> list[CaptionResult]:
        """Recognize one completed WAV and translate each non-empty segment."""
        started_at = perf_counter()
        audio = load_pcm_wav_as_16khz_mono(wav_path)
        segments, _info = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
        )
        results: list[CaptionResult] = []
        for segment in segments:
            english = segment.text.strip()
            if not english:
                continue
            translated = self.translator.translate(english)
            results.append(
                CaptionResult(
                    source_file=str(wav_path),
                    english_text=english,
                    traditional_chinese_text=translated,
                    segment_end_seconds=round(segment.end, 3),
                    # For this recorded-audio prototype, processing starts
                    # immediately after a completed WAV chunk is available.
                    processing_latency_seconds=round(perf_counter() - started_at, 3),
                )
            )
        return results

    def process_paths(
        self,
        wav_paths: Iterable[Path],
        on_caption: Callable[[CaptionResult], None],
    ) -> None:
        """Process completed WAV chunks in order and emit translated captions."""
        for wav_path in wav_paths:
            for caption in self.process_wav(wav_path):
                on_caption(caption)


def load_pcm_wav_as_16khz_mono(wav_path: Path) -> np.ndarray:
    """Load a 16-bit PCM WAV without relying on an external FFmpeg/PyAV build."""
    with wave.open(str(wav_path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
            raise ValueError(f"{wav_path} must be an uncompressed 16-bit PCM WAV file.")
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        raw_samples = wav.readframes(wav.getnframes())

    audio = np.frombuffer(raw_samples, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sample_rate == 16000:
        return audio

    source_positions = np.arange(len(audio), dtype=np.float64)
    target_length = round(len(audio) * 16000 / sample_rate)
    target_positions = np.linspace(0, len(audio) - 1, target_length)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)
