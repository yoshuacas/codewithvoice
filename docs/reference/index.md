# Reference

## Hotkeys

| Hotkey | Action |
|---|---|
| **Right Option** (hold) | Push-to-talk. Records for as long as it is held (no time limit). With live typing on, confirmed words are typed during the hold; the remainder is typed on release. With live typing off, the full transcript is pasted on release. |
| **⌃⌥S** | Speak the current selection through Kokoro. With no selection, re-speaks the last injected dictation. |

## Menu bar

Title characters:

| Title | State |
|---|---|
| `⏳` | Loading models (startup) or transcribing |
| `●` | Idle, ready |
| `🔴` | Recording |
| `✓` | Injected successfully (flashes briefly) |
| `∅` | Transcript came back empty (flashes briefly) |
| `⚠` | Error — permission missing or engine failure |

Menu items:

| Item | Behavior |
|---|---|
| `Status: …` | `loading models…` → `ready (Ns load)` / `load failed` |
| `Recording method` | `Push-to-talk (Right Option)` — the only method currently |
| `Voice` | One of 8 Kokoro voices; persisted |
| `Live typing` | Toggles streaming commits; persisted |
| `Quit` | Stops hotkey listeners and exits |

## Configuration file

`~/.config/codewithvoice/config.json` — written on change, merged over
defaults at startup.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `voice` | string | `"af_heart"` | Kokoro voice for TTS |
| `live_typing` | bool | `true` | Type confirmed words during dictation |

## Models

| Role | Model | Size | Source |
|---|---|---|---|
| ASR | `mlx-community/whisper-small-mlx-q4` | ~500 MB | Hugging Face, downloaded on first run |
| TTS | `hexgrad/Kokoro-82M` | ~330 MB | Hugging Face, downloaded on first run |

Constants: audio is captured at 16 kHz mono (`recorder.py`), TTS output is
24 kHz (`engine/tts.py`), and recording is uncapped by default
(`recorder.py:MAX_SECONDS = None`; set a float to re-arm an auto-stop timer).

## Module map

All app code lives in `src/voicebar/`:

| Module | Responsibility |
|---|---|
| `app.py` | rumps app: menu, state machine, PTT and speak flows |
| `engine/asr.py` | whisper transcription + hallucinated-segment filter |
| `engine/tts.py` | Kokoro synthesis |
| `streaming.py` | `StreamingTranscriber` — LocalAgreement-2 live commits |
| `recorder.py` | `sounddevice` mic capture, uncapped by default, live `snapshot()` |
| `hotkeys.py` | `pynput` listeners: Right Option PTT, ⌃⌥S |
| `inject.py` | `inject_text()` paste path, `type_text()` keystroke path |
| `selection.py` | `grab_selection()` — synthesized ⌘C with clipboard restore |
| `spool.py` | speak-request spool dir watcher + `submit()` |
| `speech_clean.py` | markdown-to-speech text cleanup |
| `speak_cli.py` | `codewithvoice-speak` command |
| `playback.py` | speaker output |
| `state.py` | config load/save, runtime state |

## Speak spool

`~/.local/state/codewithvoice/speak/` — drop a UTF-8 `.txt` file here and a
running bar app speaks it (write to a dotfile first, then rename, for
atomicity — or just use `codewithvoice-speak`). Watched every 0.5 s once
models are loaded. `hooks/speak-summary.py` is a Claude Code Stop hook that
feeds this; see the [guide](../guide/claude-code-voice.md).

## Commands

```bash
make install   # uv sync (venv + all dependencies)
make run       # run the app in the foreground
make smoke     # in-process ASR + TTS engine test, no desktop session needed
make espeak    # brew install espeak-ng
make docs      # serve this documentation site locally
```

Installed commands (`uv run …` from the repo, or on PATH in the venv):

```bash
codewithvoice                 # the menu-bar app (same as make run)
codewithvoice-speak "text"    # queue text for the running app to speak
echo "text" | codewithvoice-speak   # …or from stdin
```
