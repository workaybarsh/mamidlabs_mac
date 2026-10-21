#!/bin/bash
# MamidLabs (macOS) installer.
#
# Stages (run in order): preflight, layout, llama, python, comfyui, models, verify
#
# Everything is installed under the install root (default
# ~/Library/Application Support/mamidlabs, override with --root or
# MAMIDLABS_ROOT). Nothing is written outside it except the .app bundle, which
# you can skip with --no-desktop.
#
# macOS ships bash 3.2; this script sticks to features that exist there (no
# associative arrays, no ${var,,}, no mapfile).
set -euo pipefail

LLAMA_BUILD="b10998"
COMFY_COMMIT="b0f4b7b"
COMFY_GGUF_COMMIT="6ea2651"
KREA2EDIT_COMMIT="86f886d"
COMFY_REPO="https://github.com/comfyanonymous/ComfyUI.git"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT="${MAMIDLABS_ROOT:-$HOME/Library/Application Support/mamidlabs}"
STAGES="preflight,layout,llama,python,comfyui,models,verify"
PROFILE=""
LANGUAGE=""
NO_DESKTOP=0
SKIP_MEDIA=0
SKIP_AUDIO=0
SKIP_OCR=0
SKIP_MODELS=0
FORCE=0
PYTHON=""

usage() {
  cat <<'EOF'
Usage: install-mamidlabs.sh [options]

  --root <path>       Install root (default: ~/Library/Application Support/mamidlabs)
  --profile <name>    max | flash | lite  (model download profile)
  --language <code>   en | tr  (interface language; written to settings/api.json)
  --stage <list>      Stages to run (comma-separated):
                      preflight,layout,llama,python,comfyui,models,verify
  --skip-media        Skip ComfyUI and the image/video models
  --skip-audio        Skip the transcription (asr) environment
  --skip-ocr          Skip the OCR environment
  --skip-models       Skip the language model download
  --no-desktop        Do not install the MamidLabs.app bundle
  --no-cuda           Ignored (Metal/MPS is always used on macOS)
  --force             Reinstall over the existing install
  -h, --help          This text
EOF
}

log()  { printf '\033[1;34m[MamidLabs]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warning]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --language)
      case "$2" in
        tr|en) LANGUAGE="$2" ;;
        *) die "invalid language: $2 (en|tr)" ;;
      esac
      shift 2 ;;
    --stage) STAGES="$2"; shift 2 ;;
    --skip-media) SKIP_MEDIA=1; shift ;;
    --skip-audio) SKIP_AUDIO=1; shift ;;
    --skip-ocr) SKIP_OCR=1; shift ;;
    --skip-models) SKIP_MODELS=1; shift ;;
    --no-desktop) NO_DESKTOP=1; shift ;;
    --no-cuda) shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

export MAMIDLABS_ROOT="$ROOT"

has_stage() { case ",${STAGES}," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

have_cmd() { command -v "$1" >/dev/null 2>&1; }

# Resolve the root to an absolute path (BSD realpath has no -m; use Python).
abs_path() {
  "$1" -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$2"
}

# Pick a suitable interpreter (3.11–3.13). macOS system python3 is often 3.9.
detect_python() {
  local cand v
  for cand in python3.12 python3.13 python3.11 python3; do
    if have_cmd "$cand"; then
      v="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
      case "$v" in
        3.11|3.12|3.13) PYTHON="$cand"; return 0 ;;
      esac
    fi
  done
  return 1
}

# On macOS the accelerator is Metal (always present on supported hardware).
detect_gpu() { [ "$(uname -s)" = "Darwin" ]; }

