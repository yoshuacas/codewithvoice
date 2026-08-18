"""Detect whether we're running from inside a .app bundle.

`NSBundle.mainBundle` resolves to the .app when launched via its bundled
interpreter (Contents/MacOS launcher), and to the bare interpreter's directory
under `uv run` — that distinction gates bundle-only features like the
Start-at-Login menu item.
"""

from __future__ import annotations

from Foundation import NSBundle


def is_bundled() -> bool:
    return str(NSBundle.mainBundle().bundlePath()).endswith(".app")
