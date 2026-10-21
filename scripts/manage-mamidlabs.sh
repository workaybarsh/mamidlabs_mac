#!/bin/bash
# Manage the local model (start/stop/switch), ComfyUI and install health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT="${MAMIDLABS_ROOT:-$HOME/Library/Application Support/mamidlabs}"

usage() {
  cat <<'EOF'
Usage: manage-mamidlabs.sh <action> [profile]

Actions:
  start [profile]  Start the local model (max|flash|lite; default from settings)
  stop             Stop the local model
  switch [profile] Change the profile (same as start; no difference)
  status           Show the active profile
  closecomfy       Close the idle ComfyUI
  comfy            Start ComfyUI (media generation only)
  doctor           Inspect the installation
  profiles         Show the profile status
EOF
}

PY="$ROOT/venv/app/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"

action="${1:-}"
profile="${2:-}"
case "$action" in
  start|switch)
    if [[ -n "$profile" ]]; then
      exec "$PY" -m mamidlabs --root "$ROOT" manage start --profile "$profile"
    fi
    exec "$PY" -m mamidlabs --root "$ROOT" manage start
    ;;
  stop)       exec "$PY" -m mamidlabs --root "$ROOT" manage stop ;;
  status)     exec "$PY" -m mamidlabs --root "$ROOT" manage status ;;
  closecomfy) exec "$PY" -m mamidlabs --root "$ROOT" manage closecomfy ;;
  doctor)     exec "$PY" -m mamidlabs --root "$ROOT" doctor ;;
  profiles)   exec "$PY" -m mamidlabs --root "$ROOT" profiles ;;
  comfy)
    python="$ROOT/venv/imagegen/bin/python"
    [[ -x "$python" ]] || { echo "the imagegen environment is missing (the install may have used --skip-media)." >&2; exit 1; }
    extra=""
    [[ -f "$ROOT/settings/comfy-extra-models.yaml" ]] && extra="--extra-model-paths-config $ROOT/settings/comfy-extra-models.yaml"
    mkdir -p "$ROOT/logs"
    nohup "$python" "$ROOT/ComfyUI/main.py" --listen 127.0.0.1 --port 8188 $extra \
      >"$ROOT/logs/comfyui.out.log" 2>"$ROOT/logs/comfyui.err.log" &
    echo "ComfyUI started (PID $!) : http://127.0.0.1:8188"
    ;;
  ""|-h|--help) usage ;;
  *) echo "unknown action: $action" >&2; usage; exit 2 ;;
esac
