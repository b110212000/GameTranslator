"""Background chunking for live audio; UI code receives completed captions only."""

from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Callable

import numpy as np

from audio_pipeline import CaptionResult, RecordedAudioPipeline


class LiveCaptioner:
    """Groups speech into short chunks, then recognizes them off the audio thread."""

    def __init__(self, on_caption: Callable[[CaptionResult], None], chunk_seconds: float = 1.5) -> None:
        self.on_caption = on_caption
        self.chunk_seconds = chunk_seconds
        self._blocks: Queue[tuple[np.ndarray, int]] = Queue(maxsize=200)
        self._stop = Event()
        self._thread: Thread | None = None

    def submit(self, audio: np.ndarray, sample_rate: int) -> None:
        try:
            self._blocks.put_nowait((audio.copy(), sample_rate))
        except Full:
            pass

    def start(self) -> None:
        if self._thread is None:
            self._thread = Thread(target=self._run, name="live-captioner", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        pipeline = RecordedAudioPipeline()
        buffered: list[np.ndarray] = []
        sample_rate = 0
        while not self._stop.is_set():
            try:
                block, sample_rate = self._blocks.get(timeout=0.1)
            except Empty:
                continue
            # Avoid sending silent chunks to Whisper. The threshold is tuned as
            # a conservative starting point and will be calibrated in final QA.
            if float(np.sqrt(np.mean(np.square(block)))) < 0.008:
                continue
            buffered.append(block)
            frames = sum(len(item) for item in buffered)
            if frames < sample_rate * self.chunk_seconds:
                continue
            chunk = np.concatenate(buffered)
            buffered.clear()
            for caption in pipeline.process_audio(chunk, sample_rate):
                self.on_caption(caption)
