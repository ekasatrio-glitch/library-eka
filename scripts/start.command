#!/usr/bin/env bash
# Double-click this file in Finder to launch library-eka:
#   ensures Ollama is running -> starts watcher + web -> opens the browser.
# Stop everything later with Ctrl-C in the Terminal window this opens.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

echo "[start] library-eka @ $ROOT"

# 1) Ensure Ollama (embeddings) is up.
if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[start] starting Ollama..."
  if [ -d "/Applications/Ollama.app" ]; then
    open -a Ollama
  else
    nohup ollama serve >/tmp/ollama.log 2>&1 &
  fi
  for _ in $(seq 1 30); do
    curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi

# 2) Open the browser once the web server answers.
(
  for _ in $(seq 1 40); do
    if curl -s --max-time 1 "http://$HOST:$PORT/" >/dev/null 2>&1; then
      open "http://$HOST:$PORT/"
      break
    fi
    sleep 1
  done
) &

# 3) Start watcher + web (run.sh execs uvicorn in the foreground; Ctrl-C stops both).
echo "[start] web -> http://$HOST:$PORT   (Ctrl-C di sini untuk berhenti)"
exec bash scripts/run.sh
