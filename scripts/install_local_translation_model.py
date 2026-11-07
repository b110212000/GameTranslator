"""Install English/Japanese speech and local translation models explicitly."""

from __future__ import annotations

import argostranslate.package
from faster_whisper import WhisperModel
import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--language', choices=('en', 'ja', 'all'), default='all')
    args = parser.parse_args()
    installed = argostranslate.package.get_installed_packages()
    pairs = [('en', 'zh')]
    if args.language in ('ja', 'all'):
        pairs.append(('ja', 'en'))
    missing = [(src, dst) for src, dst in pairs if not any(
        p.from_code == src and p.to_code == dst for p in installed)]
    if missing:
        argostranslate.package.update_package_index()
    for src, dst in missing:
        package = next(
            item
            for item in argostranslate.package.get_available_packages()
            if item.from_code == src and item.to_code == dst
        )
        print(f'Downloading local translation model {src} -> {dst}...', flush=True)
        argostranslate.package.install_from_path(package.download())
        print(f'Installed {src} -> {dst} {package.package_version}', flush=True)
    models = ['base.en'] if args.language == 'en' else ['small', 'turbo'] if args.language == 'ja' else ['base.en', 'small', 'turbo']
    for model in models:
        print(f'Preparing speech model {model}...', flush=True)
        WhisperModel(model, device='cpu', compute_type='int8')
    print('Models are ready. GameTranslator can now run offline.')


if __name__ == "__main__":
    main()
