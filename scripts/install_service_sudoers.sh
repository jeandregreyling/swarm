#!/usr/bin/env bash
# Allow the Swarm UI user to restart the Swarm's own system services without a
# password. Only exact `systemctl <action> <unit>` commands for the units in the
# Services menu registry (frontend/blueprints/exec_bp.py) are permitted; no
# wildcards, so no other unit or argument can ride along.
#
# Usage:  sudo scripts/install_service_sudoers.sh [user]
#         sudo scripts/install_service_sudoers.sh --remove
set -euo pipefail

TARGET=/etc/sudoers.d/swarm-services
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo $0 $*" >&2
  exit 1
fi

if [[ "${1:-}" == "--remove" ]]; then
  rm -f "$TARGET"
  echo "Removed $TARGET"
  exit 0
fi

RUN_AS="${1:-${SUDO_USER:-}}"
if [[ -z "$RUN_AS" || "$RUN_AS" == root ]]; then
  echo "Give the UI user explicitly: sudo $0 <user>" >&2
  exit 1
fi
id "$RUN_AS" >/dev/null

SYSTEMCTL=/usr/bin/systemctl
UNITS=$(grep -oE "'id': '[A-Za-z0-9@_.-]+\.service'" "$ROOT/frontend/blueprints/exec_bp.py" \
  | sed -E "s/'id': '(.*)'/\1/" | sort -u)
[[ -n "$UNITS" ]] || { echo "No units found in exec_bp.py registry" >&2; exit 1; }

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
{
  echo "# Managed by $ROOT/scripts/install_service_sudoers.sh — Swarm Services menu"
  for unit in $UNITS; do
    for action in "restart" "restart --no-block" "start" "stop" "kill -s SIGKILL"; do
      echo "$RUN_AS ALL=(root) NOPASSWD: $SYSTEMCTL $action $unit"
    done
  done
} > "$TMP"

visudo -cf "$TMP" >/dev/null
install -m 0440 -o root -g root "$TMP" "$TARGET"
echo "Installed $TARGET for user '$RUN_AS' ($(echo "$UNITS" | wc -l) units)."
