"""Hidden checks of the first-run/model-location workflow; never download."""
import json
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
import audio_devices
from model_catalog import MODELS
from model_manager import ModelManager
from version import __version__


def check_setup(report):
    report=Path(report);report.parent.mkdir(parents=True,exist_ok=True)
    result={'version':__version__,'passed':False,'visible_windows':False}
    root=tk.Tk();root.withdraw()
    try:
        with tempfile.TemporaryDirectory(dir=report.parent,prefix='setup-ui-') as scratch:
            folder=Path(scratch)
            with patch.object(audio_devices,'SETTINGS_PATH',folder/'settings.json'):
                audio_devices.update_settings(model_directory=str(folder/'first'))
                busy=[False]
                manager=ModelManager(root,audio_devices.read_settings(),lambda values:audio_devices.update_settings(**values),is_busy=lambda:busy[0],first_run=True)
                manager.window.withdraw();root.update_idletasks()
                result['requested_size']=[manager.window.winfo_reqwidth(),manager.window.winfo_reqheight()]
                assert not manager.window.winfo_ismapped() and not root.winfo_ismapped()
                manager.folder.set(str(folder/'chosen 模型'))
                busy[0]=True;assert not manager.apply_directory()
                assert audio_devices.read_settings()['model_directory']==str(folder/'first')
                busy[0]=False;assert manager.apply_directory()
                target=folder/'chosen 模型'
                assert audio_devices.read_settings()['model_directory']==str(target)
                for key in ('base.en','small','en-zh','ja-en'):
                    model=target/key;model.mkdir()
                    spec=MODELS[key]
                    if spec.pair:
                        (model/'model').mkdir();(model/'model'/'model.bin').write_bytes(b'fixture')
                        (model/'sentencepiece.model').write_bytes(b'fixture')
                        (model/'metadata.json').write_text(json.dumps(dict(zip(('from_code','to_code'),spec.pair))))
                    else:
                        for name in spec.required:(model/name).write_bytes(b'fixture')
                with patch.object(manager,'run_downloads') as start:
                    manager.download_recommended()
                    assert start.call_args.args[0]==('base.en','small','en-zh','ja-en')
                manager.finish_setup()
                assert manager.closed and audio_devices.read_settings()['setup_completed']
                result['checks']=['folder save','live-session directory guard','profile download list','completion gating','setup state persistence']
                result['passed']=True
    finally:
        root.destroy()
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
