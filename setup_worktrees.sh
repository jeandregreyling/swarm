#!/bin/bash
# setup_worktrees.sh — One-time setup for DEV/UAT/PROD isolation
# Run this ONCE as the seven user (it will sudo where needed).
#
# What this does:
#   1. Creates 'uat' and 'dev' git branches
#   2. Creates git worktrees at /home/seven/swarm-uat and /home/seven/swarm-dev
#   3. Updates the systemd service files for DEV and UAT to use their worktree paths
#   4. Restarts DEV and UAT servers
#
# After this runs:
#   PROD (5050) → /home/seven/swarm       → master branch   [never touched by agents]
#   UAT  (5053) → /home/seven/swarm-uat   → uat branch      [Ghost manual testing]
#   DEV  (5051) → /home/seven/swarm-dev   → dev branch      [agents work here]

set -e
SWARM="/home/seven/swarm"
UAT_DIR="/home/seven/swarm-uat"
DEV_DIR="/home/seven/swarm-dev"

echo "=== Swarm Worktree Setup ==="
cd "$SWARM"

# ── 1. Create branches if they don't exist ────────────────────────────────────
echo ""
echo "[1/5] Creating uat and dev branches..."

if git show-ref --verify --quiet refs/heads/uat; then
    echo "  uat branch already exists"
else
    git branch uat master
    echo "  uat branch created from master"
fi

if git show-ref --verify --quiet refs/heads/dev; then
    echo "  dev branch already exists"
else
    git branch dev master
    echo "  dev branch created from master"
fi

# ── 2. Create worktrees ───────────────────────────────────────────────────────
echo ""
echo "[2/5] Creating git worktrees..."

if [ -d "$UAT_DIR" ]; then
    echo "  $UAT_DIR already exists — skipping (remove it first if you need to recreate)"
else
    git worktree add "$UAT_DIR" uat
    echo "  Created: $UAT_DIR (uat branch)"
fi

if [ -d "$DEV_DIR" ]; then
    echo "  $DEV_DIR already exists — skipping"
else
    git worktree add "$DEV_DIR" dev
    echo "  Created: $DEV_DIR (dev branch)"
fi

# ── 3. Write updated systemd service files ────────────────────────────────────
echo ""
echo "[3/5] Updating systemd service files (requires sudo)..."

# UAT service
sudo tee /etc/systemd/system/swarm-terminal-uat.service > /dev/null << 'SVCEOF'
[Unit]
Description=Swarm Terminal - UAT - port 5053
After=network.target

[Service]
Type=simple
User=seven
WorkingDirectory=/home/seven/swarm-uat
Environment=PORT=5053
Environment=STAGE=UAT
Environment=SWARM_ROOT=/home/seven/swarm-uat
Environment=SWARM_DB_PATH=/home/seven/swarm/swarm_memory.db
EnvironmentFile=-/etc/environment
ExecStart=/usr/bin/python3 /home/seven/swarm-uat/frontend/terminal.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF
echo "  UAT service updated"

# DEV service
sudo tee /etc/systemd/system/swarm-terminal-dev.service > /dev/null << 'SVCEOF'
[Unit]
Description=Swarm Terminal - DEV - port 5051
After=network.target

[Service]
Type=simple
User=seven
WorkingDirectory=/home/seven/swarm-dev
Environment=PORT=5051
Environment=STAGE=DEV
Environment=SWARM_ROOT=/home/seven/swarm-dev
Environment=SWARM_DB_PATH=/home/seven/swarm/swarm_memory.db
EnvironmentFile=-/etc/environment
ExecStart=/usr/bin/python3 /home/seven/swarm-dev/frontend/terminal.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF
echo "  DEV service updated"

# ── 4. Reload systemd ─────────────────────────────────────────────────────────
echo ""
echo "[4/5] Reloading systemd..."
sudo systemctl daemon-reload
echo "  Done"

# ── 5. Restart DEV and UAT ────────────────────────────────────────────────────
echo ""
echo "[5/5] Restarting DEV and UAT servers..."
sudo systemctl restart swarm-terminal-uat
echo "  UAT restarted (port 5053)"
sudo systemctl restart swarm-terminal-dev
echo "  DEV restarted (port 5051)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Environment layout:"
echo "  PROD (5050) → $SWARM       → master branch"
echo "  UAT  (5053) → $UAT_DIR → uat branch"
echo "  DEV  (5051) → $DEV_DIR → dev branch"
echo ""
echo "The proposal pipeline is now active:"
echo "  Agent work  → DEV only (proposal/<id> branch)"
echo "  Ghost tests → UAT (via 'Approve to UAT' in Studio)"
echo "  Goes live   → PROD (via 'Promote to PROD' in Studio)"
echo ""
echo "PROD was NOT restarted and was NOT touched."
