"""Bounded background speech processing; no Tk calls from the worker."""
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import perf_counter
from typing import Callable
import logging
import numpy as np
from audio_pipeline import CaptionResult, RecordedAudioPipeline


class LiveCaptioner:
    def __init__(self, on_caption: Callable[[CaptionResult], None], on_error=None,
                 on_ready=None, max_chunk_seconds=4.0, silence_seconds=0.35,
                 pipeline_factory=RecordedAudioPipeline):
        self.on_caption, self.on_error, self.on_ready = on_caption, on_error, on_ready
        self.max_chunk_seconds, self.silence_seconds = max_chunk_seconds, silence_seconds
        self.pipeline_factory = pipeline_factory
        self.ready = Event()
        self._stop = Event()
        self._blocks = Queue(maxsize=150)
        self._thread = None

    def submit(self, audio, sample_rate):
        if not self.ready.is_set() or self._stop.is_set():
            return
        try:
            self._blocks.put_nowait((audio.copy(), sample_rate, perf_counter()))
        except Full:
            pass

    def start(self):
        if self._thread is None:
            self._thread = Thread(target=self._run, name="live-captioner", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self.ready.clear()

    def _run(self):
        try:
            pipeline = self.pipeline_factory()
            pipeline.warm_up()
            if self._stop.is_set():
                return
            self.ready.set()
            if self.on_ready:
                self.on_ready()
            buffered, total, speech, silence = [], 0, 0, 0
            while not self._stop.is_set():
                try:
                    block, rate, captured_at = self._blocks.get(timeout=0.1)
                except Empty:
                    continue
                if perf_counter() - captured_at > 3:
                    buffered, total, speech, silence = [], 0, 0, 0
                    continue
                voiced = float(np.sqrt(np.mean(np.square(block)))) >= 0.002
                if voiced or buffered:
                    buffered.append(block)
                    total += len(block)
                    if voiced:
                        speech += len(block)
                        silence = 0
                    else:
                        silence += len(block)
                if not buffered:
                    continue
                if silence < rate * self.silence_seconds and total < rate * self.max_chunk_seconds:
                    continue
                chunk = np.concatenate(buffered)
                enough_speech = speech >= rate * 0.15
                buffered, total, speech, silence = [], 0, 0, 0
                if enough_speech:
                    for caption in pipeline.process_audio(chunk, rate):
                        if not self._stop.is_set():
                            self.on_caption(caption)
        except Exception as error:
            logging.exception("Caption worker failed")
            if self.on_error and not self._stop.is_set():
                self.on_error(error)
        finally:
            self.ready.clear()
