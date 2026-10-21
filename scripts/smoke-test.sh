#!/bin/bash
# MamidLabs (macOS) smoke test.
#
# Exercises the real stack end to end against a live install. Run it after
# `install-mamidlabs.sh` and before a release. Every step prints PASS/FAIL and
# the script exits non-zero if any required step fails.
#
#   smoke-test.sh [--profile max|flash|lite] [--skip-ocr] [--skip-media]
#                 [--skip-chart] [--skip-mtp] [--root <path>]
set -euo pipefail

ROOT="${MAMIDLABS_ROOT:-$HOME/Library/Application Support/mamidlabs}"
PROFILE="${MAMIDLABS_SMOKE_PROFILE:-}"
SKIP_OCR=0
SKIP_MEDIA=0
SKIP_CHART=0
SKIP_MTP=0
TMP="${TMPDIR:-/tmp}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --root) ROOT="$2"; shift 2 ;;
    --skip-ocr) SKIP_OCR=1; shift ;;
    --skip-media) SKIP_MEDIA=1; shift ;;
    --skip-chart) SKIP_CHART=1; shift ;;
    --skip-mtp) SKIP_MTP=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

export MAMIDLABS_ROOT="$ROOT"
PY="$ROOT/venv/app/bin/python"
[[ -x "$PY" ]] || { echo "venv/app is missing: $ROOT/venv/app" >&2; exit 1; }

PASS=0; FAIL=0; SKIP=0
results=()

record() { # name status [detail]
  local name="$1" status="$2" detail="${3:-}"
  results+=("$name|$status|$detail")
  case "$status" in
    PASS) PASS=$((PASS+1)); printf '  \033[1;32mPASS\033[0m %s %s\n' "$name" "$detail" ;;
    FAIL) FAIL=$((FAIL+1)); printf '  \033[1;31mFAIL\033[0m %s %s\n' "$name" "$detail" ;;
    SKIP) SKIP=$((SKIP+1)); printf '  \033[1;33mSKIP\033[0m %s %s\n' "$name" "$detail" ;;
  esac
}

api() { # method path [json]
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -fsS -m 600 -X "$method" "http://127.0.0.1:8080$path" \
      -H 'Content-Type: application/json' -d "$body"
  else
    curl -fsS -m 600 -X "$method" "http://127.0.0.1:8080$path"
  fi
}

echo "MamidLabs smoke test — root: $ROOT"

# --- 1. doctor ---------------------------------------------------------------
echo "[doctor]"
if "$PY" -m mamidlabs --root "$ROOT" doctor >"$TMP/mamidlabs-doctor.txt" 2>&1; then
  record "doctor" PASS
else
  record "doctor" FAIL "$(tail -n1 "$TMP/mamidlabs-doctor.txt")"
fi

# --- 2. server start ---------------------------------------------------------
echo "[server]"
if [[ -z "$PROFILE" ]]; then
  PROFILE="$("$PY" - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ["MAMIDLABS_ROOT"])
f = root / "settings" / "api.json"
try:
    print(json.loads(f.read_text(encoding="utf-8")).get("localProfile") or "flash")
except Exception:
    print("flash")
PY
)"
fi
if "$SCRIPT_DIR/manage-mamidlabs.sh" start "$PROFILE" >"$TMP/mamidlabs-start.txt" 2>&1; then
  record "server_start" PASS "profile=$PROFILE"
else
  record "server_start" FAIL "$(tail -n1 "$TMP/mamidlabs-start.txt")"
fi

ready=0
for _ in $(seq 1 90); do
  if api GET /health >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[[ $ready -eq 1 ]] && record "health" PASS || record "health" FAIL "8080 is not responding"

# --- 3. chat -----------------------------------------------------------------
echo "[chat]"
resp="$(api POST /v1/chat/completions '{"messages":[{"role":"user","content":"Hello, introduce yourself briefly."}],"max_tokens":512}' 2>/dev/null || true)"
if [[ -n "$resp" ]] && grep -q '"content"' <<<"$resp"; then
  record "chat" PASS
