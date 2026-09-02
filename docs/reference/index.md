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
| `🔴` | Recording (push-to-talk) |
| `🎙` | Recording an interview (hands-free, long-form) |
| `✓` | Injected/saved successfully (flashes briefly) |
| `∅` | Transcript came back empty (flashes briefly) |
| `⚠` | Error — permission missing or engine failure. Flashes for transient errors; stays up after a microphone open failure or engine-load failure until a later flow succeeds. The `Status:` menu item shows the reason |

Menu items:

| Item | Behavior |
|---|---|
| `Status: …` | `loading models…` → `ready (Ns load)` / `load failed — <reason>`; shows elapsed time + word count while an interview records. After any error it keeps `<error> — <reason>` until the next successful dictation/speak clears it |
| `Start/Stop interview recording` | Toggles hands-free long-form recording to a saved transcript (no typing into apps); see the [guide](../guide/record-interviews.md) |
| `Voice` | One of 8 Kokoro voices; persisted |
| `Live typing` | Toggles streaming commits; persisted |
| `Mute summaries` | Silences spoken Claude Code summaries (the spool path); ⌃⌥S speak-selection still works. Persisted |
| `Quit` | Stops hotkey listeners and exits |

## Configuration file

`~/.config/codewithvoice/config.json` — written on change, merged over
defaults at startup.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `voice` | string | `"af_heart"` | Kokoro voice for TTS |
| `live_typing` | bool | `true` | Type confirmed words during dictation |
| `mute_summaries` | bool | `false` | Suppress spoken Claude Code summaries (spool path) |

## Models

| Role | Model | Size | Source |
|---|---|---|---|
| ASR | `mlx-community/whisper-small-mlx-q4` | ~500 MB | Hugging Face, downloaded on first run |
| TTS | `hexgrad/Kokoro-82M` | ~330 MB | Hugging Face, downloaded on first run |

Constants: audio is delivered at 16 kHz mono (`recorder.py`), TTS output is
24 kHz (`engine/tts.py`), and recording is uncapped by default
(`recorder.py:MAX_SECONDS = None`; set a float to re-arm an auto-stop timer).

Some USB/conferencing mics (e.g. Anker PowerConf) reject opening at 16 kHz
with CoreAudio error `-10851` and capture silence. `Recorder` detects the
failed open, falls back to the device's native rate (often 48 kHz), and
resamples to 16 kHz on read — so every consumer still sees 16 kHz mono.

Closing the mic stream is bounded at 3 s (`recorder.py:STOP_TIMEOUT_SECONDS`):
PortAudio's stop call can deadlock against the CoreAudio HAL IO thread, which
used to freeze the app at `🔴` on PTT release and kill all hotkeys. If the
close hangs, the stream is abandoned (the log shows
`[recorder] stream stop hung`), the audio captured so far is still transcribed
and typed, and the next dictation opens a fresh stream.

Opening the stream is bounded too, at 5 s (`recorder.py:OPEN_TIMEOUT_SECONDS`):
an abandoned close can keep holding the CoreAudio HAL mutex, and the next open
would block on it forever. A hung open surfaces as a sticky `⚠` with
*"Opening the microphone hung"* in the `Status:` item instead of silently
freezing — quit and relaunch the app to recover the audio system. Hotkeys keep
working throughout: the press handler only flips state and hands the mic open
to a background thread, so a wedged open can no longer freeze the event tap.

## Module map

All app code lives in `src/voicebar/`:

| Module | Responsibility |
|---|---|
| `app.py` | rumps app: menu, state machine, PTT and speak flows |
| `engine/asr.py` | whisper transcription + hallucinated-segment filter |
| `engine/tts.py` | Kokoro synthesis |
| `streaming.py` | `StreamingTranscriber` — LocalAgreement-2 live commits |
| `interview.py` | `InterviewSession` — hands-free long-form recording to a saved `.txt`/`.wav` |
| `recorder.py` | `sounddevice` mic capture, uncapped by default, live `snapshot()` / `drain_new()` |
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
models are loaded. Requests older than 30 s (`spool.py:MAX_AGE_SECONDS`) are
discarded unheard — so a backlog that piled up while the app was closed is
drained silently on launch rather than spoken in a flood, and summaries that
arrive faster than they can be spoken don't queue up. `hooks/speak-summary.py`
is a Claude Code Stop hook that feeds this; see the
[guide](../guide/claude-code-voice.md).

## Interview transcripts

`~/Documents/codewithvoice-interviews/` — each session writes a pair named
`interview_YYYY-MM-DD_HH-MM-SS`:

- `…​.txt` — the transcript, one timestamped line per ~30 s window
  (`[m:ss] text`), appended live as the interview runs.
- `…​.wav` — the raw 16 kHz mono audio, flushed continuously so it survives a
  crash or quit even if transcription is incomplete.

Audio is transcribed in `CHUNK_SECONDS` (30 s) windows rather than one final
pass, so memory stays flat regardless of interview length. Near-silent windows
are skipped to avoid hallucinated text over a candidate's thinking pauses.

## Logs

Running from a source checkout, log lines go to the launching terminal. The
installed **CodeWithVoice.app** instead writes stdout/stderr to
`~/Library/Logs/CodeWithVoice.log` (Finder launches otherwise discard them) —
check it first when diagnosing a `⚠` or a startup failure. The launcher
rotates the file to `CodeWithVoice.log.old` when it exceeds 5 MB, and each
launch appends a `launcher: <timestamp> pid <n> start` marker.

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
