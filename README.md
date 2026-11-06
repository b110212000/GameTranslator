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

This prototype uses local models only: `faster-whisper` with the CPU-friendly
`base.en` model for English speech recognition, then Argos Translate's English
→ Chinese model and OpenCC for Traditional Chinese conversion. Internet access
is needed only once to download each model; later translation has no API key,
quota or network dependency. The pipeline accepts completed WAV files so a
future live-capture task can send audio chunks through the same code.

```powershell
cd D:\GameTranslator
py -m pip install -r requirements.txt
py scripts\install_local_translation_model.py
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

## Audio routing setup (prepared for MVP 4)

The main window now lists capture inputs and headphone outputs without changing
any Windows default device. With VB-Audio Virtual Cable installed, choose
**CABLE Output** as GameTranslator's input, set VALORANT voice-chat output to
**CABLE Input**, then select your headphone/speaker endpoint as the output.
Actual capture, passthrough and VALORANT validation remain deferred until the
final hardware test.

Selecting **開始即時音訊** now opens the selected capture and playback devices:
original audio is copied directly to the chosen headphones while English speech
blocks are processed in a background thread for subtitles. Local models are
preloaded before they receive speech, and live chunks are 0.75 seconds to
reduce caption delay. The overlay shows the English original above its larger
Traditional Chinese translation. This app never speaks a Chinese translation
aloud. Use **停止預覽** to close both streams.

## Build a double-clickable Windows app

```powershell
cd D:\GameTranslator
powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
```

Then double-click `D:\GameTranslator\dist\GameTranslator.exe`. The EXE opens
without a terminal window. Build output is ignored by Git; the local translation
model is installed once for the current Windows user and is reused by the app.
