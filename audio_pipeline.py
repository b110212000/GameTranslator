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

import argostranslate.package
import ctranslate2
from faster_whisper import WhisperModel
import numpy as np
from opencc import OpenCC


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
        # Installation downloads models explicitly; live translation only reads
        # the local cache. int8 keeps the Windows CPU footprint small.
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True)
        self.translator = LocalTraditionalChineseTranslator()

    def warm_up(self) -> None:
        self.translator.translate("Ready.")
        segments, _ = self.model.transcribe(np.zeros(16000, dtype=np.float32), language="en")
        list(segments)

    def process_wav(self, wav_path: Path) -> list[CaptionResult]:
        """Recognize one completed WAV and translate each non-empty segment."""
        audio = load_pcm_wav_as_16khz_mono(wav_path)
        return self.process_audio(audio, 16000, str(wav_path))

    def process_audio(self, audio: np.ndarray, sample_rate: int, source: str = "live") -> list[CaptionResult]:
        """Process a completed live audio chunk using the same caption pipeline."""
        started_at = perf_counter()
        audio = resample_to_16khz_mono(audio, sample_rate)
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
                    source_file=source,
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


def resample_to_16khz_mono(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate == 16000:
        return audio.astype(np.float32, copy=False)
    source_positions = np.arange(len(audio), dtype=np.float64)
    target_length = round(len(audio) * 16000 / sample_rate)
    target_positions = np.linspace(0, len(audio) - 1, target_length)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


class LocalTraditionalChineseTranslator:
    """Offline Argos English→Chinese translation with Traditional conversion."""

    def __init__(self) -> None:
        self.package = next((p for p in argostranslate.package.get_installed_packages()
                             if p.from_code == "en" and p.to_code == "zh"), None)
        if self.package is None:
            raise RuntimeError(
                "The local en→zh translation model is missing. Run "
                "py scripts\\install_local_translation_model.py once while online."
            )
        self.translation = ctranslate2.Translator(str(self.package.package_path / "model"),
                                                  device="cpu", compute_type="int8", intra_threads=4)
        self.to_traditional = OpenCC("s2twp")

    def translate(self, english_text: str) -> str:
        # Whisper already emits short sentence-like segments. Direct inference
        # avoids Stanza's implicit resource download during sentence splitting.
        if not english_text.strip():
            return ""
        prefix = self.package.target_prefix
        output = self.translation.translate_batch(
            [self.package.tokenizer.encode(english_text)],
            target_prefix=[[prefix]] if prefix else None,
            beam_size=4, replace_unknowns=True, length_penalty=0.2,
        )[0]
        translated = self.package.tokenizer.decode(output.hypotheses[0])
        if prefix and translated.startswith(prefix):
            translated = translated[len(prefix):]
        return self.to_traditional.convert(translated.strip())
