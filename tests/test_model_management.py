import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch, Mock
import numpy as np
import audio_devices
from model_catalog import DownloadCancelled,download_model,local_model_path


class ModelTests(unittest.TestCase):
    def test_audio_selection_preserves_model_preferences(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(audio_devices,'SETTINGS_PATH',Path(directory)/'settings.json'):
            audio_devices.update_settings(translation='direct',speech_ja='small',device='cpu')
            audio_devices.save_settings(audio_devices.AudioDevice(1,'Cable','API'),audio_devices.AudioDevice(2,'Headphones','API'),'ja')
            saved=audio_devices.read_settings()
            self.assertEqual(saved['translation'],'direct')
            self.assertEqual(saved['device'],'cpu')
            self.assertEqual(saved['capture']['name'],'Cable')

    def test_cancel_before_download_does_not_access_network(self):
        cancel=Event();cancel.set()
        with patch('model_catalog.HfApi') as api:
            with self.assertRaises(DownloadCancelled): download_model('nllb',cancel=cancel)
            api.assert_not_called()

    def test_cached_model_does_not_access_network(self):
        with patch('model_catalog.local_model_path',return_value=Path('cached')),patch('model_catalog.HfApi') as api:
            self.assertEqual(download_model('nllb'),Path('cached'))
            api.assert_not_called()

    def test_incomplete_snapshot_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory,patch('model_catalog.snapshot_download',return_value=directory):
            (Path(directory)/'config.json').write_text('{}')
            self.assertIsNone(local_model_path('nllb'))

    def test_gpu_runtime_failure_retries_current_audio_on_cpu(self):
        from audio_pipeline import RecordedAudioPipeline
        pipeline=RecordedAudioPipeline.__new__(RecordedAudioPipeline)
        pipeline.device='cuda';pipeline.auto_model=True;pipeline.language='ja';pipeline.model_name='turbo';pipeline.fallbacks=0
        model=Mock()
        result=Mock(text='駅はどこですか',end=1.0)
        model.transcribe.return_value=(iter([result]),None)
        pipeline.model=Mock()
        pipeline.model.transcribe.side_effect=RuntimeError('CUDA out of memory')
        pipeline._load_model=Mock(return_value=model)
        with self.assertLogs(level='WARNING'):
            rows=pipeline.recognize_audio(np.zeros(16000,dtype=np.float32),16000)
        self.assertEqual(rows,[('駅はどこですか',1.0)])
        self.assertEqual(pipeline.device,'cpu')
        self.assertEqual(pipeline.model_name,'small')
        self.assertEqual(pipeline.fallbacks,1)


if __name__=='__main__': unittest.main()
