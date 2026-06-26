# codewithvoice — Agent Guide

> **Meta note**: This is the canonical agent knowledge base for this repo.
> `CLAUDE.md` is a symlink to this file — always edit `AGENTS.md` directly.
> When you learn something durable about the codebase, update this file.

## Repository scope

- **What this is**: a single-process macOS menu-bar dictation app (mlx-whisper ASR + Kokoro TTS).
- **What this is not**: a client/server system. A FastAPI daemon existed and was deliberately deleted (2026-05-18) — do NOT reintroduce a daemon, HTTP API, or LaunchAgent. A Gemma-4 demo suite also lived here and was removed (2026-06-11); Gemma is not a dependency.
- **Primary language**: Python 3.12. **Package manager**: `uv`.
- **Platform**: macOS / Apple Silicon only (pyobjc, rumps, MLX).

## Layout

```text
src/voicebar/
├── app.py        — rumps app, menu, PTT + speak flows
├── engine/       — asr.py (whisper + hallucination filter), tts.py (Kokoro)
├── streaming.py  — StreamingTranscriber: LocalAgreement-2 live typing
├── interview.py  — InterviewSession: hands-free long-form recording → saved .txt/.wav
├── recorder.py   — mic capture (16 kHz mono, uncapped by default, snapshot()/drain_new())
├── hotkeys.py    — pynput: Right Option PTT, ⌃⌥S speak
├── inject.py     — inject_text() paste path, type_text() keystroke path
├── selection.py  — synthesized ⌘C with clipboard snapshot/restore
├── spool.py      — speak-request spool (~/.local/state/codewithvoice/speak/)
├── speech_clean.py — markdown→speech text cleanup
├── speak_cli.py  — codewithvoice-speak entry point
└── state.py      — config (~/.config/codewithvoice/config.json)
hooks/speak-summary.py — Claude Code Stop hook (stdlib-only; summarizes via `claude -p`)
docs/             — MkDocs Material site, deployed by .github/workflows/docs.yml
```

## Canonical commands

```bash
make install   # uv sync
make run       # run the app (menu bar shows ⏳ then ●)
make smoke     # in-process ASR + TTS engine test (no desktop session needed)
make docs      # serve the docs site locally
```

There is no test suite or linter configured (`uvx ruff check src/` passes; keep
it that way). Verify changes with `make smoke`; for `streaming.py` changes,
drive `StreamingTranscriber` with a fake recorder whose `snapshot()` returns a
growing slice of decoded sample audio.

## Rules

- **NEVER** retract typed text in the live-typing path — committed words are final by design; fix commit *quality* (holdback, agreement, run guard), not output.
- **NEVER** trust LocalAgreement alone to reject whisper hallucinations — silence loops ("cooling cooling…") are self-consistent across passes. Keep all three guards: segment filter in `engine/asr.py`, `MAX_WORD_RUN` in `streaming.py`, RMS silence skip in the worker loop.
- **ALWAYS** hold `app.py`'s `_engine_lock` around any whisper/Kokoro call; the engines are not concurrency-safe under MPS/MLX.
- **ALWAYS** mutate the menu-bar UI on the main thread via `AppHelper.callAfter` (see `_set_title`).
- **ALWAYS** update the matching page under `docs/` (reference for behavior, guides for workflows) in the same change as a user-visible code change.
- Recording is **uncapped by default** (`recorder.py:MAX_SECONDS = None`): it records until PTT release. Each live streaming pass re-transcribes from sample 0, so on long clips live typing updates less often (the final full-clip pass stays accurate). If you re-introduce a cap or want snappy live typing on long clips, window the streaming buffer rather than just trimming capture.
- Interview recording (`interview.py`) is a **separate flow from PTT**: hands-free, types nothing, and streams a `.txt`/`.wav` pair to `~/Documents/codewithvoice-interviews/`. It owns the mic exclusively (PTT/speak are gated off while active) and uses `recorder.drain_new()` for flat-memory chunked capture — never `snapshot()`/`stop()`, which keep cumulative frames. Keep both the `.txt` and `.wav` flushed per chunk so a crash/quit loses nothing; `_on_quit` must `stop()` an active session to close the `.wav`.
- **DO NOT** add a daemon/socket for external speak requests — the file spool (`spool.py`) is the supported IPC; keep `hooks/speak-summary.py` stdlib-only (it must run outside this venv) and keep spool writes atomic (tmp file, then rename).
- **DO NOT** add models that won't fit comfortably in RAM next to normal apps; a 10 GB Gemma-as-ASR experiment thrashed 32 GB into 44 GB of swap. Memory-pressure check: if the process RSS ≪ VSZ, the model is paged out — free RAM, don't tune inference.
- `Recorder.samplerate` is the **output** rate (16 kHz). Some mics (Anker PowerConf and other USB/conferencing devices) reject opening at 16 kHz with CoreAudio `-10851` and silently capture nothing; `start()` falls back to the device's native rate and `_to_output()` resamples on read. Keep all read paths (`stop`/`snapshot`/`drain_new`) routed through `_to_output` — don't reintroduce a raw `samplerate` open as the only attempt.
- pyobjc packages in `pyproject.toml` are lowercase (`pyobjc-framework-cocoa`); `AppKit` ships inside `pyobjc-framework-cocoa`.

## Common tasks

### Changing live-typing behavior
1. Algorithm lives in `streaming.py` (`HOLDBACK_WORDS`, `MAX_WORD_RUN`, `interval`).
2. Replicate any reported garbled output as an input-sequence unit case first (feed hypotheses through `_ingest`/`finalize`), then change the algorithm.
3. Wiring is in `app.py` `_on_ptt_down` / `_asr_and_inject`; the paste fallback path must keep working when nothing was committed.

### Changing interview recording
1. Session logic lives in `interview.py` (`CHUNK_SECONDS`, `DRAIN_INTERVAL`, `OUTPUT_DIR`).
2. Test without a mic/model: stub `asr.transcribe_samples`, feed a fake recorder exposing `drain_new()`, and assert the `.txt`/`.wav` pair (final partial chunk must flush on `stop()`).
3. Wiring is in `app.py` `_on_interview_toggle` / `_stop_interview`; menu/status mutations go through `AppHelper.callAfter`.

### Swapping the ASR model
1. Change `MODEL_REPO` in `engine/asr.py` (e.g. `mlx-community/whisper-medium-mlx-q4` for better accuracy at ~1 GB).
2. Run `make smoke`; check the `[asr] … rtf=…` log line stays well above 1× realtime.

### Manual end-to-end verification (needs desktop session + permissions)
1. `make run`, wait for `●`.
2. TextEdit → hold Right Option, speak ≥6 s, release: words appear during speech (bursts), tail on release, `✓` flash.
3. Select text → ⌃⌥S speaks it. Clipboard contents must survive both flows.

## Permissions gotcha

Microphone, Accessibility, and Input Monitoring grants attach to the *terminal
app* that launched the bar. Hotkey listeners read grants at startup — relaunch
after granting. Secure fields reject synthesized input by design.
