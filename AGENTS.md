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
make app       # build dist/CodeWithVoice.app (self-contained, ad-hoc signed)
make dmg       # package the app into dist/CodeWithVoice-<version>.dmg
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
- Error surfacing goes through `app.py:_warn` (notification + ⚠ + reason in the `Status:` menu item). Mic-open failures use `sticky=True` (⚠ stays up); the reason persists until `_set_status_ready()` runs on the next successful flow. Don't set `ICON_WARN` directly without also setting a status reason.
- **ALWAYS** update the matching page under `docs/` (reference for behavior, guides for workflows) in the same change as a user-visible code change.
- Recording is **uncapped by default** (`recorder.py:MAX_SECONDS = None`): it records until PTT release. Each live streaming pass re-transcribes from sample 0, so on long clips live typing updates less often (the final full-clip pass stays accurate). If you re-introduce a cap or want snappy live typing on long clips, window the streaming buffer rather than just trimming capture.
- Interview recording (`interview.py`) is a **separate flow from PTT**: hands-free, types nothing, and streams a `.txt`/`.wav` pair to `~/Documents/codewithvoice-interviews/`. It owns the mic exclusively (PTT/speak are gated off while active) and uses `recorder.drain_new()` for flat-memory chunked capture — never `snapshot()`/`stop()`, which keep cumulative frames. Keep both the `.txt` and `.wav` flushed per chunk so a crash/quit loses nothing; `_on_quit` must `stop()` an active session to close the `.wav`.
- **DO NOT** add a daemon/socket for external speak requests — the file spool (`spool.py`) is the supported IPC; keep `hooks/speak-summary.py` stdlib-only (it must run outside this venv) and keep spool writes atomic (tmp file, then rename).
- **DO NOT** add models that won't fit comfortably in RAM next to normal apps; a 10 GB Gemma-as-ASR experiment thrashed 32 GB into 44 GB of swap. Memory-pressure check: if the process RSS ≪ VSZ, the model is paged out — free RAM, don't tune inference.
- `Recorder.samplerate` is the **output** rate (16 kHz). Some mics (Anker PowerConf and other USB/conferencing devices) reject opening at 16 kHz with CoreAudio `-10851` and silently capture nothing; `start()` falls back to the device's native rate and `_to_output()` resamples on read. Keep all read paths (`stop`/`snapshot`/`drain_new`) routed through `_to_output` — don't reintroduce a raw `samplerate` open as the only attempt.
- **NEVER** do blocking work in a pynput hotkey callback — it runs on the CGEventTap thread; a callback that doesn't return freezes *every* hotkey (macOS may also disable the tap). `_on_ptt_down`/`_on_ptt_up` must only flip the PTT state machine (`_ptt_state` under `_ptt_lock`: idle → starting → recording → finishing) and spawn threads; the mic open lives in `app.py:_begin_ptt`, the heavy release path in `app.py:_finish_ptt`. The `_ptt_release_pending` flag covers a release that arrives while the mic is still opening — `_begin_ptt` then runs the finish path itself. (Observed 2026-09-02: `recorder.start()` in the down callback blocked on the HAL mutex an abandoned close still held; the tap froze and every hotkey died until relaunch.)
- **NEVER** let `Recorder` block indefinitely on closing **or opening** the stream: PortAudio's `Pa_StopStream` can deadlock against the CoreAudio HAL IO thread (observed 2026-08-25: `AudioOutputUnitStop` held the AudioUnit mutex waiting on the HAL IO mutex, whose owner was inside PortAudio's `startStopCallback` waiting on the AudioUnit mutex — app froze at 🔴 forever). `stop_internal()` closes the stream on a helper thread with a bounded join (`STOP_TIMEOUT_SECONDS`) and abandons it on timeout; the per-stream `accept` flag keeps an abandoned stream's late callbacks from polluting the next recording. Captured frames must never depend on the stream closing. The open side is bounded the same way (`OPEN_TIMEOUT_SECONDS`, raises `StreamOpenTimeout`, no native-rate retry): an abandoned close keeps holding the HAL mutex, so the *next* `Pa_OpenStream` deadlocks on it — only an app restart recovers, and the timeout turns that into a sticky ⚠ instead of a hung thread.
- Debugging a hung bundled app: `sample <pid> 3 -file out.txt` gives native stacks without root (py-spy needs sudo). Look for paired `__psynch_mutexwait` holders across threads.
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

