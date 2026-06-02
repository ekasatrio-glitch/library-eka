#!/usr/bin/env bash
# Launch web server + watcher. Logs in ./logs/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -d venv ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

mkdir -p logs

PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

echo "[run] starting watcher..."
python -m app.ingest.watcher >> logs/watcher.log 2>&1 &
WATCHER_PID=$!
echo "[run] watcher pid=$WATCHER_PID"

cleanup() {
  echo "[run] shutting down..."
  kill "$WATCHER_PID" 2>/dev/null || true
  wait "$WATCHER_PID" 2>/dev/null || true
}
trap cleanup INT TERM

echo "[run] starting web on ${HOST}:${PORT}..."
exec python -m uvicorn app.web.app:app --host "$HOST" --port "$PORT"
