#!/usr/bin/env bash
# install_linux.sh — install the Swarm Hive agent as a user systemd unit.
#
# Usage:
#   SWARM_HIVE_LEADER=http://leader.local:5050 ./install_linux.sh
#
# Optional env:
#   SWARM_HIVE_LEADER   leader URL (default http://localhost:5050)
#   SWARM_NODE_ID       node id override (default auto)
#   SWARM_HIVE_INTERVAL seconds between samples (default 30)
#   SWARM_HIVE_PYTHON   python interpreter (default python3)
#
# Idempotent: re-running upgrades the unit and restarts the service.

set -euo pipefail

LEADER="${SWARM_HIVE_LEADER:-http://localhost:5050}"
INTERVAL="${SWARM_HIVE_INTERVAL:-30}"
NODE_ID="${SWARM_NODE_ID:-}"
PY="${SWARM_HIVE_PYTHON:-python3}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AGENT="$REPO_ROOT/ops/hive_agent.py"

# When invoked from bootstrap.sh, REPO_ROOT *is* the stage dir and
# already contains core/hive/ from the tarball. When invoked from a
# checkout, the repo root provides core/hive/ natively. Either way,
# adding REPO_ROOT to PYTHONPATH makes ``import core.hive`` work.
STAGE_PY_PATH="${SWARM_HIVE_STAGE:-$REPO_ROOT}"

if [[ ! -f "$AGENT" ]]; then
    echo "[install_linux] agent not found at $AGENT" >&2
    exit 2
fi

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "[install_linux] python interpreter '$PY' not found in PATH" >&2
    exit 3
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/swarm-hive-agent.service"
mkdir -p "$UNIT_DIR"

ENV_LINES="Environment=SWARM_HIVE_LEADER=$LEADER
Environment=PYTHONPATH=$STAGE_PY_PATH"
if [[ -n "$NODE_ID" ]]; then
    ENV_LINES+=$'\n'"Environment=SWARM_NODE_ID=$NODE_ID"
fi

cat >"$UNIT_FILE" <<UNIT
[Unit]
Description=Swarm Hive node agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
$ENV_LINES
ExecStart=$PY $AGENT --run --interval $INTERVAL
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
UNIT

echo "[install_linux] wrote $UNIT_FILE"

systemctl --user daemon-reload
echo "[install_linux] enrolling with leader=$LEADER ..."
PYTHONPATH="$STAGE_PY_PATH" "$PY" "$AGENT" --enrol --leader "$LEADER" ${NODE_ID:+--node-id "$NODE_ID"}
systemctl --user enable --now swarm-hive-agent.service
sleep 1
systemctl --user --no-pager status swarm-hive-agent.service | head -20 || true

echo
echo "[install_linux] done. Tail logs with:"
echo "  journalctl --user -u swarm-hive-agent.service -f"
