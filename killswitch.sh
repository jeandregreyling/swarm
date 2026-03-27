#!/bin/bash
# Seven's Swarm Kill Switch
# Stops all swarm services instantly

echo "=== Killing Seven's Swarm ==="
sudo systemctl stop swarm-listener
sudo systemctl stop swarm-monitor
sudo systemctl stop swarm-sniffer
sudo killall python3 2>/dev/null
echo "All swarm services stopped."
echo "Run ~/swarm/startswarm.sh to restart."