# --- stages ------------------------------------------------------------------
stage_preflight() {
  log "Checking prerequisites"
  detect_python || die "Python 3.11–3.13 not found. Install: brew install python@3.12"
  log "Python: $PYTHON ($("$PYTHON" --version 2>&1))"
  "$PYTHON" -c 'import venv' >/dev/null 2>&1 || die "The venv module is missing."
  have_cmd git || warn "git not found; the ComfyUI stage will be skipped (brew install git)."
  have_cmd curl || warn "curl not found; downloads may fail."
  have_cmd unzip || warn "unzip not found; llama.cpp cannot be extracted (ships with macOS)."
  if [ "$SKIP_MEDIA" -eq 0 ]; then
    detect_gpu || warn "Metal does not look available; image/video generation will be very slow."
  fi
  if have_cmd 7z || have_cmd 7za; then
    :
  else
    warn "7-Zip not found; RAR reading will be disabled (brew install sevenzip)."
  fi
  local free_gb
  free_gb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}' || echo 0)"
  [ "${free_gb:-0}" -ge 60 ] || warn "Free disk ${free_gb} GB; LITE needs ~36 GB, MAX/FLASH ~52 GB."
}

stage_layout() {
  log "Installing program files: $ROOT"
  mkdir -p "$ROOT"
  local venv_dir="$ROOT/venv/app"
  "$PYTHON" -m venv --upgrade-deps "$venv_dir"
  "$venv_dir/bin/python" -m pip install --quiet --upgrade pip
  "$venv_dir/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements/app.txt"
  "$venv_dir/bin/python" -m pip install --quiet --no-deps -e "$REPO_DIR"

  # Launcher helper (so the .app bundle is a one-liner).
  cat > "$ROOT/mamidlabs-launch" <<EOF
#!/bin/bash
export MAMIDLABS_ROOT="$ROOT"
exec "$venv_dir/bin/python" -m mamidlabs "\$@"
EOF
  chmod +x "$ROOT/mamidlabs-launch"

  if [ "$NO_DESKTOP" -eq 0 ]; then
    install_app_bundle
  fi
}

install_app_bundle() {
  local version app_dir
  version="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$REPO_DIR/mamidlabs/__init__.py" 2>/dev/null | head -1)"
  [ -n "$version" ] || version="1.0.0"
  app_dir="$HOME/Applications/MamidLabs.app"
  mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"
  sed "s|@VERSION@|$version|g" "$REPO_DIR/packaging/Info.plist" > "$app_dir/Contents/Info.plist"
  sed "s|@ROOT@|$ROOT|g" "$REPO_DIR/packaging/MacOS-MamidLabs" > "$app_dir/Contents/MacOS/MamidLabs"
  chmod +x "$app_dir/Contents/MacOS/MamidLabs"

  if have_cmd sips && have_cmd iconutil && [ -f "$REPO_DIR/packaging/mamidlabs.png" ]; then
    local iconset="$ROOT/tools/mamidlabs.iconset"
    rm -rf "$iconset"; mkdir -p "$iconset"
    for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
                "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" "512 icon_256x256@2x" \
                "512 icon_512x512" "1024 icon_512x512@2x"; do
      set -- $spec
      sips -z "$1" "$1" "$REPO_DIR/packaging/mamidlabs.png" --out "$iconset/$2.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$iconset" -o "$app_dir/Contents/Resources/mamidlabs.icns" >/dev/null 2>&1 || true
  fi
  touch "$app_dir"
  log "Application bundle installed: $app_dir"
}

stage_llama() {
  log "Downloading llama.cpp ($LLAMA_BUILD) (Metal)"
  local dir="$ROOT/llama.cpp/$LLAMA_BUILD"
  if [ -x "$dir/llama-server" ] && [ "$FORCE" -eq 0 ]; then
    log "llama-server already present; skipping."
    return
  fi
  mkdir -p "$dir"
  local asset url tmp arch
  arch="$(uname -m)"
  if [ "$arch" = "arm64" ]; then
    asset="llama-${LLAMA_BUILD}-bin-macos-arm64.zip"
  else
    asset="llama-${LLAMA_BUILD}-bin-macos-x64.zip"
  fi
  url="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_BUILD}/${asset}"
  tmp="$ROOT/tools/downloads/llama.zip"
  mkdir -p "$(dirname "$tmp")"
  log "Downloading: $url"
  if have_cmd curl; then curl -fL --retry 3 -o "$tmp" "$url"; else die "curl is required"; fi
  (cd "$dir" && unzip -o -j "$tmp" 'llama-server' '*.dylib' '*.metallib' '*.metal' >/dev/null 2>&1 || true)
  # Some archives keep the binary in a subfolder.
  if [ ! -x "$dir/llama-server" ]; then
    find "$dir" -name 'llama-server' -type f -exec cp {} "$dir/llama-server" \; || true
  fi
  chmod +x "$dir/llama-server" 2>/dev/null || true
  [ -x "$dir/llama-server" ] || die "llama-server could not be extracted ($url)"
}

