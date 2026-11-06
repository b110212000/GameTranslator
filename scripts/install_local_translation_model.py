"""Download and install Argos' en→zh model once for offline translation."""

from __future__ import annotations

import argostranslate.package
import argostranslate.translate


def main() -> None:
    installed = argostranslate.translate.get_installed_languages()
    english = next((language for language in installed if language.code == "en"), None)
    chinese = next((language for language in installed if language.code == "zh"), None)
    if english is not None and chinese is not None and english.get_translation(chinese) is not None:
        print("Local en→zh translation model is already installed.")
        return

    argostranslate.package.update_package_index()
    package = next(
        item
        for item in argostranslate.package.get_available_packages()
        if item.from_code == "en" and item.to_code == "zh"
    )
    argostranslate.package.install_from_path(package.download())
    print(f"Installed local translation model: {package.from_code}→{package.to_code} {package.package_version}")


if __name__ == "__main__":
    main()
