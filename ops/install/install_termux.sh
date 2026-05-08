#!/data/data/com.termux/files/usr/bin/env bash
# install_termux.sh — install the Swarm Hive agent on Android via Termux.
#
# Usage (inside Termux):
#   SWARM_HIVE_LEADER=http://<leader-ip>:5050 ./install_termux.sh
#
# Termux has no systemd, so we run the agent under termux-services
# (runit) when available and fall back to a nohup-managed background
# process otherwise. Idempotent: re-running stops the old process and
# starts a fresh one.
#
# Required Termux packages: python, curl. termux-services is optional
# but recommended for boot-time autostart.
#
# Env:
#   SWARM_HIVE_LEADER    leader URL (default http://localhost:5050)
#   SWARM_NODE_ID        node id override (default auto)
#   SWARM_HIVE_INTERVAL  seconds between samples (default 30)
#   SWARM_HIVE_PYTHON    python interpreter (default python3)
#   SWARM_HIVE_STAGE     stage dir (default $HOME/.local/share/swarm-hive)

set -euo pipefail

LEADER="${SWARM_HIVE_LEADER:-http://localhost:5050}"
INTERVAL="${SWARM_HIVE_INTERVAL:-30}"
NODE_ID="${SWARM_NODE_ID:-}"
PY="${SWARM_HIVE_PYTHON:-python3}"

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AGENT="$REPO_ROOT/ops/hive_agent.py"
STAGE_PY_PATH="${SWARM_HIVE_STAGE:-$REPO_ROOT}"

if [[ ! -f "$AGENT" ]]; then
    echo "[install_termux] agent not found at $AGENT" >&2
    exit 2
fi

if ! command -v "$PY" >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1; then
        PY="python"
    else
        echo "[install_termux] python not found. Run: pkg install python" >&2
        exit 3
    fi
fi

RUN_DIR="$HOME/.local/state/swarm-hive"
LOG_DIR="$RUN_DIR/logs"
PID_FILE="$RUN_DIR/agent.pid"
mkdir -p "$RUN_DIR" "$LOG_DIR"

# Stop any previous instance.
if [[ -f "$PID_FILE" ]]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[install_termux] stopping previous agent (pid=$OLD_PID)"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi

echo "[install_termux] enrolling with leader=$LEADER ..."
PYTHONPATH="$STAGE_PY_PATH" "$PY" "$AGENT" --enrol --leader "$LEADER" ${NODE_ID:+--node-id "$NODE_ID"}

# Try termux-services (sv-enable) first; fall back to nohup.
SVDIR="${SVDIR:-$PREFIX/var/service}"
if command -v sv >/dev/null 2>&1 && [[ -d "$SVDIR" ]]; then
    SERVICE_DIR="$SVDIR/swarm-hive-agent"
    mkdir -p "$SERVICE_DIR/log"
    cat >"$SERVICE_DIR/run" <<RUN
#!$PREFIX/bin/sh
exec 2>&1
export SWARM_HIVE_LEADER="$LEADER"
export PYTHONPATH="$STAGE_PY_PATH"
if [ -n "$NODE_ID" ]; then export SWARM_NODE_ID="$NODE_ID"; fi
exec "$PY" "$AGENT" --run --interval "$INTERVAL"
RUN
    cat >"$SERVICE_DIR/log/run" <<LOGRUN
#!$PREFIX/bin/sh
exec svlogd -tt "$LOG_DIR"
LOGRUN
    chmod +x "$SERVICE_DIR/run" "$SERVICE_DIR/log/run"
    sv up swarm-hive-agent >/dev/null 2>&1 || true
    echo "[install_termux] registered swarm-hive-agent under termux-services"
    echo "[install_termux] tail logs with: tail -f $LOG_DIR/current"
else
    LOG_FILE="$LOG_DIR/agent.log"
    # ${NODE_ID:+VAR=val} cannot act as a bash env-prefix (the assignment
    # must be literal at parse time), so export it explicitly first.
    if [ -n "$NODE_ID" ]; then export SWARM_NODE_ID="$NODE_ID"; fi
    SWARM_HIVE_LEADER="$LEADER" \
        PYTHONPATH="$STAGE_PY_PATH" \
        nohup "$PY" "$AGENT" --run --interval "$INTERVAL" \
        >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    sleep 1
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "[install_termux] agent running (pid=$(cat "$PID_FILE"))"
        echo "[install_termux] tail logs with: tail -f $LOG_FILE"
    else
        echo "[install_termux] FAILED to start agent. Last log:" >&2
        tail -20 "$LOG_FILE" >&2 || true
        exit 5
    fi
fi

echo
echo "[install_termux] done. Stop with:"
echo "  kill \$(cat $PID_FILE)   # nohup mode"
echo "  sv down swarm-hive-agent  # termux-services mode"
