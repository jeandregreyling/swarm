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
echo ""
echo "[Swarm] PORT/BANNER MAPPING IS FIXED:"
echo "  5050 → Fridays (PROD)"
echo "  5051 → Mondays (DEV)"
echo "  5053 → Wednesdays (UAT)"
echo "If you change a port, update all banners and scripts."

