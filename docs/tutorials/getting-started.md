# Getting started

Take codewithvoice from zero to your first dictated sentence. Takes about
10 minutes; most of that is the one-time model download.

**You'll need:** a Mac with Apple Silicon and macOS 14+.

## 1. Install the app

Download `CodeWithVoice-<version>.dmg` from the
[latest release](https://github.com/yoshuacas/codewithvoice/releases), open it,
and drag **CodeWithVoice** to **Applications**.

Releases are not yet notarized by Apple, so the first open needs one extra
step:

- **macOS 15 (Sequoia):** double-click the app (macOS blocks it), then go to
  **System Settings → Privacy & Security**, scroll down, and click
  **Open Anyway**.
- **macOS 14 (Sonoma):** right-click the app → **Open** → **Open**.
- Terminal alternative (either version):
  `xattr -dr com.apple.quarantine /Applications/CodeWithVoice.app`

*(Prefer running from source? See [Developing](#developing-from-a-source-checkout)
below.)*

## 2. Launch the app

Open **CodeWithVoice** from Applications. The menu bar shows `⏳` while models
load. The first launch downloads whisper-small (~500 MB) and Kokoro (~330 MB)
from Hugging Face — a few minutes on a fast connection; a notification tells
you the download is running. Subsequent launches load in 10–25 seconds. When
the title flips to `●`, it's ready.

## 3. Grant permissions

The first time you dictate, macOS prompts for three permissions, all
attributed to **CodeWithVoice** itself. Approve all three under
**System Settings → Privacy & Security**:

1. **Microphone**
2. **Accessibility**
3. **Input Monitoring**

After granting Input Monitoring, quit the app (menu bar → Quit) and open it
again so the hotkey listeners pick up the grant.

## 4. Start at login (optional)

Click the menu-bar icon → **Start at Login**. The bar now comes up with every
reboot. Details: [How to start codewithvoice at login](../guide/start-at-login.md).

## 5. Dictate

1. Open TextEdit and click into the document.
2. Hold **Right Option**, say *"hello world, this is my first dictation"*, release.
3. Watch the menu bar: `🔴` recording → `⏳` transcribing → `✓` done.

Your words appear at the cursor. If you spoke for more than ~5 seconds, you'll
see confirmed words being typed *while* you talk — that's live typing.

## 6. Hear it back

Select the text you just dictated and press **⌃⌥S** (Control+Option+S).
Kokoro reads it aloud.

That's it — you have a working local dictation setup.

## 7. Optional: spoken summaries from Claude Code

If you use Claude Code, close the loop — dictate your prompts with Right
Option, and hear a one-sentence spoken summary when Claude finishes each turn:

```bash
mkdir -p ~/.claude/hooks
cp hooks/speak-summary.py ~/.claude/hooks/
```

Then add to `~/.claude/settings.json` (create it if missing):

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "python3 ~/.claude/hooks/speak-summary.py",
        "async": true,
        "timeout": 60
      }
    ]
  }
}
```

Start a new Claude Code session anywhere, ask it something, and the bar speaks
the summary. Details and tuning:
[How to get spoken summaries from Claude Code](../guide/claude-code-voice.md).

## Developing from a source checkout

To hack on codewithvoice (or if you'd rather not download a 500 MB DMG), run
it from a clone. You'll need [Homebrew](https://brew.sh) and
[uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
git clone https://github.com/yoshuacas/codewithvoice.git
cd codewithvoice
make install    # uv sync
make espeak     # espeak-ng: Kokoro's fallback for words outside its lexicon
make run
```

Note that when running from a terminal, the three permissions attach to the
*terminal app*, not to codewithvoice — see
[How to fix hotkeys that do nothing](../guide/fix-permissions.md). Build your
own bundle with `make app` (and `make dmg` to package it).

**What next?**

- [How to fix hotkeys that do nothing](../guide/fix-permissions.md) — if step 5 didn't work
- [How to tune or disable live typing](../guide/live-typing.md)
- [Hotkeys and menu reference](../reference/index.md)
