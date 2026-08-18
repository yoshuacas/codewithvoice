# How to start codewithvoice at login

**Goal:** have the bar running after every reboot without keeping a terminal
window open.

## Installed app (recommended)

If you installed **CodeWithVoice.app** (from the DMG), click the menu-bar
icon → **Start at Login**. That's it — the app registers itself under
**System Settings → General → Login Items & Extensions** via Apple's
`SMAppService` API, and the same menu item unchecks to remove it.

> A Login Item is used deliberately instead of a `launchd` LaunchAgent: a
> background daemon was removed from this project on purpose and must not come
> back.

## Running from a source checkout

The **Start at Login** menu item only appears in the bundled app (macOS needs
an `.app` to register). From a clone, use the Login Item script instead:

```bash
make login          # register the Login Item
make login-remove   # undo
```

This writes a `start.command` launcher in the repo and registers it as a macOS
Login Item via `scripts/login-item.sh` (idempotent — rerun any time). Check the
current state with `./scripts/login-item.sh status`.

For a one-off launch, `./start.sh` (or `make run`) starts the bar from
anywhere.

### Caveat: source-checkout permissions follow the host app

`.command` files open in Terminal, so the Microphone / Accessibility /
Input Monitoring grants must be on **Terminal** (see
[How to fix hotkeys that do nothing](fix-permissions.md)). If you normally run
from iTerm, you'll be granting a second set for Terminal. The installed .app
does not have this problem — it owns its permissions.
