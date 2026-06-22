from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "codewithvoice"
LEGACY_CONFIG_DIR = Path.home() / ".config" / "gemma-voicebar"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {"voice": "af_heart", "live_typing": True, "mute_summaries": False}


def load_config() -> dict:
    path = CONFIG_PATH
    if not path.exists():
        legacy = LEGACY_CONFIG_DIR / "config.json"
        if legacy.exists():
            path = legacy
        else:
            return dict(DEFAULT_CONFIG)
    try:
        return {**DEFAULT_CONFIG, **json.loads(path.read_text())}
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


class Runtime:
    """Mutable in-memory app state."""

    last_injected: str | None = None
