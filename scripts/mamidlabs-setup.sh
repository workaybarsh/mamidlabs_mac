#!/bin/bash
# MamidLabs kurulum sihirbazını başlatır (Python 3.12 + PySide6 / Qt6).
#
# Kurulu bir kök varsa onun venv'ini, yoksa sistem python3'ünü kullanır; böylece
# hem "git clone + ./scripts/mamidlabs-setup.sh" hem de kurulmuş sistemde
# "mamidlabs-setup" aynı sihirbazı açar. Seçenekler (--root, --lang) sihirbaza
# aynen geçirilir.
#
# macOS bash 3.2 ile uyumludur (bash 4+ özellikleri kullanılmaz).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT_DIR="${MAMIDLABS_ROOT:-$HOME/Library/Application Support/mamidlabs}"

PYTHON=""
if [ -x "$ROOT_DIR/venv/app/bin/python" ]; then
  PYTHON="$ROOT_DIR/venv/app/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
fi

if [ -z "$PYTHON" ]; then
  echo "[hata] python3 bulunamadı (brew install python@3.12)" >&2
  exit 1
fi

export PYTHONPATH="${REPO_DIR}${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m mamidlabs.wizard "$@"
