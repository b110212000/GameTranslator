"""One explicit location for model downloads, imports and inference."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from audio_devices import read_settings


def configured_directory():
    value = read_settings().get('model_directory')
    return Path(value).expanduser().resolve() if isinstance(value, str) and value.strip() else None


def default_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData'/'Local'))/'GameTranslator'/'models'


def model_directory():
    return configured_directory() or default_directory()


def writable_directory(value):
    value = str(value).strip()
    if not value or not Path(value).expanduser().is_absolute():
        raise ValueError('請選擇完整的模型資料夾路徑。')
    path = Path(value).expanduser().resolve()
    if path == Path(path.anchor):
        raise ValueError('請選擇磁碟中的資料夾，例如 D:\\GameTranslatorModels。')
    path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=path):
        pass
    return path


def model_is_complete(path, spec):
    if spec.pair:
        try:
            metadata = json.loads((path/'metadata.json').read_text(encoding='utf-8-sig'))
            return ((metadata.get('from_code'), metadata.get('to_code')) == spec.pair
                    and (path/'model'/'model.bin').is_file()
                    and (path/'model'/'model.bin').stat().st_size > 0
                    and any((path/name).is_file() for name in ('sentencepiece.model','bpe.model')))
        except (OSError, ValueError, TypeError):
            return False
    return all((path/name).is_file() and (path/name).stat().st_size > 0 for name in spec.required)


def import_model(spec, source, destination, cancel=None):
    """Copy into staging, publish only a complete model, leave the source intact."""
    source, destination = Path(source), Path(destination)
    if not model_is_complete(source, spec):
        raise ValueError('來源資料夾不是這個模型，或模型檔案不完整。')
    target = destination/spec.key
    if model_is_complete(target, spec):
        return target
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-', dir=destination) as scratch:
        staged = Path(scratch)/spec.key
        staged.mkdir()
        for path in source.rglob('*'):
            if cancel: cancel()
            relative = path.relative_to(source)
            if '.cache' in relative.parts: continue
            output = staged/relative
            if path.is_dir(): output.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, output)
        if cancel: cancel()
        if not model_is_complete(staged, spec):
            raise ValueError('匯入後的模型檔案不完整。')
        # Preserve incomplete files instead of overwriting or deleting user data.
        if target.exists():
            backup = destination/(spec.key+'.incomplete-'+Path(scratch).name)
            target.rename(backup)
            try: staged.rename(target)
            except Exception:
                backup.rename(target)
                raise
        else: staged.rename(target)
    return target


def install_argos_archive(archive, spec, destination, cancel=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.unpack-', dir=destination) as scratch:
        root = Path(scratch).resolve()
        with zipfile.ZipFile(archive) as package:
            for item in package.infolist():
                if cancel: cancel()
                output = (root/item.filename).resolve()
                if not output.is_relative_to(root) or ':' in item.filename or '\\' in item.filename:
                    raise ValueError('模型壓縮檔包含無效路徑。')
                if item.is_dir(): output.mkdir(parents=True, exist_ok=True)
                else:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(item) as src, output.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
        candidates = [p.parent for p in root.rglob('metadata.json') if model_is_complete(p.parent, spec)]
        if len(candidates) != 1:
            raise ValueError('下載內容沒有符合語言的完整模型。')
        return import_model(spec, candidates[0], destination, cancel)
