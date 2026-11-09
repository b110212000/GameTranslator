import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import zipfile

import audio_devices
import model_catalog
from model_storage import import_model, install_argos_archive, model_directory, writable_directory


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.scratch=tempfile.TemporaryDirectory()
        self.root=Path(self.scratch.name)
        self.settings=patch.object(audio_devices,'SETTINGS_PATH',self.root/'settings.json')
        self.settings.start()
        self.models=self.root/'model storage 模型'
        audio_devices.update_settings(model_directory=str(self.models))

    def tearDown(self):
        self.settings.stop();self.scratch.cleanup()

    def speech(self,path,key='small'):
        path.mkdir(parents=True,exist_ok=True)
        for name in model_catalog.MODELS[key].required:(path/name).write_bytes(b'fixture')

    def argos_zip(self,invalid=False):
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as archive:
            archive.writestr('translate-en_zh/metadata.json',json.dumps({'from_code':'en','to_code':'zh'}))
            archive.writestr('translate-en_zh/model/model.bin',b'fixture')
            archive.writestr('translate-en_zh/sentencepiece.model',b'fixture')
            if invalid:archive.writestr('../outside.txt','bad')
        content.seek(0);return content

    def test_explicit_empty_location_does_not_silently_use_old_cache(self):
        with patch('model_catalog.legacy_model_path') as old:
            self.assertIsNone(model_catalog.local_model_path('small'))
            old.assert_not_called()
        self.speech(self.models/'small')
        self.assertEqual(model_catalog.local_model_path('small'),self.models/'small')

    def test_huggingface_download_writes_to_selected_location(self):
        files=[SimpleNamespace(rfilename=name,size=7) for name in model_catalog.MODELS['small'].required]
        def download(repo,filename,**options):
            path=Path(options['local_dir']);path.mkdir(parents=True,exist_ok=True)
            (path/filename).write_bytes(b'fixture')
        with patch('model_catalog.HfApi') as api,patch('model_catalog.hf_hub_download',side_effect=download) as fetch:
            api.return_value.model_info.return_value=SimpleNamespace(siblings=files)
            result=model_catalog.download_model('small')
            self.assertEqual(result,self.models/'small')
            self.assertTrue(all(call.kwargs['local_dir']==str(self.models/'small') for call in fetch.call_args_list))

    def test_argos_download_and_inference_inventory_share_selected_location(self):
        index=io.BytesIO(json.dumps([{'from_code':'en','to_code':'zh','links':['https://example.invalid/model.argosmodel']}]).encode())
        index.headers={}
        archive=self.argos_zip();archive.headers={'Content-Length':str(len(archive.getvalue()))}
        with patch('model_catalog.urllib.request.urlopen',side_effect=[index,archive]):
            result=model_catalog.download_model('en-zh')
        self.assertEqual(result,self.models/'en-zh')
        with patch('model_catalog.argostranslate.package.Package',side_effect=lambda path:path):
            self.assertEqual(model_catalog.installed_translation_packages(),[result])
        self.assertFalse(any(self.models.glob('.download-*')))

    def test_archive_traversal_is_rejected_without_outside_writes(self):
        with self.assertRaises(ValueError):install_argos_archive(self.argos_zip(True),model_catalog.MODELS['en-zh'],self.models)
        self.assertFalse((self.models/'outside.txt').exists())
        self.assertFalse((self.models/'en-zh').exists())

    def test_import_copies_model_and_preserves_source(self):
        source=self.root/'old';self.speech(source)
        result=import_model(model_catalog.MODELS['small'],source,self.models)
        self.assertEqual(result,self.models/'small')
        self.assertTrue((source/'model.bin').exists())
        self.assertEqual(model_catalog.local_model_path('small'),result)

    def test_import_cancel_does_not_publish_partial_model(self):
        source=self.root/'old';self.speech(source)
        def cancel():raise model_catalog.DownloadCancelled()
        with self.assertRaises(model_catalog.DownloadCancelled):import_model(model_catalog.MODELS['small'],source,self.models,cancel)
        self.assertTrue((source/'model.bin').exists())
        self.assertFalse((self.models/'small').exists())

    def test_location_validation_and_settings_preservation(self):
        with self.assertRaises(ValueError):writable_directory('relative/path')
        with self.assertRaises(ValueError):writable_directory('')
        path=writable_directory(self.models)
        audio_devices.update_settings(capture={'name':'Cable'},language='mixed')
        self.assertEqual(model_directory(),path)
        self.assertEqual(audio_devices.read_settings()['capture'],{'name':'Cable'})

    def test_recognizer_loads_resolved_path_not_default_named_cache(self):
        from audio_pipeline import RecordedAudioPipeline
        self.speech(self.models/'small')
        engine=RecordedAudioPipeline.__new__(RecordedAudioPipeline)
        engine.model_name='small';engine.device='cpu'
        with patch('audio_pipeline.WhisperModel') as model:
            engine._load_model()
            self.assertEqual(model.call_args.args[0],str(self.models/'small'))
            self.assertTrue(model.call_args.kwargs['local_files_only'])

    def test_high_accuracy_profile_keeps_automatic_cpu_fallback(self):
        from model_manager import ModelManager, PROFILES
        manager=ModelManager.__new__(ModelManager)
        manager.running=False;manager.apply_directory=Mock(return_value=True)
        manager.profile=Mock();manager.profile.get.return_value=list(PROFILES)[2]
        manager.on_save=Mock();manager.run_downloads=Mock()
        manager.choices={key:(Mock(),{}) for key in ('speech_en','speech_mixed','speech_ja','translation')}
        manager.download_recommended()
        choices=manager.on_save.call_args.args[0]
        self.assertEqual(choices['speech_mixed'],'auto')
        self.assertEqual(choices['speech_ja'],'auto')
        self.assertIn('turbo',manager.run_downloads.call_args.args[0])
        self.assertIn('small',manager.run_downloads.call_args.args[0])
