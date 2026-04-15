#!/usr/bin/env bash
# scripts/install.sh — Seven's Swarm installer (E.5.1)
# Usage: bash scripts/install.sh [--skip-ollama] [--skip-systemd]
set -euo pipefail

SKIP_OLLAMA=false
SKIP_SYSTEMD=false
for arg in "$@"; do
    case "$arg" in
        --skip-ollama)  SKIP_OLLAMA=true ;;
        --skip-systemd) SKIP_SYSTEMD=true ;;
    esac
done

SWARM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== Seven's Swarm Installer ==="
echo "Root: $SWARM_ROOT"

# 1. Check Python version
echo ""
echo "[1/7] Checking Python..."
PYTHON=""
for cmd in python3.12 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.12+ required. Found none."
    exit 1
fi
echo "  Found: $PYTHON ($($PYTHON --version))"

# 2. Create virtual environment
echo ""
echo "[2/7] Setting up virtual environment..."
if [ ! -d "$SWARM_ROOT/.venv" ]; then
    "$PYTHON" -m venv "$SWARM_ROOT/.venv"
    echo "  Created .venv"
else
    echo "  .venv already exists"
fi
source "$SWARM_ROOT/.venv/bin/activate"

# 3. Install dependencies
echo ""
echo "[3/7] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$SWARM_ROOT/requirements.txt"
echo "  Dependencies installed"

# 4. Generate .env template
echo ""
echo "[4/7] Generating environment template..."
"$PYTHON" "$SWARM_ROOT/scripts/generate_env.py"
if [ ! -f "$SWARM_ROOT/.env" ]; then
    cp "$SWARM_ROOT/.env.template" "$SWARM_ROOT/.env"
    # Set SWARM_ROOT in .env
    sed -i "s|SWARM_ROOT=.*|SWARM_ROOT=$SWARM_ROOT|" "$SWARM_ROOT/.env"
    echo "  Created .env from template — edit with your settings"
else
    echo "  .env already exists — skipping"
fi

# 5. Ollama models
if [ "$SKIP_OLLAMA" = false ]; then
    echo ""
    echo "[5/7] Checking Ollama..."
    if command -v ollama >/dev/null 2>&1; then
        echo "  Ollama found. Pulling base models..."
        for model in gemma3:latest llama3.2:latest; do
            echo "  Pulling $model..."
            ollama pull "$model" 2>/dev/null || echo "  Warning: failed to pull $model"
        done
    else
        echo "  Ollama not found — install from https://ollama.com"
        echo "  Skipping model pulls"
    fi
else
    echo ""
    echo "[5/7] Skipping Ollama (--skip-ollama)"
fi

# 6. Systemd services
if [ "$SKIP_SYSTEMD" = false ]; then
    echo ""
    echo "[6/7] Systemd services..."
    if [ -d /etc/systemd/system ] && [ "$(id -u)" -eq 0 ]; then
        for svc in swarm-terminal swarm-prewarm; do
            if [ -f "$SWARM_ROOT/$svc.service" ]; then
                cp "$SWARM_ROOT/$svc.service" /etc/systemd/system/
                echo "  Installed $svc.service"
            fi
        done
        systemctl daemon-reload
        echo "  Reloaded systemd"
    else
        echo "  Skipping systemd (not root or no systemd)"
        echo "  Run as root to install services"
    fi
else
    echo ""
    echo "[6/7] Skipping systemd (--skip-systemd)"
fi

# 7. Validate installation
echo ""
echo "[7/7] Validating installation..."
source "$SWARM_ROOT/.env" 2>/dev/null || true
export SWARM_ROOT
"$PYTHON" -c "
import sys
sys.path.insert(0, '$SWARM_ROOT')
from utils.config_validator import validate_config
ok, errors, warnings = validate_config()
if errors:
    for e in errors:
        print(f'  ERROR: {e}')
if warnings:
    for w in warnings:
        print(f'  WARN: {w}')
if ok:
    print('  Installation valid!')
else:
    print('  Installation has errors — check above')
"

echo ""
echo "=== Installation Complete ==="
echo "Start with: source .venv/bin/activate && python3 frontend/terminal.py"
echo "Or:         python3 scripts/desktop_launcher.py"