## Distribution build (.app + DMG)

`scripts/build-app.sh` builds `dist/CodeWithVoice.app` with **no freezer**:
a python-build-standalone CPython in `Contents/Resources/python/` plus the
locked dependency set `uv pip install`-ed into its real site-packages (not a
venv — venvs embed absolute paths and don't relocate). Rules that keep it
working:

- The launcher (`scripts/launcher.c`) **must stay a compiled Mach-O binary
  that embeds python via `dlopen(libpython)`** — never a shell stub that
  `exec()`s python. After an `exec`, the process's code identity is
  `python3.12` (ad-hoc, per-binary), which no longer matches the app record
  LaunchServices launched: the WindowServer then never attaches the
  scene-based `NSStatusItem` (no menu-bar icon, item floats off-screen) and
  TCC can't attribute the mic request to the bundle (silent denial, no
  prompt). Terminal launches mask the bug — only Finder/`open` launches hit
  it. The launcher forwards argv when invoked with arguments because
  multiprocessing re-invokes `sys.executable -c …` for its spawn helpers.
- The launcher and all bundled bin scripts run python with `-B`
  (`PYTHONDONTWRITEBYTECODE`): writing `.pyc` inside the bundle breaks the
  codesign resource seal on first launch.
- The launcher redirects stdout/stderr to `~/Library/Logs/CodeWithVoice.log`
  when no tty is attached (Finder launches otherwise pipe them to /dev/null,
  making failures undiagnosable). It uses `open`+`dup2` — not `freopen`, which
  destroys the stream even when the open fails — rotates at 5 MB, and sets
  `PYTHONUNBUFFERED` so a crash doesn't swallow buffered lines. Keep this when
  touching `scripts/launcher.c`.
- `en_core_web_sm` is pre-installed at build time — misaki (kokoro's G2P)
  otherwise runs `pip install` at runtime, which fails inside the bundle.
- Signing: the script auto-uses a keychain identity named `CodeWithVoice
  Signing` when present (stable TCC identity across rebuilds; CLI creation
  recipe in `docs/guide/fix-permissions.md` — note `openssl pkcs12 -legacy`,
  since `security import` can't read OpenSSL 3's default PKCS12 format);
  `SIGN_IDENTITY` env var overrides; falls back to ad-hoc. The Developer ID
  signing/notarization seam is marked in the script.
- **Start at Login** in the bundled app uses `SMAppService`
  (`src/voicebar/login_item.py`) — this is a sanctioned Login Item, not the
  banned launchd-daemon topology. The menu item only appears when
  `bundle.is_bundled()`; source checkouts keep using `make login`.

## Permissions gotcha

Microphone, Accessibility, and Input Monitoring grants attach to the *host
app*: **CodeWithVoice.app** itself when running the bundle, or the *terminal
app* that launched the bar when running from source. Ad-hoc signed builds get
a new TCC identity on every rebuild — re-grant after rebuilding the app.
Hotkey listeners read grants at startup — relaunch after granting. Secure
fields reject synthesized input by design.

After replacing the installed .app, macOS does **not** re-prompt: the stale
same-bundle-ID TCC entries (bound to the old signature) make it silently deny
instead. Clear them first, then relaunch and re-grant:

```bash
tccutil reset Accessibility io.github.yoshuacas.codewithvoice
tccutil reset ListenEvent   io.github.yoshuacas.codewithvoice   # Input Monitoring
tccutil reset Microphone    io.github.yoshuacas.codewithvoice
```

Missing-Accessibility is the sneakiest state: hotkeys and ASR work (log shows
`[asr]` lines) but synthesized keystrokes/⌘V are dropped with no error — text
just never appears. pynput's startup line `This process is not trusted!` in
the log means Input Monitoring/Accessibility is missing. To stop re-granting
on every rebuild, sign with a stable identity: a self-signed cert named
`CodeWithVoice Signing` is picked up automatically by `make app` (created
2026-09-02 on David's machine; creation recipe in
`docs/guide/fix-permissions.md`). Switching an installed ad-hoc build to the
signed identity needs one last `tccutil` reset + re-grant; later rebuilds
keep the grants.
