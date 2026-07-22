# How to start codewithvoice at login

**Goal:** have the bar running after every reboot without keeping a terminal
window open.

There is no code-signed `.app` bundle yet, so the practical option is a small
launcher script registered as a Login Item.

## Quick start (any time)

From the repo, `./start.sh` (or `make run`) launches the bar. `start.sh`
resolves the project root from its own location, so it works from anywhere.

## Start at every login (one command)

```bash
make login          # register the Login Item
make login-remove   # undo
```

This writes a `start.command` launcher in the repo and registers it as a macOS
Login Item via `scripts/login-item.sh` (idempotent — rerun any time). Check the
current state with `./scripts/login-item.sh status`.

> A Login Item is used deliberately instead of a `launchd` LaunchAgent: a
> background daemon was removed from this project on purpose and must not come
> back.

## Doing it manually instead

The script automates these steps; do them by hand if you prefer:

1. Make a launcher — a `.command` that `cd`s to your clone and runs
   `uv run python -m voicebar`.
2. **System Settings → General → Login Items & Extensions → Open at Login → +**
   and select the `.command` file.

## Caveat: permissions follow the host app

`.command` files open in Terminal, so the Microphone / Accessibility /
Input Monitoring grants must be on **Terminal** (see
[How to fix hotkeys that do nothing](fix-permissions.md)). If you normally run
from iTerm, you'll be granting a second set for Terminal.

A proper code-signed `.app` bundle — which would own its permissions and skip
the terminal entirely — is on the roadmap but not built yet.
