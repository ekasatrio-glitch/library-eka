#!/usr/bin/env bash
# Snapshot the SQLite DB while idle, then rsync over SSH to VPS.
# Env (override at call site or in .env):
#   DB_PATH         (default: data/library.db)
#   VPS_USER, VPS_HOST, VPS_PATH    (required)
#   VPS_SSH_PORT    (default: 22)
#   LOCK_FILE       (default: $DB_PATH.sync.lock)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi

DB_PATH="${DB_PATH:-data/library.db}"
SNAP_PATH="${DB_PATH}.snapshot"
LOCK_FILE="${LOCK_FILE:-${DB_PATH}.sync.lock}"
VPS_SSH_PORT="${VPS_SSH_PORT:-22}"

if [ -z "${VPS_USER:-}" ] || [ -z "${VPS_HOST:-}" ] || [ -z "${VPS_PATH:-}" ]; then
  echo "[sync] missing VPS_USER / VPS_HOST / VPS_PATH; aborting" >&2
  exit 2
fi

if [ ! -f "$DB_PATH" ]; then
  echo "[sync] DB not found: $DB_PATH" >&2
  exit 1
fi

# Best-effort serialization with the ingestion worker.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[sync] another sync is running; exit." >&2
  exit 0
fi

echo "[sync] creating snapshot..."
# Use sqlite's VACUUM INTO for a consistent copy that's also compact.
rm -f "$SNAP_PATH"
sqlite3 "$DB_PATH" "VACUUM INTO '$SNAP_PATH';"

echo "[sync] rsync -> ${VPS_USER}@${VPS_HOST}:${VPS_PATH}"
rsync -avz --partial --progress \
  -e "ssh -p ${VPS_SSH_PORT}" \
  "$SNAP_PATH" \
  "${VPS_USER}@${VPS_HOST}:${VPS_PATH}"

echo "[sync] done."
