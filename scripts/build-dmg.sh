#!/bin/zsh
# Package dist/CodeWithVoice.app into dist/CodeWithVoice-<version>.dmg
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
APP="$ROOT/dist/CodeWithVoice.app"
DMG="$ROOT/dist/CodeWithVoice-$VERSION.dmg"
STAGE="$ROOT/build/dmg-root"

[[ -d "$APP" ]] || { echo "error: $APP missing — run scripts/build-app.sh first" >&2; exit 1; }

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

hdiutil create -volname "CodeWithVoice" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
shasum -a 256 "$DMG"
echo "==> Built $DMG"
