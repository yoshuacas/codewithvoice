#!/usr/bin/env python3
"""Claude Code Stop hook: speak a one-sentence summary of the turn.

Reads the Stop-hook JSON from stdin (which carries a `transcript_path`, not
the message itself), pulls the last assistant turn out of that transcript,
summarizes it with a fast model via `claude -p`, and drops the result into
the codewithvoice speak spool, where a running bar app picks it up and speaks
it through Kokoro. Stdlib-only; degrades to the first sentences of the
response if the summarizer call fails.

Register in settings.json (each Stop entry is a {matcher?, hooks:[...]} group):
    {"hooks": {"Stop": [{"hooks": [{"type": "command",
                         "command": "python3 /abs/path/hooks/speak-summary.py",
                         "async": true, "timeout": 60}]}]}}
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

SPOOL_DIR = Path.home() / ".local" / "state" / "codewithvoice" / "speak"
SUMMARY_MODEL = "haiku"
MAX_INPUT_CHARS = 8000  # plenty for a turn; keeps the summary call fast

PROMPT = (
    "Summarize this AI coding assistant's message in ONE short spoken sentence "
    "(under 25 words). Lead with what happened or was found. Include a caveat "
    "only if critical (test failure, blocked, needs user decision). No markdown, "
    "no preamble — output only the sentence.\n\nMessage:\n"
)


def final_text(payload: dict) -> str:
    """Text of the last assistant turn.

    The Stop-hook payload does NOT carry the message inline — it gives a
    `transcript_path` to a JSONL conversation log. Read it, find the last
    `type == "assistant"` entry, and join its `message.content` text blocks.
    """
    path = payload.get("transcript_path")
    if not path:
        return ""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    last_blocks: list = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        if isinstance(content, list):
            last_blocks = content
    return "\n".join(
        b.get("text", "")
        for b in last_blocks
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


def summarize(text: str) -> str | None:
    try:
        out = subprocess.run(
            ["claude", "-p", "--model", SUMMARY_MODEL],
            input=PROMPT + text[:MAX_INPUT_CHARS],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    summary = out.stdout.strip()
    return summary if out.returncode == 0 and summary else None


def first_sentences(text: str, limit: int = 2) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_`#|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:limit])


def submit(text: str) -> None:
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SPOOL_DIR / f".{uuid.uuid4().hex}.tmp"
    tmp.write_text(text, encoding="utf-8")
    tmp.rename(tmp.with_name(tmp.name[1:-4] + ".txt"))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    text = final_text(payload)
    if not text:
        sys.exit(0)
    speech = summarize(text) or first_sentences(text)
    if speech:
        submit(speech)


if __name__ == "__main__":
    main()
