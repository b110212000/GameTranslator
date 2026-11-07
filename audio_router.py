"""Low-latency capture and original-audio passthrough for Windows endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import Callable

import numpy as np
import sounddevice as sd


AudioBlockHandler = Callable[[np.ndarray, int], None]


@dataclass(frozen=True)
class AudioRoute:
    capture_device: int
    playback_device: int
    sample_rate: int = 48000
    channels: int = 2
    block_size: int = 960  # 20 ms at 48 kHz


class AudioRouter:
    """Copies capture audio to headphones immediately and exposes its blocks.

    Playback is independent of subtitle processing: a slow recognizer cannot
    stall the output callback or delay teammates' original speech.
    """

    def __init__(self, route: AudioRoute, on_audio: AudioBlockHandler | None = None) -> None:
        self.route = route
        self.on_audio = on_audio
        self._playback_blocks: Queue[np.ndarray] = Queue(maxsize=10)
        self.level = 0.0
        self.captured_frames = 0
        self.played_frames = 0
        self._input_stream: sd.InputStream | None = None
        self._output_stream: sd.OutputStream | None = None

    @property
    def is_running(self) -> bool:
        return self._input_stream is not None and self._input_stream.active

    def start(self) -> None:
        if self.is_running:
            return
        stream_args = dict(
            samplerate=self.route.sample_rate,
            channels=self.route.channels,
            blocksize=self.route.block_size,
            dtype="float32",
            latency="low",
        )
        capture = sd.query_devices(self.route.capture_device)
        playback = sd.query_devices(self.route.playback_device)
        if "CABLE Input" in playback["name"]:
            raise ValueError("耳機輸出不可選 CABLE Input，否則會形成音訊迴路。")
        self._capture_channels = min(2, capture["max_input_channels"])
        self._playback_channels = min(2, playback["max_output_channels"])
        try:
            stream_args["channels"] = self._playback_channels
            self._output_stream = sd.OutputStream(device=self.route.playback_device,
                callback=self._playback_callback, **stream_args)
            stream_args["channels"] = self._capture_channels
            self._input_stream = sd.InputStream(device=self.route.capture_device,
                callback=self._capture_callback, **stream_args)
            self._output_stream.start()
            self._input_stream.start()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        for stream in (self._input_stream, self._output_stream):
            if stream is not None:
                try:
                    stream.abort()
                finally:
                    stream.close()
        self._input_stream = None
        self._output_stream = None
        self._drain_playback_queue()

    def _capture_callback(self, indata: np.ndarray, _frames: int, _time: object, _status: sd.CallbackFlags) -> None:
        block = indata.copy()
        self.level = float(np.sqrt(np.mean(np.square(block))))
        self.captured_frames += len(block)
        try:
            self._playback_blocks.put_nowait(block)
        except Full:
            # Prefer fresh audio over increasing delay if output momentarily stalls.
            try:
                self._playback_blocks.get_nowait()
                self._playback_blocks.put_nowait(block)
            except (Empty, Full):
                pass
        if self.on_audio is not None:
            self.on_audio(block, self.route.sample_rate)

    def _playback_callback(self, outdata: np.ndarray, _frames: int, _time: object, _status: sd.CallbackFlags) -> None:
        try:
            block = self._playback_blocks.get_nowait()
            if block.shape[1] > outdata.shape[1]:
                block = block.mean(axis=1, keepdims=True)
            outdata[:] = block
            self.played_frames += len(block)
        except Empty:
            outdata.fill(0)

    def _drain_playback_queue(self) -> None:
        while True:
            try:
                self._playback_blocks.get_nowait()
            except Empty:
                return
