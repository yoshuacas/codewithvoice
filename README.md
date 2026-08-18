<p align="center"><em>Local, accurate voice dictation for macOS — Whisper ASR + Kokoro TTS in a single menu-bar app.</em></p>

<p align="center">
  <a href="https://yoshuacas.github.io/codewithvoice/">Documentation</a> ·
  <a href="https://yoshuacas.github.io/codewithvoice/tutorials/getting-started/">Getting started</a> ·
  <a href="https://yoshuacas.github.io/codewithvoice/reference/">Reference</a> ·
  <a href="./AGENTS.md">Agent guide</a>
</p>

---

# codewithvoice

**codewithvoice** replaces macOS built-in dictation with a menu-bar app that runs
entirely on-device: [mlx-whisper](https://github.com/ml-explore/mlx-examples) for
speech-to-text and [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) for
text-to-speech, in one process. Apple's dictation types instantly but mishears
constantly; this types a couple of seconds behind your voice, and gets the words
right.

Because it types into whatever has focus, it works as **voice input for AI coding
tools** — talk your prompts into Claude Code, Cursor, aider, or any terminal or
editor. No subscription required (Claude Code's built-in `/voice` is gated to
Anthropic subscription plans), no audio sent anywhere.

## Key features

- **Push-to-talk dictation** — hold Right Option, speak, release; text lands at your cursor.
- **Live typing** — confirmed words are typed *while* you speak (LocalAgreement-2 over chunked whisper passes), with layered guards against whisper's silence-hallucination loops.
- **Speak-back** — ⌃⌥S reads the selected text aloud; 8 Kokoro voices.
- **Spoken Claude Code summaries** — a Stop hook speaks a one-sentence summary of every turn, so you hear what happened instead of reading walls of text. Works for any tool via `codewithvoice-speak` or the speak spool.
- **100% local** — audio never leaves the machine; models are ~500 MB (whisper-small-q4) + ~330 MB (Kokoro).
- **Clipboard-safe** — paste injection snapshots and restores clipboard contents, including rich types.
- **Single process** — no daemon, no HTTP; one `rumps` app owns hotkeys, mic, models, and injection.

## Quickstart

Requires Apple Silicon and macOS 14+.

1. Download `CodeWithVoice-<version>.dmg` from the
   [latest release](https://github.com/yoshuacas/codewithvoice/releases) and
   drag **CodeWithVoice** to Applications.
2. First open (releases aren't notarized yet): on Sequoia, double-click, then
   **System Settings → Privacy & Security → Open Anyway**; on Sonoma,
   right-click → **Open**.
3. Wait for the model download (~850 MB, first run only): ⏳ → ●.
4. Grant **Microphone**, **Accessibility**, and **Input Monitoring** to
   CodeWithVoice when prompted, relaunch, then hold **Right Option** in any
   text field and speak.
5. Menu bar → **Start at Login** to have it at every reboot.

Full walkthrough:
[Getting started](https://yoshuacas.github.io/codewithvoice/tutorials/getting-started/).

### Developing

With [Homebrew](https://brew.sh) and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/yoshuacas/codewithvoice.git
cd codewithvoice
make install
make espeak    # Kokoro fallback for uncommon words
make run       # first run downloads models (~850 MB), then ⏳ → ●
make app       # build dist/CodeWithVoice.app; make dmg packages it
```

For the full voice loop with Claude Code — dictate your prompt, hear a spoken
summary of each response — add the
[Stop hook](https://yoshuacas.github.io/codewithvoice/guide/claude-code-voice/)
(one settings.json entry, ~2 minutes).

## Documentation

Full docs at **[yoshuacas.github.io/codewithvoice](https://yoshuacas.github.io/codewithvoice/)**:

- [Tutorial: getting started](https://yoshuacas.github.io/codewithvoice/tutorials/getting-started/)
- [Guides](https://yoshuacas.github.io/codewithvoice/guide/) — permissions, live-typing tuning, voices, login launch, slow-ASR diagnosis
- [Reference](https://yoshuacas.github.io/codewithvoice/reference/) — hotkeys, menu, config keys, models, module map
- [How it works](https://yoshuacas.github.io/codewithvoice/explanation/architecture/) — the single-process design and how live typing works on a non-streaming model

Source for all pages lives in [`./docs`](./docs) (MkDocs Material; `make docs`
serves it locally). AI coding agents: start at [AGENTS.md](./AGENTS.md).

## Project layout

```text
src/voicebar/     — the app (engine/, streaming.py, recorder, hotkeys, inject…)
docs/             — documentation site source (MkDocs Material)
samples/          — sample audio used by `make smoke`
scripts/          — build-app.sh / build-dmg.sh (release), login-item.sh (source)
Makefile          — install / run / smoke / espeak / docs / app / dmg
```

## License

[MIT](./LICENSE). Whisper weights are MIT, Kokoro TTS is Apache 2.0.
