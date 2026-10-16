#!/bin/bash
# MamidLabs (macOS) .dmg paketi — KURULUM SİHİRBAZI ile birlikte.
#
# Üretilen DMG'nin içinde "MamidLabs Kurulum.app" vardır. Kullanıcı DMG'yi açar,
# uygulamayı Applications klasörüne sürükler ve çalıştırır: sihirbaz donanımı
# ölçüp uygun profili önerir, sonra gerçek kurulumu (llama.cpp, ComfyUI, modeller)
# `scripts/install-mamidlabs.sh` üzerinden yapar.
#
# Kullanım:
#   packaging/macos/build-dmg.sh [--output <dizin>] [--no-icon]
#
# Gereksinim: macOS (hdiutil). İkon için sips/iconutil (yoksa ikonsuz derlenir).
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
    *) echo "[hata] bilinmeyen seçenek: $1" >&2; exit 1 ;;
  esac
done

command -v hdiutil >/dev/null 2>&1 || {
  echo "[hata] hdiutil bulunamadı; DMG yalnızca macOS'ta derlenir." >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' "$REPO_DIR/mamidlabs/__init__.py" | head -n1)"
[ -n "$VERSION" ] || { echo "[hata] sürüm okunamadı: mamidlabs/__init__.py" >&2; exit 1; }

APP_NAME="MamidLabs Kurulum"
STAGE="${SCRIPT_DIR}/build/dmg"
APP="${STAGE}/${APP_NAME}.app"
DMG_NAME="MamidLabs-Kurulum-${VERSION}.dmg"

echo "[MamidLabs] DMG hazırlanıyor: $DMG_NAME"
rm -rf "$STAGE"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"

# --- Info.plist (sürüm yer tutucusu doldurulur) ------------------------------
sed "s/@VERSION@/${VERSION}/g" "${SCRIPT_DIR}/Info.plist" > "${APP}/Contents/Info.plist"

# --- iç yürütücü -------------------------------------------------------------
cp "${SCRIPT_DIR}/MacOS-MamidLabsSetup" "${APP}/Contents/MacOS/MamidLabsSetup"
chmod 0755 "${APP}/Contents/MacOS/MamidLabsSetup"

# --- gömülü Python kaynakları ------------------------------------------------
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

# --- simge (opsiyonel) -------------------------------------------------------
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
    echo "[MamidLabs] ikon üretildi (sips/iconutil)"
  else
    echo "[uyarı] .icns üretilemedi; ikonsuz devam ediliyor"
  fi
  rm -rf "$ICONSET"
else
  echo "[MamidLabs] ikon atlanıyor (--no-icon ya da sips/iconutil yok)"
fi

# --- DMG ---------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR"
rm -f "${OUTPUT_DIR}/${DMG_NAME}"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "${OUTPUT_DIR}/${DMG_NAME}" >/dev/null

echo "[MamidLabs] hazır: ${OUTPUT_DIR}/${DMG_NAME}"
echo "[MamidLabs] aç: open \"${OUTPUT_DIR}/${DMG_NAME}\"  →  uygulamayı Applications'a sürükle"