stage_python() {
  log "Preparing virtual environments"
  # On macOS torch wheels ship with MPS (Metal) built in; no extra index needed.
  if [ "$SKIP_MEDIA" -eq 0 ]; then
    local venv_dir="$ROOT/venv/imagegen"
    "$PYTHON" -m venv --upgrade-deps "$venv_dir"
    "$venv_dir/bin/python" -m pip install --quiet --upgrade pip
    "$venv_dir/bin/python" -m pip install --quiet torch torchvision torchaudio
    "$venv_dir/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements/imagegen.txt"
  fi
  if [ "$SKIP_AUDIO" -eq 0 ]; then
    local venv_dir="$ROOT/venv/asr"
    "$PYTHON" -m venv --upgrade-deps "$venv_dir"
    "$venv_dir/bin/python" -m pip install --quiet --upgrade pip
    "$venv_dir/bin/python" -m pip install --quiet torch torchaudio
    "$venv_dir/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements/asr.txt"
  fi
  if [ "$SKIP_OCR" -eq 0 ]; then
    local venv_dir="$ROOT/venv/ocr"
    "$PYTHON" -m venv --upgrade-deps "$venv_dir"
    "$venv_dir/bin/python" -m pip install --quiet --upgrade pip
    "$venv_dir/bin/python" -m pip install --quiet paddlepaddle
    "$venv_dir/bin/python" -m pip install --quiet -r "$REPO_DIR/requirements/ocr.txt"
  fi
}

stage_comfyui() {
  [ "$SKIP_MEDIA" -eq 0 ] || { log "Skipping ComfyUI (--skip-media)"; return; }
  have_cmd git || { warn "git not found; skipping ComfyUI."; return; }
  log "Preparing ComfyUI ($COMFY_COMMIT)"
  local dir="$ROOT/ComfyUI"
  if [ -d "$dir/.git" ]; then
    (cd "$dir" && git fetch --quiet --tags origin && git checkout --quiet "$COMFY_COMMIT")
  else
    git clone --quiet "$COMFY_REPO" "$dir"
    (cd "$dir" && git checkout --quiet "$COMFY_COMMIT")
  fi
  local nodes="$dir/custom_nodes"
  mkdir -p "$nodes"
  clone_node() {
    local url="$1" commit="$2" name="$3"
    if [ -d "$nodes/$name/.git" ]; then
      (cd "$nodes/$name" && git fetch --quiet origin && git checkout --quiet "$commit")
    else
      git clone --quiet "$url" "$nodes/$name"
      (cd "$nodes/$name" && git checkout --quiet "$commit")
    fi
  }
  clone_node "https://github.com/city96/ComfyUI-GGUF.git" "$COMFY_GGUF_COMMIT" "ComfyUI-GGUF"
  clone_node "https://github.com/conradlocke/comfyui-krea2edit.git" "$KREA2EDIT_COMMIT" "comfyui-krea2edit"
  log "Installing ComfyUI dependencies"
  "$ROOT/venv/imagegen/bin/python" -m pip install --quiet -r "$dir/requirements.txt" || \
    warn "ComfyUI requirements installation partially failed."
}

