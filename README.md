# GameTranslator

Windows-based development project for a real-time game voice translation tool.

## First release target

Test with VALORANT: receive teammates' English voice chat, preserve and play the original audio to headphones without waiting for processing, and show an English-to-Traditional-Chinese translation in a transparent subtitle overlay.

The first release covers receiving teammate speech and displaying subtitles only. It does not include a virtual microphone or translating the player's Chinese speech into English.

## Development notes

- Development location: `D:\GameTranslator` on Windows.
- Audio routing, headset playback, subtitle-overlay compatibility, and packaging as an EXE will be tested on this Windows machine.
- Current status: MVP 1 implements a Windows preview control window and a
  separate subtitle overlay. Audio capture and translation are not yet wired in.

## Initial technical direction

Prototype the pipeline with recorded English audio first, then integrate Windows audio and the game. Options under consideration include Python, faster-whisper, and PySide6.

## Run the MVP 1 subtitle preview

No third-party packages are required; the included Python 3.12 Tkinter runtime
is used.

```powershell
cd D:\GameTranslator
py app.py
```

1. The main window opens in **待機** (idle) and identifies itself as **預覽模式**.
2. Select **開始預覽** to display the one-line Traditional Chinese test
   subtitle in a separate transparent, always-on-top window.
3. Select **停止預覽** to hide that overlay and return to **待機**.
4. To preview a different line, edit the subtitle text box and press Enter
   while preview is running.

Future recognizer/translator code can send replacement subtitle text through
`GameTranslatorApp.set_subtitle_text(text)` from the UI event loop. The recorded
demo uses a queue to marshal worker results back to that event loop, so worker
code never accesses Tk widgets directly.

## Run the MVP 3 recorded-audio prototype

This prototype uses `faster-whisper` with the CPU-friendly `base.en` model and
MyMemory through `deep-translator` for English → Traditional Chinese. It needs
Internet access the first time to download the Whisper model and while
translating; no API key is used. The pipeline accepts completed WAV files so a
future live-capture task can send audio chunks through the same code.

```powershell
cd D:\GameTranslator
py -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\generate_sample_audio.ps1
py recorded_demo.py
```

The last command prints one JSON record per caption, including the recognized
English, Traditional Chinese result, and processing latency measured from the
point each completed WAV becomes available. To display results through the
subtitle preview UI instead, run:

```powershell
py recorded_demo.py --preview
```

The generated WAV files are created locally from Windows speech synthesis and
are ignored by Git. Use your own authorized English WAV files by appending their
paths to `recorded_demo.py`.
