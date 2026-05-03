#!/usr/bin/env bash
# install_macos.sh — install the Swarm Hive agent as a launchd LaunchAgent.
#
# Usage:
#   SWARM_HIVE_LEADER=http://leader.local:5050 ./install_macos.sh
#
# Optional env (same as Linux installer):
#   SWARM_HIVE_LEADER, SWARM_NODE_ID, SWARM_HIVE_INTERVAL, SWARM_HIVE_PYTHON

set -euo pipefail

LEADER="${SWARM_HIVE_LEADER:-http://localhost:5050}"
INTERVAL="${SWARM_HIVE_INTERVAL:-30}"
NODE_ID="${SWARM_NODE_ID:-}"
PY="${SWARM_HIVE_PYTHON:-python3}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AGENT="$REPO_ROOT/ops/hive_agent.py"

if [[ ! -f "$AGENT" ]]; then
    echo "[install_macos] agent not found at $AGENT" >&2
    exit 2
fi

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "[install_macos] python interpreter '$PY' not found in PATH" >&2
    exit 3
fi

LABEL="com.swarm.hive.agent"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/swarm-hive"
mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"

NODE_ENV=""
if [[ -n "$NODE_ID" ]]; then
    NODE_ENV="<key>SWARM_NODE_ID</key><string>$NODE_ID</string>"
fi

cat >"$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$AGENT</string>
    <string>--run</string>
    <string>--interval</string>
    <string>$INTERVAL</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>SWARM_HIVE_LEADER</key><string>$LEADER</string>
    $NODE_ENV
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/agent.out.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/agent.err.log</string>
</dict>
</plist>
PLIST

echo "[install_macos] wrote $PLIST"

echo "[install_macos] enrolling with leader=$LEADER ..."
"$PY" "$AGENT" --enrol --leader "$LEADER" ${NODE_ID:+--node-id "$NODE_ID"}

# Reload (bootout is allowed to fail if not previously loaded)
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo
echo "[install_macos] done. Tail logs with:"
echo "  tail -f $LOG_DIR/agent.out.log"
