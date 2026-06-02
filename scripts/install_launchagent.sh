#!/usr/bin/env bash
# Install the watcher LaunchAgent for the current user on macOS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$ROOT/scripts/com.eka.library.watcher.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.eka.library.watcher.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

# Substitute project dir into the plist template.
sed "s|REPLACE_WITH_PROJECT_DIR|${ROOT}|g" "$PLIST_SRC" > "$PLIST_DST"

# Reload if already loaded.
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"

echo "[install] installed: $PLIST_DST"
echo "[install] status:"
launchctl list | grep com.eka.library.watcher || true
