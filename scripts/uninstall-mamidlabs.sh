#!/bin/bash
# MamidLabs (macOS) uninstaller.
#
# Removes everything the installer created under the install root, plus the
# MamidLabs.app bundle. Never touches anything outside the root.
#
#   --keep-user-data   keep settings/, chats/, models/, outputs/, tools/
#   --dry-run          show what would be removed, change nothing
#   --yes              do not ask for confirmation
set -euo pipefail

ROOT="${MAMIDLABS_ROOT:-$HOME/Library/Application Support/mamidlabs}"
KEEP_USER_DATA=0
DRY_RUN=0
ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage: uninstall-mamidlabs.sh [options]

  --root <path>       Install root (default: ~/Library/Application Support/mamidlabs)
  --keep-user-data    Keep settings/chats/models/outputs
  --dry-run           Only show what would be removed
  --yes               Do not ask for confirmation
  -h, --help          This text
EOF
}

log()  { printf '\033[1;34m[MamidLabs]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warning]\033[0m %s\n' "$*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --keep-user-data) KEEP_USER_DATA=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) warn "unknown option: $1"; usage; exit 2 ;;
  esac
done

export MAMIDLABS_ROOT="$ROOT"
ROOT="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$ROOT")"

# Safety: refuse to delete obviously wrong locations.
case "$ROOT" in
  "/"|"$HOME"|"/usr"|"/etc"|"/var"|"/opt"|"/tmp"|"/Applications"|"")
    warn "Safety: '$ROOT' will not be removed."; exit 1 ;;
esac
[[ "$ROOT" == "$HOME"/* ]] || [[ -n "${MAMIDLABS_ALLOW_OUTSIDE_HOME:-}" ]] || {
  warn "The install root is outside the home directory: $ROOT (force with MAMIDLABS_ALLOW_OUTSIDE_HOME=1)."
  exit 1
}

log "Install root: $ROOT"

# 1. Stop anything running from this root.
if [[ $DRY_RUN -eq 0 ]]; then
  for pid in $(pgrep -f "$ROOT" 2>/dev/null || true); do
    [[ "$pid" == "$$" ]] && continue
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in $(pgrep -f "$ROOT" 2>/dev/null || true); do
    [[ "$pid" == "$$" ]] && continue
    kill -9 "$pid" 2>/dev/null || true
  done
  log "Processes running from this root were stopped."
fi

# 2. Remove the .app bundle.
APP="$HOME/Applications/MamidLabs.app"
if [ -e "$APP" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then log "would remove: $APP"; else rm -rf "$APP"; log "removed: $APP"; fi
fi

# 3. Remove the root (or only program files when keeping user data).
if [[ ! -e "$ROOT" ]]; then
  log "The install root does not exist."
  exit 0
fi

if [[ $KEEP_USER_DATA -eq 1 ]]; then
  log "Keeping user data (--keep-user-data)."
  KEEP=(settings chats models outputs tools logs)
  if [[ $DRY_RUN -eq 1 ]]; then
    for entry in "$ROOT"/*; do
      base="$(basename "$entry")"
      for k in "${KEEP[@]}"; do [[ "$base" == "$k" ]] && continue 2; done
      log "would remove: $entry"
    done
  else
    for entry in "$ROOT"/*; do
      base="$(basename "$entry")"
      for k in "${KEEP[@]}"; do [[ "$base" == "$k" ]] && continue 2; done
      rm -rf "$entry"
    done
    log "Program files removed; user data kept."
  fi
  exit 0
fi

if [[ $ASSUME_YES -eq 0 && $DRY_RUN -eq 0 ]]; then
  read -r -p "The entire MamidLabs installation will be deleted ($ROOT). Continue? [y/N] " reply
  [[ "$reply" =~ ^[yYeE] ]] || { log "Cancelled."; exit 0; }
fi

if [[ $DRY_RUN -eq 1 ]]; then
  log "would remove: $ROOT (everything)"
else
  rm -rf "$ROOT"
  log "The installation was removed completely: $ROOT"
fi
