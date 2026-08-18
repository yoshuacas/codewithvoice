#!/bin/zsh
# Build dist/CodeWithVoice.app — a self-contained, relocatable bundle.
#
# Approach: no freezer (py2app/PyInstaller choke on torch/spacy/mlx).
# We ship a python-build-standalone CPython in Contents/Resources/python and
# `uv pip install` the exact locked dependency set into its real site-packages
# (NOT a venv — venvs embed absolute paths and don't relocate).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
BUNDLE_ID="io.github.yoshuacas.codewithvoice"
APP="$ROOT/dist/CodeWithVoice.app"
CONTENTS="$APP/Contents"
RES="$CONTENTS/Resources"
PYDIST="$ROOT/build/python-dist"
# "-" = ad-hoc signing. For Developer ID, export e.g.:
#   SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
SIGN_IDENTITY="${SIGN_IDENTITY:--}"

echo "==> Building CodeWithVoice.app $VERSION"
rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$RES" "$ROOT/build"

# ---- 1. Relocatable CPython (python-build-standalone via uv) --------------
if [[ ! -d "$PYDIST" ]]; then
  uv python install 3.12 --install-dir "$PYDIST"
fi
PBS_DIR="$(echo "$PYDIST"/cpython-3.12*)"
[[ -d "$PBS_DIR" ]] || { echo "error: no cpython-3.12* under $PYDIST" >&2; exit 1; }
cp -R "$PBS_DIR/" "$RES/python/"
PY="$RES/python/bin/python3.12"
"$PY" --version >/dev/null  # sanity: interpreter runs from its new home

# ---- 2. Locked dependencies + the project wheel ---------------------------
uv build --wheel -o build/wheels >/dev/null
uv export --frozen --no-dev --no-emit-project -o build/requirements.txt --quiet
uv pip install --python "$PY" --break-system-packages --quiet \
  -r build/requirements.txt \
  build/wheels/codewithvoice-"$VERSION"-*.whl

# misaki (kokoro's G2P) pip-installs en_core_web_sm at runtime if missing —
# impossible inside the bundle (externally-managed marker, signed app).
# Pre-install the spacy model wheel instead.
SPACY_MODEL_URL="https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
uv pip install --python "$PY" --break-system-packages --quiet "en_core_web_sm@$SPACY_MODEL_URL"

# Slim down and make bin/ scripts relocatable.
find "$RES/python" -name '__pycache__' -type d -prune -exec rm -rf {} +
for script in "$RES/python/bin/codewithvoice" "$RES/python/bin/codewithvoice-speak"; do
  name="$(basename "$script")"
  mod="voicebar.__main__"; [[ "$name" == "codewithvoice-speak" ]] && mod="voicebar.speak_cli"
  cat > "$script" <<WRAP
#!/bin/sh
exec "\$(dirname "\$0")/python3.12" -B -m $mod "\$@"
WRAP
  chmod +x "$script"
done

# ---- 3. Launcher, Info.plist, PkgInfo, icon -------------------------------
# The launcher MUST be a compiled Mach-O binary that keeps running as the
# bundle's main executable (it embeds python via libpython). A shell stub
# that exec()s python leaves the process identity as "python3.12", which no
# longer matches the app record — the WindowServer then never attaches the
# NSStatusItem scene (no menu bar icon) and TCC silently denies the mic.
# This also satisfies notarization's Mach-O main-executable requirement.
cc -O2 -Wall -o "$CONTENTS/MacOS/codewithvoice" scripts/launcher.c

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
	<key>CFBundleName</key><string>CodeWithVoice</string>
	<key>CFBundleDisplayName</key><string>CodeWithVoice</string>
	<key>CFBundleExecutable</key><string>codewithvoice</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>$VERSION</string>
	<key>CFBundleVersion</key><string>$VERSION</string>
	<key>CFBundleIconFile</key><string>AppIcon</string>
	<key>LSUIElement</key><true/>
	<key>LSMinimumSystemVersion</key><string>14.0</string>
	<key>LSRequiresNativeExecution</key><true/>
	<key>LSArchitecturePriority</key><array><string>arm64</string></array>
	<key>NSHighResolutionCapable</key><true/>
	<key>NSMicrophoneUsageDescription</key>
	<string>CodeWithVoice records your voice to transcribe it locally on this Mac. Audio never leaves the device.</string>
</dict>
</plist>
PLIST

printf 'APPL????' > "$CONTENTS/PkgInfo"

ICONSET="$ROOT/build/AppIcon.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon-1024.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) assets/icon-1024.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$RES/AppIcon.icns"

# ---- 4. Sign ---------------------------------------------------------------
# ---- SIGNING SEAM ----
# Ad-hoc today: TCC identity resets on every rebuild (users re-grant perms).
# Developer ID later:
#   1. sign inside-out with --options runtime --entitlements scripts/entitlements.plist
#   2. ditto -c -k dist/CodeWithVoice.app build/app.zip
#   3. xcrun notarytool submit build/app.zip --keychain-profile codewithvoice --wait
#   4. xcrun stapler staple dist/CodeWithVoice.app
codesign --force --deep -s "$SIGN_IDENTITY" "$APP"
codesign --verify --deep "$APP"

du -sh "$APP"
echo "==> Built $APP"
