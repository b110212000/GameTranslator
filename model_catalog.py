"""Local model inventory and explicit, cancellable downloads (no inference I/O)."""
from dataclasses import dataclass
from pathlib import Path
import fnmatch
import tempfile
import urllib.request
import json
from threading import Event
import argostranslate.package
from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from tqdm import tqdm
from model_storage import configured_directory, model_directory, model_is_complete, install_argos_archive

NLLB_REPO = 'JustFrederik/nllb-200-distilled-600M-ct2-int8'
NLLB_REVISION = '302d78f00e6fdb50a1064059df7c392b735e9d05'
SPEECH_PATTERNS = ('config.json','preprocessor_config.json','model.bin','tokenizer.json','vocabulary.*')


@dataclass(frozen=True)
class ModelSpec:
    key: str
    name: str
    purpose: str
    size: str
    repo: str = ''
    revision: str = 'main'
    pair: tuple = ()
    patterns: tuple = SPEECH_PATTERNS
    required: tuple = ('model.bin','config.json','tokenizer.json','vocabulary.txt')
    license: str = 'MIT'


MODELS = {
    'tiny.en': ModelSpec('tiny.en','英文快速 tiny.en','英文辨識','約 75 MB','Systran/faster-whisper-tiny.en'),
    'base.en': ModelSpec('base.en','英文標準 base.en','英文辨識','約 150 MB','Systran/faster-whisper-base.en'),
    'small': ModelSpec('small','多語輕量 small','中英混合／日文','約 500 MB','Systran/faster-whisper-small'),
    'turbo': ModelSpec('turbo','多語高準確 turbo','中英混合／日文','約 1.6 GB','mobiuslabsgmbh/faster-whisper-large-v3-turbo',
        required=('model.bin','config.json','tokenizer.json','preprocessor_config.json','vocabulary.json')),
    'nllb': ModelSpec('nllb','NLLB 日文直譯','日文→繁中','約 620 MB',NLLB_REPO,NLLB_REVISION,
        patterns=('config.json','model.bin','tokenizer.json','shared_vocabulary.txt','README.md'),
        required=('model.bin','config.json','tokenizer.json','shared_vocabulary.txt'),license='CC BY-NC 4.0（非商用）'),
    'en-zh': ModelSpec('en-zh','Argos 英文翻譯','英文→中文','約 70 MB',pair=('en','zh'),license='依模型套件授權'),
    'ja-en': ModelSpec('ja-en','Argos 日文轉譯','日文→英文','約 60 MB',pair=('ja','en'),license='依模型套件授權'),
}


class DownloadCancelled(Exception): pass


def local_model_path(key):
    spec = MODELS[key]
    path = model_directory()/key
    if model_is_complete(path, spec): return path
    if configured_directory() is not None: return None
    return legacy_model_path(key)


def legacy_model_path(key):
    spec = MODELS[key]
    if spec.pair:
        for package in argostranslate.package.get_installed_packages():
            if (package.from_code,package.to_code) == spec.pair:
                return package.package_path if model_is_complete(package.package_path, spec) else None
        return None
    try:
        # A deliberately filtered snapshot need not contain the repository's
        # README or .gitattributes. Only inference files determine readiness.
        path = Path(snapshot_download(spec.repo, revision=spec.revision,
                    allow_patterns=list(spec.required), local_files_only=True))
        if all((path/file).is_file() and (path/file).stat().st_size > 0 for file in spec.required):
            return path
    except (OSError, ValueError):
        pass
    return None


def inventory():
    return [(spec, local_model_path(key)) for key,spec in MODELS.items()]


def installed_translation_packages():
    return [argostranslate.package.Package(path) for key,spec in MODELS.items()
            if spec.pair and (path := local_model_path(key)) is not None]


def download_model(key, progress=None, cancel=None):
    """Download only catalog-listed files; cancellation never publishes partial models."""
    progress = progress or (lambda percent,message: None)
    cancel = cancel or Event()
    spec = MODELS[key]
    def check():
        if cancel.is_set(): raise DownloadCancelled()
    check()
    path = local_model_path(key)
    if path:
        progress(100,'模型已安裝')
        return path
    destination = model_directory()
    destination.mkdir(parents=True, exist_ok=True)
    if spec.pair:
        progress(0,'取得翻譯模型清單…')
        from argostranslate import settings as argos_settings
        with urllib.request.urlopen(argos_settings.remote_package_index, timeout=15) as response:
            index = json.loads(response.read(10*1024*1024))
        check()
        package = next((p for p in index if (p.get('from_code'),p.get('to_code')) == spec.pair),None)
        if package is None: raise RuntimeError('模型清單沒有這個語言組合')
        url = next(url for url in package['links'] if url.startswith('https://'))
        with tempfile.TemporaryDirectory(prefix='.download-', dir=destination) as scratch:
            archive = Path(scratch)/'model.argosmodel'
            with urllib.request.urlopen(url,timeout=15) as response, archive.open('wb') as file:
                total = int(response.headers.get('Content-Length',0))
                received = 0
                while True:
                    check()
                    block = response.read(256*1024)
                    if not block: break
                    file.write(block)
                    received += len(block)
                    progress(min(95,received*95/total) if total else 0,f'下載 {received/1048576:.1f} MB')
            check()
            progress(96,'安裝模型…')
            install_argos_archive(archive, spec, destination, check)
    else:
        from huggingface_hub import constants
        constants.HF_HUB_DISABLE_XET = True  # HTTP chunk progress supports cancellation.
        progress(0,'取得檔案清單…')
        info = HfApi().model_info(spec.repo,revision=spec.revision,files_metadata=True)
        files = [f for f in info.siblings if any(fnmatch.fnmatch(f.rfilename,p) for p in spec.patterns)]
        total = sum(f.size or 0 for f in files) or 1
        completed = 0
        for file in files:
            check()
            filename = file.rfilename
            class DownloadProgress(tqdm):
                def __init__(self,*args,**kwargs):
                    kwargs['disable'] = True
                    super().__init__(*args,**kwargs)
                    self.received = kwargs.get('initial',0)
                def update(self,n=1):
                    check()
                    self.received += n
                    progress(min(99,(completed+self.received)*100/total),f'下載 {filename}')
                    return super().update(n)
            hf_hub_download(spec.repo,filename,revision=spec.revision,tqdm_class=DownloadProgress,
                            local_dir=str(destination/key))
            completed += file.size or 0
            progress(min(99,completed*100/total),f'完成 {filename}')
    path = local_model_path(key)
    if path is None: raise RuntimeError('模型檔案不完整，請重試下載')
    progress(100,'下載完成，可離線使用')
    return path