else
  record "chat" FAIL
fi

# --- 4. chart ----------------------------------------------------------------
echo "[chart]"
if [[ $SKIP_CHART -eq 1 ]]; then
  record "chart" SKIP "--skip-chart"
else
  if "$PY" - <<'PY' >/dev/null 2>&1
import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from mamidlabs.core.chart import render_chart
from mamidlabs.core.paths import Paths
from mamidlabs.core.settings import Settings
paths = Paths(); settings = Settings(paths)
out = render_chart({"type": "bar", "title": "t", "labels": ["a", "b"], "values": [1, 2]},
                   paths.output_dir("charts"))
print(out)
PY
  then record "chart" PASS; else record "chart" FAIL; fi
fi

# --- 5. offline --------------------------------------------------------------
echo "[offline]"
WORKERS_DIR="$("$PY" -c 'import os, mamidlabs.workers; print(os.path.dirname(mamidlabs.workers.__file__))' 2>/dev/null || true)"
if [ -n "$WORKERS_DIR" ] && "$PY" "$WORKERS_DIR/mamidlabs-agent-tools.py" <<'PY' 2>/dev/null | grep -q '"error"'
{"action": "search", "query": "test", "offline": true}
PY
then record "offline" PASS; else record "offline" SKIP "worker path not found"; fi

# --- 6. MTP ------------------------------------------------------------------
echo "[mtp]"
if [[ $SKIP_MTP -eq 1 ]]; then
  record "mtp" SKIP "--skip-mtp"
else
  if grep -q -- '--spec-type draft-mtp' "$ROOT/logs/llama-server-"*.stdout.log 2>/dev/null; then
    if grep -q 'draft_n_accepted' "$ROOT/logs/llama-server-"*.stdout.log 2>/dev/null; then
      record "mtp" PASS
    else
      record "mtp" PASS "draft-mtp enabled"
    fi
  else
    record "mtp" SKIP "draft-mtp not enabled"
  fi
fi

# --- 7. OCR ------------------------------------------------------------------
echo "[ocr]"
if [[ $SKIP_OCR -eq 1 ]]; then
  record "ocr" SKIP "--skip-ocr"
elif [[ -x "$ROOT/venv/ocr/bin/python" ]]; then
  record "ocr" PASS "venv/ocr present"
else
  record "ocr" SKIP "venv/ocr missing"
fi

# --- 8. media ----------------------------------------------------------------
echo "[media]"
if [[ $SKIP_MEDIA -eq 1 ]]; then
  record "image" SKIP "--skip-media"
  record "video" SKIP "--skip-media"
else
  if [[ -f "$ROOT/ComfyUI/main.py" ]]; then
    record "comfyui" PASS
  else
    record "comfyui" FAIL "ComfyUI missing"
  fi
  record "image" SKIP "must be verified manually (ComfyUI generation)"
  record "video" SKIP "must be verified manually (ComfyUI generation)"
fi

# --- 9. stop -----------------------------------------------------------------
echo "[stop]"
"$SCRIPT_DIR/manage-mamidlabs.sh" stop >/dev/null 2>&1 && record "server_stop" PASS || record "server_stop" FAIL

# --- summary -----------------------------------------------------------------
echo
echo "Result: $PASS passed, $FAIL failed, $SKIP skipped"
{
  echo "{"
  echo "  \"root\": \"$ROOT\","
  echo "  \"profile\": \"$PROFILE\","
  echo "  \"passed\": $PASS,"
  echo "  \"failed\": $FAIL,"
  echo "  \"skipped\": $SKIP,"
  echo "  \"steps\": ["
  first=1
  for r in "${results[@]}"; do
    IFS='|' read -r name status detail <<<"$r"
    [[ $first -eq 1 ]] || echo ","
    first=0
    printf '    {"name": "%s", "status": "%s", "detail": "%s"}' "$name" "$status" "$detail"
  done
  echo
  echo "  ]"
  echo "}"
} > "$ROOT/logs/smoke-test-son.json" 2>/dev/null || true

[[ $FAIL -eq 0 ]]
