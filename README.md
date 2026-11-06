# GameTranslator

Windows-based development project for a real-time game voice translation tool.

## First release target

Test with VALORANT: receive teammates' English voice chat, preserve and play the original audio to headphones without waiting for processing, and show an English-to-Traditional-Chinese translation in a transparent subtitle overlay.

The first release covers receiving teammate speech and displaying subtitles only. It does not include a virtual microphone or translating the player's Chinese speech into English.

## Development notes

- Development location: `D:\GameTranslator` on Windows.
- Audio routing, headset playback, subtitle-overlay compatibility, and packaging as an EXE will be tested on this Windows machine.
- Current status: planning only; implementation has not started.

## Initial technical direction

Prototype the pipeline with recorded English audio first, then integrate Windows audio and the game. Options under consideration include Python, faster-whisper, and PySide6.
