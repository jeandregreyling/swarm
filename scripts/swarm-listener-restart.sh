#!/usr/bin/env bash
# swarm-listener-restart.sh — graceful restart for the listener daemon.
#
# S-398A356904 — restart with a soft drain instead of `systemctl kill -9`.
# Behaviour:
#   1. Set a drain marker file the listener checks at the top of its loop.
#   2. Wait up to LISTENER_DRAIN_TIMEOUT seconds (default 30) for the
#      listener to acknowledge by removing the marker.
#   3. systemctl restart swarm-listener (force if drain timed out).
#   4. Verify the unit is active+running before exit.
#
# Exit codes:
#   0  — restarted cleanly
#   2  — drain timed out, restarted forcefully
#   3  — restart failed / unit not active after restart
#
# Notes:
#   * This script never edits source code.
#   * Sudo is requested only for `systemctl`; the marker file lives in
#     the swarm runtime dir so it's writeable by the seven user.

set -u

SWARM_ROOT="${SWARM_ROOT:-/home/seven/swarm}"
DRAIN_FILE="${SWARM_ROOT}/run/listener-drain.flag"
TIMEOUT="${LISTENER_DRAIN_TIMEOUT:-30}"
UNIT="${LISTENER_UNIT:-swarm-listener.service}"

mkdir -p "$(dirname "$DRAIN_FILE")"

echo "[restart] requesting drain via $DRAIN_FILE (timeout=${TIMEOUT}s)..."
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$DRAIN_FILE"

drained=0
for ((i=0; i<TIMEOUT; i++)); do
  if [[ ! -f "$DRAIN_FILE" ]]; then
    drained=1
    echo "[restart] listener acknowledged drain after ${i}s"
    break
  fi
  sleep 1
done

if [[ "$drained" -eq 0 ]]; then
  echo "[restart] WARN: drain timeout — proceeding with hard restart"
  rm -f "$DRAIN_FILE"
fi

echo "[restart] sudo systemctl restart $UNIT"
if ! sudo systemctl restart "$UNIT"; then
  echo "[restart] ERROR: systemctl restart failed"
  exit 3
fi

# Verify
state="$(systemctl is-active "$UNIT" 2>/dev/null || true)"
if [[ "$state" != "active" ]]; then
  echo "[restart] ERROR: unit is '$state' after restart"
  exit 3
fi

echo "[restart] OK — $UNIT active"
if [[ "$drained" -eq 0 ]]; then
  exit 2
fi
exit 0
