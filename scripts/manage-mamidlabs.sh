#!/bin/bash
# Manage the local model (start/stop/switch), ComfyUI and install health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT="${MAMIDLABS_ROOT:-$HOME/Library/Application Support/mamidlabs}"

usage() {
  cat <<'EOF'
Kullanım: manage-mamidlabs.sh <eylem> [profil]

Eylemler:
  start [profil]   Yerel modeli başlat (max|flash|lite; varsayılan ayardaki)
  stop             Yerel modeli durdur
  switch [profil]  Profil değiştir (start ile aynı; farkı yok)
  status           Etkin profili göster
  closecomfy       Boştaki ComfyUI'yi kapat
  comfy            ComfyUI'yi başlat (yalnızca medya üretimi için)
  doctor           Kurulumu denetle
  profiles         Profil durumunu göster
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
    [[ -x "$python" ]] || { echo "imagegen ortamı yok (kurulum --skip-media olabilir)." >&2; exit 1; }
    extra=""
    [[ -f "$ROOT/settings/comfy-extra-models.yaml" ]] && extra="--extra-model-paths-config $ROOT/settings/comfy-extra-models.yaml"
    mkdir -p "$ROOT/logs"
    nohup "$python" "$ROOT/ComfyUI/main.py" --listen 127.0.0.1 --port 8188 $extra \
      >"$ROOT/logs/comfyui.out.log" 2>"$ROOT/logs/comfyui.err.log" &
    echo "ComfyUI başlatıldı (PID $!) : http://127.0.0.1:8188"
    ;;
  ""|-h|--help) usage ;;
  *) echo "bilinmeyen eylem: $action" >&2; usage; exit 2 ;;
esac
