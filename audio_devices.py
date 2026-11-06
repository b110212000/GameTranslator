"""Windows audio endpoint discovery for GameTranslator's routing UI."""

from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd


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
    return devices
