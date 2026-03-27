#!/bin/bash
# Seven's Swarm Start Script
# Brings all services back up

echo "=== Starting Seven's Swarm ==="
sudo systemctl start swarm-listener
sudo systemctl start swarm-monitor
echo "Core services started."
echo "Sniffles (sniffer) must be started manually:"
echo "  sudo systemctl start swarm-sniffer"
echo ""
echo "Status:"
sudo systemctl status swarm-listener --no-pager | grep Active
sudo systemctl status swarm-monitor --no-pager | grep Active
