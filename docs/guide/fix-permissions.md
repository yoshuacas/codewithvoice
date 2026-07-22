# How to fix hotkeys that do nothing

**Goal:** Right Option or ⌃⌥S is pressed and nothing happens — no recording
indicator, no notification.

**You'll need:** to know which terminal app you launch codewithvoice from.

macOS attributes permissions to the *host application* of the process. When you
launch from Terminal, the grants live on Terminal — not on Python or the bar app.
If you switch terminals (say, Terminal → iTerm), you must grant everything again
for the new app.

## Checklist

Open **System Settings → Privacy & Security** and verify your terminal app is
enabled under all three panes:

| Pane | Symptom when missing |
|---|---|
| **Input Monitoring** | Hotkeys never fire; nothing happens at all |
| **Microphone** | Title flips to `⚠` and a "Microphone error" notification appears |
| **Accessibility** | Transcription works but no text appears (the synthesized ⌘V is blocked); "Paste blocked" notification |

## After changing a grant

1. Quit the app: menu bar `●` → **Quit**.
2. Relaunch: `make run`.

Microphone takes effect immediately, but the `pynput` listeners only read
Input Monitoring and Accessibility state at startup — a relaunch is required.

## Speak (⌃⌥S) works in some apps but not others

The app waits for you to physically release ⌃ and ⌥ before synthesizing the
⌘C that grabs your selection — macOS merges held modifiers into synthesized
keystrokes, and ⌘⌃⌥C matches no Copy command in most apps (terminals are the
strictest). If speak-selection still fails somewhere, release the hotkey
promptly after pressing it, and check the log for `[hotkeys]` errors.

## Startup crash in the keyboard listener (`AXIsProcessTrusted`)

If the log shows a traceback ending in

```
  File ".../objc/_lazyimport.py", line 359, in get_constant
    funcmap.pop(name)
KeyError: 'AXIsProcessTrusted'
```

the PTT listener thread died at startup, so Right Option does nothing even
though the models loaded fine. This is a thread-safety race in pyobjc's
lazy-import machinery when two listeners resolve the same symbol at once.
codewithvoice pre-resolves it on the main thread before starting the listeners
(`hotkeys._warm_ax_trust`); if you still see this, relaunch with `make run`.

## Still stuck

- Check you're testing in a normal text field. Password and other secure fields
  reject synthesized keystrokes by design; the text is left on the clipboard.
- Run from a foreground terminal and watch the log output: permission errors
  from the listeners print as `[hotkeys] ...` lines.
