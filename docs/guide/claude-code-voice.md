# How to get spoken summaries from Claude Code

**Goal:** after every Claude Code turn, hear a one-sentence spoken summary of
what it did — instead of reading multi-hundred-word responses.

**You'll need:** the bar app running, and the `claude` CLI on your PATH.

## How it works

```text
Claude finishes a turn
  → Stop hook runs hooks/speak-summary.py (async, non-blocking)
  → summarizes the response to one sentence via `claude -p --model haiku`
  → drops it in ~/.local/state/codewithvoice/speak/
  → the bar app's spool watcher speaks it through Kokoro
```

If the summarizer call fails (no `claude` CLI, no credits, timeout), the hook
falls back to speaking the first two sentences of the response, markdown
stripped.

## Enable it everywhere (recommended)

The hook is stdlib-only Python — it does not need this project's virtualenv,
so one copy serves all your projects:

```bash
mkdir -p ~/.claude/hooks
cp hooks/speak-summary.py ~/.claude/hooks/
```

Register it in `~/.claude/settings.json` (create the file if missing; if you
already have a `hooks` section, add the `Stop` entry to it):

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

Hooks load at session start — open a **new** Claude Code session to hear it.
`"async": true` matters: the summary is generated in the background, so your
next prompt is never blocked.

## Or enable it per project

Copy the script into the project and register it in the project's
`.claude/settings.json` instead, using the project-relative path:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR\"/hooks/speak-summary.py",
        "async": true,
        "timeout": 60
      }
    ]
  }
}
```

This repo ships exactly that configuration, so Claude Code sessions in this
repo speak summaries out of the box.

## Speak anything from the shell

The same spool powers a general-purpose command:

```bash
codewithvoice-speak "build finished"
make test 2>&1 | tail -1 | codewithvoice-speak
```

Text is cleaned for speech (markdown stripped, code blocks replaced with
"code omitted") and spoken by the already-loaded Kokoro — the bar app must be
running with `●` in the menu bar.

## Tuning

- **Summary length/style** — edit `PROMPT` in `hooks/speak-summary.py`.
- **Summarizer model** — `SUMMARY_MODEL` in the same file (default `haiku`:
  fast and cheap; each summary costs roughly 500 input tokens).
- **Voice** — the spool uses the same voice as ⌃⌥S (menu bar → Voice).

## If you hear nothing

1. Is the bar running with `●` in the menu bar? The spool is only watched
   once models finish loading.
2. Did you start a **new** Claude Code session after registering the hook?
3. Is the `claude` CLI on the PATH that hooks run with? Without it the hook
   still speaks (first two sentences of the response) — silence means the
   spool isn't being read, not that summarization failed.
4. Test the pipeline directly: `codewithvoice-speak "test"` — if that speaks,
   the bar side is fine and the issue is hook registration.
5. Requests older than 30 s are dropped unheard (see the spool reference), so a
   summary spooled while the bar was closed won't play when you launch it
   later — only summaries from the last few seconds are spoken. This is by
   design: it stops a backlog from flooding out on startup.
