"""Install the English speech and en→zh translation models for offline use."""

from __future__ import annotations

import argostranslate.package
from faster_whisper import WhisperModel


def main() -> None:
    installed = argostranslate.package.get_installed_packages()
    if any(item.from_code == "en" and item.to_code == "zh" for item in installed):
        print("Local en→zh translation model is already installed.")
    else:
        argostranslate.package.update_package_index()
        package = next(
            item
            for item in argostranslate.package.get_available_packages()
            if item.from_code == "en" and item.to_code == "zh"
        )
        argostranslate.package.install_from_path(package.download())
        print(f"Installed local translation model: {package.from_code}→{package.to_code} {package.package_version}")
    print("Preparing the base.en speech model (downloads only when needed)...")
    WhisperModel("base.en", device="cpu", compute_type="int8")
    print("Both models are ready. GameTranslator can now run offline.")


if __name__ == "__main__":
    main()
