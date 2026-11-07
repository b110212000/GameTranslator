"""Local English/Japanese recognition and Traditional Chinese translation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable
import wave
import logging

import argostranslate.package
import ctranslate2
from faster_whisper import WhisperModel
import numpy as np
from opencc import OpenCC
from gpu_runtime import cuda_available


@dataclass(frozen=True)
class CaptionResult:
    source_file: str
    source_text: str
    traditional_chinese_text: str
    segment_end_seconds: float
    processing_latency_seconds: float
    source_language: str = "en"

    @property
    def english_text(self) -> str:
        """Compatibility for older recorded-demo callers."""
        return self.source_text

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RecordedAudioPipeline:
    """Separate recognition and translation entry points for worker threads."""

    def __init__(self, model_name: str | None = None, language: str = "en") -> None:
        if language not in ("en", "ja"):
            raise ValueError("Unsupported source language")
        self.language = language
        self.auto_model = model_name is None
        # Installation downloads models explicitly; live translation only reads
        # the local cache. int8 keeps the Windows CPU footprint small.
        self.device = "cuda" if cuda_available() else "cpu"
        self.model_name = model_name or ("base.en" if language == "en" else "turbo" if self.device == "cuda" else "small")
        try:
            self.model = self._load_model()
        except RuntimeError:
            if self.device != "cuda": raise
            logging.warning("GPU model loading failed; using CPU", exc_info=True)
            self.device = "cpu"
            if self.auto_model and self.language == "ja": self.model_name = "small"
            self.model = self._load_model()
        self.translator = LocalTraditionalChineseTranslator(language)

    def _load_model(self):
        return WhisperModel(self.model_name, device=self.device,
                            compute_type="int8_float16" if self.device == "cuda" else "int8",
                            cpu_threads=4, local_files_only=True)

    def warm_up(self) -> None:
        self.translator.translate("Ready." if self.language == "en" else "準備ができました。")
        try:
            self._warm_recognition()
        except RuntimeError:
            if self.device != "cuda": raise
            logging.warning("GPU warmup failed; using CPU", exc_info=True)
            self.device = "cpu"
            if self.auto_model and self.language == "ja": self.model_name = "small"
            self.model = self._load_model()
            self._warm_recognition()

    def _warm_recognition(self):
        segments, _ = self.model.transcribe(np.zeros(16000, dtype=np.float32), language=self.language,
                                            beam_size=1, temperature=0.0)
        list(segments)

    def recognize_audio(self, audio: np.ndarray, sample_rate: int) -> list[tuple[str, float]]:
        """Return original text without waiting for translation."""
        audio = resample_to_16khz_mono(audio, sample_rate)
        segments, _ = self.model.transcribe(
            audio, language=self.language, beam_size=3 if self.language == "ja" else 1, best_of=1,
            temperature=0.0, condition_on_previous_text=False, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 200, "speech_pad_ms": 150},
        )
        return [(s.text.strip(), s.end) for s in segments if s.text.strip()]

    def translate(self, source_text: str) -> str:
        return self.translator.translate(source_text)

    def process_wav(self, wav_path: Path) -> list[CaptionResult]:
        """Recognize one completed WAV and translate each non-empty segment."""
        audio = load_pcm_wav_as_16khz_mono(wav_path)
        return self.process_audio(audio, 16000, str(wav_path))

    def process_audio(self, audio: np.ndarray, sample_rate: int, source: str = "live") -> list[CaptionResult]:
        """Process a completed live audio chunk using the same caption pipeline."""
        started_at = perf_counter()
        results: list[CaptionResult] = []
        for original, end in self.recognize_audio(audio, sample_rate):
            translated = self.translate(original)
            results.append(
                CaptionResult(
                    source_file=source,
                    source_text=original,
                    traditional_chinese_text=translated,
                    segment_end_seconds=round(end, 3),
                    # For this recorded-audio prototype, processing starts
                    # immediately after a completed WAV chunk is available.
                    processing_latency_seconds=round(perf_counter() - started_at, 3),
                    source_language=self.language,
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
    """Local direct translation, or Japanese→English→Chinese when needed."""

    def __init__(self, language: str = "en") -> None:
        installed = {(p.from_code, p.to_code): p for p in argostranslate.package.get_installed_packages()}
        pairs = [(language, "zh")] if language == "en" or (language, "zh") in installed else [(language, "en"), ("en", "zh")]
        self.steps = []
        for pair in pairs:
            package = installed.get(pair)
            if package is None:
                raise RuntimeError(f"缺少本機翻譯模型 {pair[0]}→{pair[1]}，請執行 scripts\\install_local_translation_model.py")
            translator = ctranslate2.Translator(str(package.package_path / "model"),
                                                device="cpu", compute_type="int8", intra_threads=2)
            self.steps.append((package, translator))
        self.to_traditional = OpenCC("s2twp")

    def translate(self, source_text: str) -> str:
        # Whisper already emits short sentence-like segments. Direct inference
        # avoids Stanza's implicit resource download during sentence splitting.
        if not source_text.strip():
            return ""
        translated = source_text
        for package, translator in self.steps:
            prefix = package.target_prefix
            output = translator.translate_batch(
                [package.tokenizer.encode(translated)],
                target_prefix=[[prefix]] if prefix else None,
                beam_size=2, replace_unknowns=True, length_penalty=0.2,
            )[0]
            translated = package.tokenizer.decode(output.hypotheses[0]).strip()
            if prefix and translated.startswith(prefix):
                translated = translated[len(prefix):]
        return self.to_traditional.convert(translated.strip())
