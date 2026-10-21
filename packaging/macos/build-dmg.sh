#!/bin/bash
# MamidLabs (macOS) .dmg package — together with the SETUP WIZARD.
#
# The generated DMG contains "MamidLabs Setup.app". The user opens the DMG,
# drags the app into Applications and runs it: the wizard measures the hardware
# and suggests a suitable profile, then does the real installation (llama.cpp,
# ComfyUI, models) through `scripts/install-mamidlabs.sh`.
#
# Usage:
#   packaging/macos/build-dmg.sh [--output <dir>] [--no-icon]
#
# Requirement: macOS (hdiutil). For the icon sips/iconutil (built without an icon when missing).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

OUTPUT_DIR="${SCRIPT_DIR}/Output"
WITH_ICON=1

while [ $# -gt 0 ]; do
  case "$1" in
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --no-icon) WITH_ICON=0; shift ;;
    -h|--help)
      sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "[error] unknown option: $1" >&2; exit 1 ;;
  esac
done

command -v hdiutil >/dev/null 2>&1 || {
  echo "[error] hdiutil not found; the DMG can only be built on macOS." >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' "$REPO_DIR/mamidlabs/__init__.py" | head -n1)"
[ -n "$VERSION" ] || { echo "[error] could not read the version: mamidlabs/__init__.py" >&2; exit 1; }

APP_NAME="MamidLabs Setup"
STAGE="${SCRIPT_DIR}/build/dmg"
APP="${STAGE}/${APP_NAME}.app"
DMG_NAME="MamidLabs-Setup-${VERSION}.dmg"

echo "[MamidLabs] Preparing the DMG: $DMG_NAME"
rm -rf "$STAGE"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"

# --- Info.plist (the version placeholder is filled in) -----------------------
sed "s/@VERSION@/${VERSION}/g" "${SCRIPT_DIR}/Info.plist" > "${APP}/Contents/Info.plist"

# --- inner launcher ----------------------------------------------------------
cp "${SCRIPT_DIR}/MacOS-MamidLabsSetup" "${APP}/Contents/MacOS/MamidLabsSetup"
chmod 0755 "${APP}/Contents/MacOS/MamidLabsSetup"

# --- embedded Python sources ------------------------------------------------
SRC="${APP}/Contents/Resources/mamidlabs-src"
mkdir -p "$SRC"
cp -R "$REPO_DIR/mamidlabs" "$SRC/mamidlabs"
find "$SRC" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$SRC" -name '*.pyc' -delete 2>/dev/null || true
cp -R "$REPO_DIR/scripts" "$SRC/scripts"
cp -R "$REPO_DIR/requirements" "$SRC/requirements"
cp "$REPO_DIR/pyproject.toml" "$SRC/"
for extra in EULA.txt LICENSE README.md CHANGELOG.md; do
  [ -f "$REPO_DIR/$extra" ] && cp "$REPO_DIR/$extra" "$SRC/"
done

# --- icon (optional) ---------------------------------------------------------
if [ "$WITH_ICON" -eq 1 ] && [ -f "$REPO_DIR/packaging/mamidlabs.png" ] \
   && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET="${STAGE}/mamidlabs.iconset"
  rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for size in 16 32 64 128 256 512; do
    sips -z "$size" "$size" "$REPO_DIR/packaging/mamidlabs.png" \
      --out "${ICONSET}/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$REPO_DIR/packaging/mamidlabs.png" \
      --out "${ICONSET}/icon_${size}x${size}@2x.png" >/dev/null
  done
  if iconutil -c icns "$ICONSET" -o "${APP}/Contents/Resources/mamidlabs.icns" 2>/dev/null; then
    echo "[MamidLabs] icon generated (sips/iconutil)"
  else
    echo "[warning] .icns could not be generated; continuing without an icon"
  fi
  rm -rf "$ICONSET"
else
  echo "[MamidLabs] skipping the icon (--no-icon or sips/iconutil missing)"
fi

# --- DMG ---------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR"
rm -f "${OUTPUT_DIR}/${DMG_NAME}"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "${OUTPUT_DIR}/${DMG_NAME}" >/dev/null

echo "[MamidLabs] ready: ${OUTPUT_DIR}/${DMG_NAME}"
echo "[MamidLabs] open: open \"${OUTPUT_DIR}/${DMG_NAME}\"  →  drag the app into Applications"
