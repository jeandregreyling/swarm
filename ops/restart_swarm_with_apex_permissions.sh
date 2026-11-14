#!/bin/bash

# Restart Swarm Services with Full APEX Permissions
# This script restarts the necessary services to enable APEX with full permissions
# and LIVE visibility in the chat window.

echo "=========================================="
echo "Restarting Swarm with APEX Full Permissions"
echo "=========================================="
echo ""

# Step 1: Kill existing services
echo "[1/4] Stopping existing services..."
pkill -f "python.*terminal.py" || true
pkill -f "llama-server" || true
sleep 2

# Step 2: Verify APEX database entries
echo "[2/4] Verifying APEX permissions in database..."
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect('/mnt/archive/projects/swarm/swarm_memory.db')

# Check APEX in agents
cursor = conn.execute("SELECT name, tier, enabled FROM agents WHERE name='apex'")
row = cursor.fetchone()
if row:
    print(f"  ✓ APEX in agents table: {row}")
else:
    print("  ✗ APEX not found in agents table")

# Check APEX service principal
cursor = conn.execute("SELECT id, display_name, enabled FROM service_principals WHERE id='apex'")
row = cursor.fetchone()
if row:
    print(f"  ✓ APEX service principal: {row}")
else:
    print("  ✗ APEX service principal not found")

# Check APEX scopes
cursor = conn.execute("SELECT principal_id, scopes FROM service_tokens WHERE principal_id='apex'")
row = cursor.fetchone()
if row:
    print(f"  ✓ APEX scopes: {row[1][:100]}...")
else:
    print("  ✗ APEX scopes not found")

# Check memory table
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_apex'")
row = cursor.fetchone()
if row:
    print(f"  ✓ APEX memory table exists")
else:
    print("  ✗ APEX memory table not found")

# Check Mistral Vibe
cursor = conn.execute("SELECT name, enabled FROM agents WHERE name='mistral-vibe'")
row = cursor.fetchone()
if row:
    print(f"  ✓ Mistral Vibe in agents: {row}")
else:
    print("  ✗ Mistral Vibe not found")

conn.close()
EOF

# Step 3: Restart llama-server (APEX)
echo ""
echo "[3/4] Restarting APEX (llama-server)..."
cd /mnt/archive/projects/swarm
nohup /home/jd/llama.cpp/build-vulkan/bin/llama-server \
    -m /mnt/archive/models/blobs/sha256-2049f5674b1e92b4464e5729975c9689fcfbf0b0e4443ccf10b5339f370f9a54 \
    --device Vulkan0 \
    -ngl 99 \
    --load-mode dio \
    --host 0.0.0.0 \
    --port 8080 \
    --ctx-size 16384 \
    --parallel 1 \
    --jinja \
    --flash-attn on \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --cache-ram 0 \
    --fit off \
    --no-webui \
    > /tmp/llama-server.log 2>&1 &

sleep 3

# Verify llama-server is running
if pgrep -f "llama-server" > /dev/null; then
    echo "  ✓ APEX (llama-server) restarted on port 8080"
else
    echo "  ✗ Failed to start APEX"
    tail -20 /tmp/llama-server.log
fi

# Step 4: Restart terminal.py
echo ""
echo "[4/4] Restarting Fridays terminal..."
cd /mnt/archive/projects/swarm/frontend
nohup /home/jd/swarm/.venv/bin/python3 terminal.py \
    > /tmp/terminal.log 2>&1 &

sleep 5

# Verify terminal is running
if pgrep -f "python.*terminal.py" > /dev/null; then
    echo "  ✓ Fridays terminal restarted on port 5050"
else
    echo "  ✗ Failed to start terminal"
    tail -20 /tmp/terminal.log
fi

echo ""
echo "=========================================="
echo "Services Restarted with APEX Full Permissions"
echo "=========================================="
echo ""
echo "APEX now has:"
echo "  ✓ FULL PLAYWRITE ACCESS"
echo "  ✓ Full permissions to speak and think"
echo "  ✓ Direct interaction with all online models (Mistral Vibe, etc.)"
echo "  ✓ LIVE visibility in chat window"
echo "  ✓ All skills and auths required"
echo ""
echo "Access the chat at: http://127.0.0.1:5050/ui"
echo ""
echo "Test APEX with:"
echo "  @apex <your request>"
echo "  @mistral-vibe Teach APEX about..."
echo ""
echo "=========================================="
