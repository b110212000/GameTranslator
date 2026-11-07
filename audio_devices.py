"""Windows audio endpoint discovery for GameTranslator's routing UI."""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd
import json
from pathlib import Path
import sys

SETTINGS_PATH = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                 else Path(__file__).parent) / "settings.json"


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    host_api: str

    @property
    def label(self) -> str:
        return f"[{self.index}] {self.name} — {self.host_api}"


def list_input_devices() -> list[AudioDevice]:
    return _list_devices("max_input_channels")


def list_output_devices() -> list[AudioDevice]:
    return _list_devices("max_output_channels")


def _list_devices(channel_key: str) -> list[AudioDevice]:
    host_apis = sd.query_hostapis()
    devices: list[AudioDevice] = []
    for index, device in enumerate(sd.query_devices()):
        if device[channel_key] <= 0:
            continue
        devices.append(AudioDevice(index, device["name"], host_apis[device["hostapi"]]["name"]))
    return sorted(devices, key=lambda d: (d.host_api != "Windows WASAPI", d.index))


def read_settings() -> dict:
    try:
        result = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(capture: AudioDevice, playback: AudioDevice) -> None:
    payload = {"capture": {"name": capture.name, "host_api": capture.host_api},
               "playback": {"name": playback.name, "host_api": playback.host_api}}
    temp = SETTINGS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(SETTINGS_PATH)


def choose_device(devices: list[AudioDevice], saved: dict, capture: bool) -> AudioDevice | None:
    if not isinstance(saved, dict):
        saved = {}
    exact = next((d for d in devices if d.name == saved.get("name") and d.host_api == saved.get("host_api")), None)
    if exact:
        return exact
    if capture:
        return next((d for d in devices if "CABLE Output" in d.name), None)
    default_ids = [a["default_output_device"] for a in sd.query_hostapis() if a["name"] == "Windows WASAPI"]
    return next((d for d in devices if d.index in default_ids and "CABLE" not in d.name), None)
