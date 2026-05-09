#!/bin/bash
# Seven's Swarm Kill Switch
# Stops all swarm services instantly

set -euo pipefail

echo "=== Killing Seven's Swarm ==="
for unit in \
	swarm-terminal.service \
	swarm-terminal-prod.service \
	swarm-terminal-uat.service \
	swarm-terminal-dev.service \
	swarm-fridays.service \
	swarm-discord.service \
	swarm-telegram.service \
	swarm-prewarm.service \
	swarm-listener.service \
	swarm-monitor.service \
	swarm-sniffer.service
do
	sudo systemctl stop "$unit" 2>/dev/null || true
done

_SWARM_ROOT="${SWARM_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
python3 "${_SWARM_ROOT}/ollama_killswitch.py" --service || true
sudo fuser -k 5050/tcp 5051/tcp 5053/tcp 11434/tcp 2>/dev/null || true

echo "All swarm services stopped."
echo "To restart: sudo systemctl start swarm-terminal (or 'make wake-dev' / 'make wake-uat' for other stages)."
