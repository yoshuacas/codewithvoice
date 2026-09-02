# How to fix hotkeys that do nothing

**Goal:** Right Option or ⌃⌥S is pressed and nothing happens — no recording
indicator, no notification.

**You'll need:** to know which app owns the grants — **CodeWithVoice** itself
if you installed the .app, or your terminal app if you run from a source
checkout.

macOS attributes permissions to the *host application* of the process. The
installed **CodeWithVoice.app** owns its grants directly. When you launch from
a terminal instead, the grants live on Terminal (or iTerm, …) — not on Python
or the bar app — and switching terminals means granting everything again.

> **Unsigned builds:** while releases are ad-hoc signed (no Apple Developer
> ID), macOS treats each update as a new app — expect to re-grant the three
> permissions after updating CodeWithVoice.app.

## After updating the app: no prompt, grants silently dead

macOS does **not** re-prompt after you replace the .app: the old permission
entries (bound to the previous build's signature) still exist under the same
bundle ID, so it silently denies instead of asking. Reset them, then relaunch
and re-grant:

```bash
tccutil reset Accessibility io.github.yoshuacas.codewithvoice
tccutil reset ListenEvent   io.github.yoshuacas.codewithvoice   # Input Monitoring
tccutil reset Microphone    io.github.yoshuacas.codewithvoice
```

Missing **Accessibility** is the sneakiest case: hotkeys fire and
transcription runs (the log shows `[asr]` lines), but the synthesized
keystrokes are dropped without any error — dictated text simply never
appears. Accessibility never triggers a prompt on its own; add the app
manually with **+** in that pane.

To stop re-granting after every rebuild, sign with a stable identity. The
build script looks for a keychain identity named **`CodeWithVoice Signing`**
and uses it automatically (the `==> Signing as:` build line shows which
identity was picked); any other name still works via
`SIGN_IDENTITY="<certname>" make app`. Create the identity either in Keychain
Access (**Certificate Assistant → Create a Certificate…**, Identity Type
*Self-Signed Root*, Certificate Type **Code Signing**) or from a terminal:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 3650 -nodes \
  -subj "/CN=CodeWithVoice Signing" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=critical,codeSigning" \
  -addext "basicConstraints=critical,CA:false"
openssl pkcs12 -export -legacy -out cert.p12 -inkey key.pem -in cert.pem \
  -passout pass:tmpimport -name "CodeWithVoice Signing"   # -legacy: security(1) can't read OpenSSL 3 default PKCS12
security import cert.p12 -k ~/Library/Keychains/login.keychain-db \
  -P tmpimport -T /usr/bin/codesign
security add-trusted-cert -r trustRoot -p codeSign \
  -k ~/Library/Keychains/login.keychain-db cert.pem     # may prompt for your login password
rm key.pem cert.pem cert.p12
```

Approve the keychain prompt on the first `make app` (**Always Allow**). One
last `tccutil` reset + re-grant is needed when switching an installed ad-hoc
build to the signed identity; after that, grants survive every rebuild.

## Checklist

Open **System Settings → Privacy & Security** and verify the right app
(CodeWithVoice, or your terminal) is enabled under all three panes:

| Pane | Symptom when missing |
|---|---|
| **Input Monitoring** | Hotkeys never fire; nothing happens at all |
| **Microphone** | Title sticks at `⚠` and a "Microphone error" notification appears; the `Status:` menu item keeps the error text |
| **Accessibility** | Transcription works but no text appears (the synthesized ⌘V is blocked); "Paste blocked" notification |

## After changing a grant

1. Quit the app: menu bar `●` → **Quit**.
2. Relaunch: open CodeWithVoice.app again (or `make run` from a checkout).

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

- Click the menu bar icon and read the `Status:` item — it keeps the text of
  the last error (e.g. the exact microphone failure) even if you missed the
  notification.
- Check you're testing in a normal text field. Password and other secure fields
  reject synthesized keystrokes by design; the text is left on the clipboard.
- Read the log: the installed .app writes to `~/Library/Logs/CodeWithVoice.log`;
  from a source checkout, run in a foreground terminal and watch its output.
  Permission errors from the listeners print as `[hotkeys] ...` lines.
