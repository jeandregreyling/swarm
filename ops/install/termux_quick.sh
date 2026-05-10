#!/data/data/com.termux/files/usr/bin/env bash
# termux_quick.sh — one-liner bootstrap for Samsung/Termux Hive nodes.
# Paste this ONE line into Termux:
#   curl -fsSL http://100.87.66.45:5050/api/hive/install/t | bash
#
# Or even shorter:
#   curl -fsSL 100.87.66.45:5050/api/hive/install/t | bash

set -e
L="${SWARM_HIVE_LEADER:-http://100.87.66.45:5050}"
N="${SWARM_NODE_ID:-potato-2}"
echo "[hive] leader=$L node=$N"
curl -fsSL "$L/api/hive/install/bootstrap.sh" | SWARM_HIVE_LEADER="$L" SWARM_NODE_ID="$N" bash
