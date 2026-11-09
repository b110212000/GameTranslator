"""Independent segmentation, recognition and translation with bounded queues."""
from collections import OrderedDict
from dataclasses import dataclass, replace
from queue import Empty, Full, Queue
from threading import Condition, Event, Thread, Lock
from time import perf_counter
import logging
import numpy as np
from audio_pipeline import RecordedAudioPipeline
from captions import CaptionUpdate


@dataclass(frozen=True)
class AudioSegment:
    segment_id: int
    revision: int
    audio: np.ndarray
    rate: int
    started_at: float
    speech_end: float
    final: bool


class LiveCaptioner:
    def __init__(self, on_caption, on_error=None, on_ready=None,
                 max_chunk_seconds=None, silence_seconds=0.25,
                 partial_seconds=None, language="en", pipeline_factory=None,
                 model_name=None, translation='auto', device='auto'):
        self.on_caption, self.on_error, self.on_ready = on_caption, on_error, on_ready
        self.max_chunk_seconds = max_chunk_seconds or (6.0 if language in ('ja','mixed') else 2.4)
        self.silence_seconds = silence_seconds
        self.partial_seconds = partial_seconds or (2.4 if language in ('ja','mixed') else 1.0)
        self.pipeline_factory = pipeline_factory or (lambda: RecordedAudioPipeline(
            model_name=model_name,language=language,translation=translation,device=device))
        self.ready, self._stop = Event(), Event()
        self._blocks = Queue(maxsize=200)
        self._translation_pending = OrderedDict()
        self._translation_condition = Condition()
        self._pending = OrderedDict()
        self._condition = Condition()
        self._thread = None
        self._workers = []
        self.backend = ""
        self.translation_route = ''
        self._stats_lock = Lock()
        self._stats = dict(dropped_blocks=0,stale_blocks=0,skipped_segments=0,
            recognized=0,translated=0,translation_errors=0,gpu_fallbacks=0)

    def _count(self,key,amount=1):
        with self._stats_lock: self._stats[key] += amount

    def snapshot(self):
        with self._stats_lock: result=dict(self._stats)
        with self._condition: result['recognition_queue']=len(self._pending)
        with self._translation_condition: result['translation_queue']=len(self._translation_pending)
        result['audio_queue']=self._blocks.qsize()
        result['backend']=self.backend
        return result

    @property
    def is_alive(self):
        return any(t and t.is_alive() for t in [self._thread,*self._workers])

    def submit(self, audio, sample_rate):
        if not self.ready.is_set() or self._stop.is_set():
            return
        try:
            self._blocks.put_nowait((audio.copy(), sample_rate, perf_counter()))
        except Full:
            self._count('dropped_blocks')

    def start(self):
        if self._thread is None:
            self._thread = Thread(target=self._run, name="speech-segmenter", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        self.ready.clear()
        with self._condition:
            self._pending.clear()
            self._condition.notify_all()
        with self._translation_condition:
            self._translation_pending.clear()
            self._translation_condition.notify_all()
        while True:
            try: self._blocks.get_nowait()
            except Empty: break

    def _emit(self, update):
        if not self._stop.is_set():
            self.on_caption(update)

    def _fail(self, error):
        logging.exception("Caption worker failed")
        if self.on_error and not self._stop.is_set():
            self.on_error(error)
        self.stop()

    def _queue_segment(self, job):
        with self._condition:
            # Replace an unprocessed preview with the newest revision/final.
            self._pending[job.segment_id] = job
            while len(self._pending) > 3:
                _, discarded = self._pending.popitem(last=False)
                self._count('skipped_segments')
                self._emit(CaptionUpdate(discarded.segment_id, discarded.revision, state="skipped"))
            self._condition.notify()

    def _run(self):
        pipeline = None
        try:
            pipeline = self.pipeline_factory()
            pipeline.warm_up()
            self.backend = "GPU" if getattr(pipeline, "device", "cpu") == "cuda" else "CPU"
            self.translation_route = getattr(pipeline,'translation_route','本機翻譯')
            if self._stop.is_set():
                return
            for target in (self._recognize, self._translate):
                worker = Thread(target=target, args=(pipeline,), daemon=True)
                self._workers.append(worker)
                worker.start()
            self.ready.set()
            if self.on_ready:
                self.on_ready()
            buffered, total, speech, silence = [], 0, 0, 0
            segment_id, revision, next_partial = 0, 0, self.partial_seconds
            started_at = speech_end = 0.0
            while not self._stop.is_set():
                try:
                    block, rate, captured_at = self._blocks.get(timeout=0.1)
                except Empty:
                    continue
                if perf_counter() - captured_at > 1.0:
                    self._count('stale_blocks')
                    buffered, total, speech, silence = [], 0, 0, 0
                    continue
                voiced = float(np.sqrt(np.mean(np.square(block)))) >= 0.002
                if voiced and not buffered:
                    segment_id += 1
                    revision = 0
                    next_partial = self.partial_seconds
                    started_at = captured_at - len(block) / rate
                if voiced or buffered:
                    buffered.append(block)
                    total += len(block)
                    if voiced:
                        speech += len(block)
                        silence = 0
                        speech_end = captured_at
                    else:
                        silence += len(block)
                if not buffered:
                    continue
                final = silence >= rate * self.silence_seconds or total >= rate * self.max_chunk_seconds
                preview_due = total >= rate * next_partial and silence == 0 and total < rate * (self.max_chunk_seconds - 0.4)
                if speech >= rate * 0.15 and (final or preview_due):
                    revision += 1
                    self._queue_segment(AudioSegment(segment_id, revision, np.concatenate(buffered),
                                                      rate, started_at, speech_end, final))
                    next_partial = total / rate + 1.2
                if final:
                    buffered, total, speech, silence = [], 0, 0, 0
        except Exception as error:
            self._fail(error)

        finally:
            # Stop may arrive while a native inference is still running. Wait
            # here (off the UI thread), then release models while DLLs are alive.
            for worker in self._workers: worker.join()
            close = getattr(pipeline, 'close', None)
            if close:
                try: close()
                except Exception: logging.exception('Model cleanup failed')

    def _recognize(self, pipeline):
        try:
            while not self._stop.is_set():
                with self._condition:
                    self._condition.wait_for(lambda: self._pending or self._stop.is_set(), timeout=0.1)
                    if self._stop.is_set():
                        return
                    if not self._pending:
                        continue
                    _, job = self._pending.popitem(last=False)
                started = perf_counter()
                if started - job.speech_end > 3:
                    self._count('skipped_segments')
                    self._emit(CaptionUpdate(job.segment_id, job.revision, state="skipped"))
                    continue
                source = " ".join(text for text, _end in pipeline.recognize_audio(job.audio, job.rate)).strip()
                now = perf_counter()
                self.backend = 'GPU' if getattr(pipeline,'device','cpu')=='cuda' else 'CPU'
                with self._stats_lock: self._stats['gpu_fallbacks']=getattr(pipeline,'fallbacks',0)
                if now-job.speech_end > 4:
                    self._count('skipped_segments')
                    self._emit(CaptionUpdate(job.segment_id,job.revision,state='skipped',is_final=job.final))
                    continue
                self._count('recognized')
                update = CaptionUpdate(job.segment_id, job.revision, source,
                    state="recognized" if job.final else "partial",
                    recognition_seconds=now-started, since_start_seconds=now-job.started_at,
                    after_speech_seconds=now-job.speech_end, is_final=job.final)
                if not source:
                    if job.final:
                        self._emit(replace(update, state="skipped"))
                    continue
                self._emit(update)  # Publish source before even queueing translation.
                if not self._stop.is_set():
                    with self._translation_condition:
                        self._translation_pending[job.segment_id] = (update, job)
                        while len(self._translation_pending) > 6:
                            _, (old, _) = self._translation_pending.popitem(last=False)
                            self._count('skipped_segments')
                            self._emit(replace(old, state="skipped"))
                        self._translation_condition.notify()
        except Exception as error:
            self._fail(error)

    def _translate(self, pipeline):
        while not self._stop.is_set():
            with self._translation_condition:
                self._translation_condition.wait_for(lambda: self._translation_pending or self._stop.is_set(), timeout=0.1)
                if self._stop.is_set(): return
                if not self._translation_pending: continue
                _, (update, job) = self._translation_pending.popitem(last=False)
            started = perf_counter()
            if started-job.speech_end > 4:
                self._count('skipped_segments')
                self._emit(replace(update,state='skipped'))
                continue
            try:
                chinese = pipeline.translate(update.source_text)
                now = perf_counter()
                if now-job.speech_end > 6:
                    self._count('skipped_segments')
                    self._emit(replace(update,state='skipped'))
                    continue
                self._count('translated')
                self._emit(replace(update, traditional_chinese_text=chinese,
                    state="translated", translation_seconds=now-started,
                    since_start_seconds=now-job.started_at, after_speech_seconds=now-job.speech_end))
            except Exception:
                self._count('translation_errors')
                logging.exception("Translation failed for segment %s", update.segment_id)
                self._emit(replace(update, state="error"))