stage_models() {
  [ "$SKIP_MODELS" -eq 0 ] || { log "Skipping the model download (--skip-models)"; return; }
  [ -n "$PROFILE" ] || { log "No profile given (--profile); model download skipped."; return; }
  log "Downloading profile models: $PROFILE"
  "$ROOT/venv/app/bin/python" - "$PROFILE" <<'PY'
import sys
sys.path.insert(0, ".")
from mamidlabs.core.paths import Paths
from mamidlabs.core.profiles import get_profile
from mamidlabs.core.runner import WorkerRunner
from mamidlabs.core.settings import Settings

profile_id = sys.argv[1]
paths = Paths()
paths.ensure_dirs()
settings = Settings(paths)
runner = WorkerRunner(paths, settings)
profile = get_profile(profile_id)
for item in profile.files:
    target = paths.root / item.target
    if target.exists():
        print(f"exists: {item.target}")
        continue
    payload = {"action": "download", "repo": item.repo, "revision": item.revision,
               "filename": item.filename, "target": str(target),
               "bytes": item.bytes, "sha256": item.sha256,
               "mtp": ({"repo": item.mtp_repo} if item.mtp_repo else None)}
    result = runner.run("hf-hub.py", payload, env_name="app", timeout=7200)
    if result.get("error"):
        print(f"ERROR {item.target}: {result['error']}")
    else:
        print(f"downloaded: {item.target}")
PY
}

stage_verify() {
  log "Verifying the installation"
  local ok=1
  "$ROOT/venv/app/bin/python" -c 'import mamidlabs; print("mamidlabs", mamidlabs.__version__)' || ok=0
  [ -x "$ROOT/llama.cpp/$LLAMA_BUILD/llama-server" ] || { warn "llama-server missing"; ok=0; }
  if [ "$SKIP_MEDIA" -eq 0 ]; then
    [ -f "$ROOT/ComfyUI/main.py" ] || { warn "ComfyUI missing"; ok=0; }
  fi
  "$ROOT/venv/app/bin/python" -m mamidlabs doctor || ok=0
  [ "$ok" -eq 1 ] && log "Installation complete." || warn "The installation finished with missing pieces; see the 'mamidlabs doctor' output."
}

# --- main --------------------------------------------------------------------
detect_python || die "Python 3.11–3.13 not found. Install: brew install python@3.12"
ROOT="$(abs_path "$PYTHON" "$ROOT")"
export MAMIDLABS_ROOT="$ROOT"

mkdir -p "$ROOT/tools/downloads" "$ROOT/logs"
log "Install root: $ROOT"
log "Stages: $STAGES"

# Interface language (wizard/CLI): written to settings/api.json; read at app start.
if [ -n "$LANGUAGE" ]; then
  mkdir -p "$ROOT/settings"
  "$PYTHON" - "$ROOT/settings/api.json" "$LANGUAGE" <<'PY'
import json, os, sys
path, lang = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {}
if not isinstance(data, dict):
    data = {}
data["language"] = lang
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
PY
fi

# The wizard's progress source: line 1 = step number, line 2 = total, line 3 = name.
progress_file="$ROOT/logs/kurulum-adim.txt"
total=0
for stage in preflight layout llama python comfyui models verify; do
  has_stage "$stage" && total=$((total + 1))
done
index=0
for stage in preflight layout llama python comfyui models verify; do
  has_stage "$stage" || continue
  index=$((index + 1))
  printf '%s\n%s\n%s\n' "$index" "$total" "$stage" > "$progress_file"
  "stage_${stage}"
done
printf '%s\n%s\n%s\n' "$total" "$total" "verify" > "$progress_file"

# Summary: the wizard's last page shows this file.
{
  echo "MamidLabs install summary"
  echo "Root: $ROOT"
  echo "Stages: $STAGES"
  [ -n "$PROFILE" ] && echo "Profile: $PROFILE"
  [ -n "$LANGUAGE" ] && echo "Language: $LANGUAGE"
  echo
  if [ -x "$ROOT/venv/app/bin/python" ]; then
    "$ROOT/venv/app/bin/python" -m mamidlabs doctor 2>&1 || true
  fi
} > "$ROOT/logs/kurulum-ozeti.txt"

log "Done. To start: $ROOT/mamidlabs-launch (or ~/Applications/MamidLabs.app)"
