import unittest
from threading import Event
from unittest.mock import Mock
import numpy as np
from mixed_translation import MixedChineseEnglishTranslator
from live_captioner import LiveCaptioner


class MixedTests(unittest.TestCase):
    def test_chinese_never_reaches_english_translator(self):
        english=Mock()
        mixed=MixedChineseEnglishTranslator(english)
        self.assertEqual(mixed.translate('请等一下，我们从右边过去。'), '請等一下，我們從右邊過去。')
        english.translate.assert_not_called()

    def test_only_english_spans_are_translated(self):
        english=Mock()
        english.translate.return_value='請等一下'
        mixed=MixedChineseEnglishTranslator(english)
        self.assertEqual(mixed.translate('我先去 B 點，please wait，我馬上回來。'),
                         '我先去 B 點，請等一下，我馬上回來。')
        english.translate.assert_called_once_with('please wait')

    def test_english_only_uses_whole_sentence(self):
        english=Mock()
        english.translate.return_value='注意右邊。'
        self.assertEqual(MixedChineseEnglishTranslator(english).translate('Watch the right side.'),'注意右邊。')
        english.translate.assert_called_once_with('Watch the right side.')

    def test_mixed_recognizer_does_not_force_english(self):
        from audio_pipeline import RecordedAudioPipeline
        pipeline=RecordedAudioPipeline.__new__(RecordedAudioPipeline)
        pipeline.language='mixed'
        pipeline.model=Mock()
        pipeline.model.transcribe.return_value=([Mock(text='請等一下',end=1.0)],None)
        self.assertEqual(pipeline._recognize(np.zeros(16000,dtype=np.float32)),[('請等一下',1.0)])
        self.assertIsNone(pipeline.model.transcribe.call_args.kwargs['language'])

    def test_stop_waits_for_translation_before_releasing_models(self):
        translating,release,closed=Event(),Event(),Event()
        class Pipeline:
            def warm_up(self): pass
            def recognize_audio(self,audio,rate): return [('Hello',0.3)]
            def translate(self,text):
                translating.set();release.wait(3);return '你好'
            def close(self): closed.set()
        engine=LiveCaptioner(lambda _:None,pipeline_factory=Pipeline)
        try:
            engine.start();self.assertTrue(engine.ready.wait(2))
            engine.submit(np.ones(4800,dtype=np.float32)*0.1,16000)
            engine.submit(np.zeros(4800,dtype=np.float32),16000)
            self.assertTrue(translating.wait(2))
            engine.stop();self.assertFalse(closed.is_set())
            release.set();engine._thread.join(timeout=3)
            self.assertTrue(closed.is_set());self.assertFalse(engine.is_alive)
        finally:
            release.set();engine.stop()


if __name__=='__main__': unittest.main()
