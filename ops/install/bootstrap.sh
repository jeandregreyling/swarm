#!/usr/bin/env bash
# bootstrap.sh — one-liner installer for a Swarm Hive node.
#
# Usage:
#   curl -fsSL http://<leader>:5050/api/hive/install/bootstrap.sh | bash
#   curl -fsSL http://<leader>:5050/api/hive/install/bootstrap.sh \
#       | SWARM_HIVE_LEADER=http://<leader>:5050 bash
#
# Detects platform, fetches the agent + installer from the leader, and
# runs the appropriate installer. No git clone required.
#
# Env:
#   SWARM_HIVE_LEADER   Override leader URL (default: derived from how
#                       you fetched this script if possible, else
#                       http://localhost:5050)
#   SWARM_NODE_ID       Optional node id pin
#   SWARM_HIVE_INTERVAL Sample interval seconds (default 30)
#   SWARM_HIVE_PYTHON   Python interpreter (default python3)

set -euo pipefail

LEADER="${SWARM_HIVE_LEADER:-http://localhost:5050}"
LEADER="${LEADER%/}"
PY="${SWARM_HIVE_PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1; then
        PY="python"
    else
        echo "[bootstrap] no python interpreter found (tried '$PY' and 'python')" >&2
        exit 3
    fi
fi

if ! command -v curl >/dev/null 2>&1; then
    echo "[bootstrap] curl not found in PATH" >&2
    exit 3
fi

case "$(uname -s)" in
    Linux*)
        # Termux on Android sets $PREFIX to /data/data/com.termux/files/usr.
        # Detect it before falling through to plain Linux so we can pick
        # the no-systemd installer path.
        if [[ -n "${PREFIX:-}" && "$PREFIX" == */com.termux/* ]]; then
            PLATFORM="termux"
        else
            PLATFORM="linux"
        fi
        ;;
    Darwin*)  PLATFORM="macos"   ;;
    *)        echo "[bootstrap] unsupported platform: $(uname -s) — for Windows use install_windows.ps1" >&2
              exit 4 ;;
esac

# Stage everything under a per-user dir so subsequent re-runs are
# idempotent and easy to inspect.
STAGE_DIR="${SWARM_HIVE_STAGE:-$HOME/.local/share/swarm-hive}"
mkdir -p "$STAGE_DIR/ops/install"

echo "[bootstrap] leader=$LEADER platform=$PLATFORM stage=$STAGE_DIR"

# 1) Agent + platform installer.
curl -fsSL "$LEADER/api/hive/install/agent.py"             -o "$STAGE_DIR/ops/hive_agent.py"
curl -fsSL "$LEADER/api/hive/install/install_${PLATFORM}.sh" -o "$STAGE_DIR/ops/install/install_${PLATFORM}.sh"
chmod +x "$STAGE_DIR/ops/hive_agent.py" "$STAGE_DIR/ops/install/install_${PLATFORM}.sh"

# 2) Runtime Python deps for the agent (core/hive tree). Fetched as a
# small built-on-demand tarball so we don't need a git clone.
echo "[bootstrap] fetching core/hive runtime ..."
curl -fsSL "$LEADER/api/hive/install/core_hive.tar.gz" -o "$STAGE_DIR/core_hive.tar.gz"
tar -xzf "$STAGE_DIR/core_hive.tar.gz" -C "$STAGE_DIR"
rm -f "$STAGE_DIR/core_hive.tar.gz"

# Run the platform installer from the stage dir. The installer locates
# the agent relative to itself (../hive_agent.py) and adds the stage
# dir to PYTHONPATH so ``import core.hive`` works.
SWARM_HIVE_LEADER="$LEADER" \
    SWARM_HIVE_PYTHON="$PY" \
    SWARM_HIVE_STAGE="$STAGE_DIR" \
    "$STAGE_DIR/ops/install/install_${PLATFORM}.sh"

echo
echo "[bootstrap] done. Files staged under $STAGE_DIR"
