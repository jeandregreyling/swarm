#!/bin/bash
# seven.sh — Linux launcher for the Seven .desktop entry.
# Launch priority:
#   1. Native Tauri binary (desktop/src-tauri/target/release/sevens-swarm)
#   2. Chromium --app=URL (own window, no tabs)
#   3. Firefox with dedicated profile
# Waits for swarm-terminal /_health before launching.

set -u
URL="${SEVEN_URL:-http://127.0.0.1:5050/ui}"
HEALTH="${SEVEN_HEALTH:-http://127.0.0.1:5050/_health}"
PROFILE_DIR="${SEVEN_BROWSER_PROFILE:-$HOME/.seven-chromium}"
LOG="${SEVEN_LAUNCH_LOG:-$HOME/.cache/seven-launch.log}"
TAURI_BIN="${SEVEN_TAURI_BIN:-/home/seven/swarm/desktop/src-tauri/target/release/sevens-swarm}"
mkdir -p "$(dirname "$LOG")" "$PROFILE_DIR"
exec >> "$LOG" 2>&1
echo "=== $(date -Iseconds) seven.sh launch ==="

# 1. Nudge swarm-terminal if down (user scope, non-fatal).
if command -v systemctl >/dev/null 2>&1; then
  if ! systemctl is-active --quiet swarm-terminal 2>/dev/null; then
    echo "swarm-terminal not active — user start attempt (non-fatal)"
    systemctl --user start swarm-terminal 2>/dev/null || true
  fi
fi

# 2. Wait up to 25s for /_health.
for i in $(seq 1 25); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$HEALTH" 2>/dev/null || echo 000)
  [ "$code" = "200" ] && { echo "health ok after ${i}s"; break; }
  sleep 1
done

# 3. Prefer native Tauri binary.
if [ -x "$TAURI_BIN" ] && [ "${SEVEN_FORCE_BROWSER:-0}" != "1" ]; then
  echo "launching tauri: $TAURI_BIN"
  exec "$TAURI_BIN"
fi

# 4. Chromium --app mode.
BIN=""
for candidate in chromium chromium-browser google-chrome brave-browser; do
  if command -v "$candidate" >/dev/null 2>&1; then BIN="$candidate"; break; fi
done
if [ -n "$BIN" ]; then
  echo "launching $BIN --app=$URL"
  exec "$BIN" \
    --app="$URL" \
    --user-data-dir="$PROFILE_DIR" \
    --class=Seven \
    --name=Seven \
    --no-first-run \
    --no-default-browser-check
fi

# 5. Firefox fallback.
if command -v firefox >/dev/null 2>&1; then
  FX_PROFILE="$HOME/.seven-firefox"
  [ -d "$FX_PROFILE" ] || firefox --headless --CreateProfile "seven-app $FX_PROFILE" >/dev/null 2>&1 || true
  echo "falling back to firefox"
  exec firefox --profile "$FX_PROFILE" --no-remote --new-window "$URL" --class Seven --name Seven
fi

echo "no launcher available — install chromium, firefox, or build the Tauri binary" >&2
exit 1
