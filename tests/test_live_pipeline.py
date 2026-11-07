import unittest
from dataclasses import replace
from threading import Event
from unittest.mock import patch
import numpy as np
from captions import CaptionStore, CaptionUpdate
from live_captioner import LiveCaptioner


class PipelineTests(unittest.TestCase):
    def test_japanese_gpu_load_failure_falls_back_to_small_cpu_model(self):
        from audio_pipeline import RecordedAudioPipeline
        with patch('audio_pipeline.cuda_available', return_value=True), \
             patch('audio_pipeline.LocalTraditionalChineseTranslator'), \
             patch('audio_pipeline.WhisperModel', side_effect=[RuntimeError('GPU unavailable'), object()]) as load:
            with self.assertLogs(level='WARNING'):
                pipeline = RecordedAudioPipeline(language='ja')
        self.assertEqual(pipeline.device, 'cpu')
        self.assertEqual(pipeline.model_name, 'small')
        self.assertEqual(load.call_args_list[0].args[0], 'turbo')
        self.assertEqual(load.call_args_list[1].kwargs['device'], 'cpu')

    def test_original_preview_is_published_before_speech_ends(self):
        preview, translated, finalized = Event(), Event(), Event()
        updates = []
        class FakePipeline:
            def warm_up(self): pass
            def recognize_audio(self, audio, rate): return [('途中の日本語',len(audio)/rate)]
            def translate(self, text): translated.set(); return '中文'
        def receive(update):
            updates.append(update)
            if update.state == 'partial': preview.set()
            if update.is_final: finalized.set()
        engine = LiveCaptioner(receive, language='ja', partial_seconds=1.0, pipeline_factory=FakePipeline)
        try:
            engine.start()
            self.assertTrue(engine.ready.wait(3))
            engine.submit(np.ones(16000,dtype=np.float32)*0.1,16000)
            self.assertTrue(preview.wait(3))
            self.assertTrue(translated.wait(3))
            self.assertEqual(updates[0].state, 'partial')
            self.assertFalse(updates[0].traditional_chinese_text)
            engine.submit(np.zeros(4800,dtype=np.float32),16000)
            self.assertTrue(finalized.wait(3))
            source_updates = [r for r in updates if r.state in ('partial','recognized')]
            self.assertEqual([r.segment_id for r in source_updates], [1,1])
            self.assertLess(source_updates[0].revision,source_updates[1].revision)
        finally:
            engine.stop()

    def test_late_translation_updates_matching_row_without_reordering(self):
        store = CaptionStore(limit=2)
        first = CaptionUpdate(1, 1, "First", state="recognized")
        second = CaptionUpdate(2, 1, "Second", state="recognized")
        store.apply(first)
        store.apply(second)
        self.assertTrue(store.apply(replace(first, traditional_chinese_text="第一", state="translated")))
        self.assertEqual(list(store.rows), [1, 2])
        self.assertEqual(store.rows[2].source_text, "Second")
        store.apply(CaptionUpdate(3, 1, "Third"))
        self.assertFalse(store.apply(replace(first, state="translated")))
        self.assertEqual(list(store.rows), [2, 3])

    def test_old_revision_cannot_replace_new_source(self):
        store = CaptionStore()
        store.apply(CaptionUpdate(1, 1, "Turn"))
        store.apply(CaptionUpdate(1, 2, "Turn left", state="recognized"))
        self.assertFalse(store.apply(CaptionUpdate(1, 1, "Turn", "轉", "translated")))
        self.assertEqual(store.rows[1].source_text, "Turn left")
        self.assertTrue(store.apply(CaptionUpdate(1, 3, state="skipped")))
        self.assertEqual(store.rows[1].source_text, "Turn left")

    def test_slow_translation_does_not_block_next_source_and_stop_cancels_results(self):
        translating, release, second_source, source = Event(), Event(), Event(), Event()
        updates = []
        class FakePipeline:
            calls = 0
            def warm_up(self): pass
            def recognize_audio(self, audio, rate):
                self.calls += 1
                return [(f"Sentence {self.calls}", 0.3)]
            def translate(self, text):
                translating.set()
                release.wait(5)
                return "中文"
        def received(update):
            updates.append(update)
            if update.state == "recognized":
                source.set()
                if update.segment_id == 2:
                    second_source.set()
        engine = LiveCaptioner(received, pipeline_factory=FakePipeline)
        try:
            engine.start()
            self.assertTrue(engine.ready.wait(3))
            for _ in range(2):
                engine.submit(np.ones(4800, dtype=np.float32)*0.1,16000)
                engine.submit(np.zeros(4800,dtype=np.float32),16000)
            self.assertTrue(translating.wait(3))
            self.assertTrue(source.is_set())
            self.assertTrue(second_source.wait(3), 'Translation must not block recognition')
            self.assertTrue(all(x.state != 'translated' for x in updates))
            engine.stop()
            count = len(updates)
            release.set()
            for worker in engine._workers:
                worker.join(timeout=2)
            self.assertEqual(len(updates), count)
        finally:
            engine.stop()
            release.set()

    def test_model_startup_error_reaches_ui(self):
        failed, errors = Event(), []
        def broken(): raise RuntimeError('Missing model')
        def report(error): errors.append(str(error)); failed.set()
        engine = LiveCaptioner(lambda row: None, on_error=report, pipeline_factory=broken)
        engine.start()
        self.assertTrue(failed.wait(3))
        self.assertEqual(errors, ['Missing model'])
        self.assertFalse(engine.ready.is_set())


if __name__ == '__main__':
    unittest.main()
