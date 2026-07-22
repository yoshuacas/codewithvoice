#!/bin/zsh
# Register (or remove) codewithvoice as a macOS Login Item so the menu bar
# starts on every login. Uses a Login Item — NOT a launchd LaunchAgent, which
# is deliberately banned here (see AGENTS.md: no daemon/LaunchAgent).
#
#   scripts/login-item.sh install   # add / refresh the Login Item
#   scripts/login-item.sh remove    # remove it
#   scripts/login-item.sh status    # show whether it's registered
#
# Idempotent: install removes any prior entry of the same name first.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="codewithvoice"
LAUNCHER="$ROOT/start.command"

make_launcher() {
  # Login Items run a double-clickable file; a .command opens in Terminal, so
  # the Microphone/Accessibility/Input Monitoring grants attach to Terminal.
  cat > "$LAUNCHER" <<EOF
#!/bin/zsh
cd "$ROOT" || exit 1
exec uv run python -m voicebar
EOF
  chmod +x "$LAUNCHER"
}

case "${1:-install}" in
  install)
    make_launcher
    osascript >/dev/null <<EOF
tell application "System Events"
  if login item "$NAME" exists then delete login item "$NAME"
  make new login item at end with properties ¬
    {name:"$NAME", path:"$LAUNCHER", hidden:false}
end tell
EOF
    echo "Registered Login Item '$NAME' -> $LAUNCHER"
    echo "Grant Microphone/Accessibility/Input Monitoring to Terminal if not already (see docs)."
    ;;
  remove)
    osascript >/dev/null <<EOF
tell application "System Events"
  if login item "$NAME" exists then delete login item "$NAME"
end tell
EOF
    echo "Removed Login Item '$NAME' (launcher $LAUNCHER left in place)."
    ;;
  status)
    osascript <<EOF
tell application "System Events"
  if login item "$NAME" exists then
    return "Login Item '$NAME' is registered -> " & (path of login item "$NAME")
  else
    return "Login Item '$NAME' is not registered"
  end if
end tell
EOF
    ;;
  *)
    echo "usage: $0 {install|remove|status}" >&2
    exit 2
    ;;
esac
