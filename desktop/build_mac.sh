#!/usr/bin/env bash
# desktop/build_mac.sh — One-command build for Seven on macOS.
#
# Copy this file to your Mac, make it executable, and run it.
# It downloads the latest source, builds the DMG, and opens it.
#
# Usage:
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
set -euo pipefail

LEADER="http://100.87.66.45:5050"
BUILD_DIR="$HOME/.seven_build"
DMG_PATH=""

echo "=== Seven Desktop — macOS Build ==="
echo ""

# 1. Check prerequisites
if ! command -v cargo >/dev/null 2>&1; then
    echo "Rust not found. Installing..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git is required. Install Xcode Command Line Tools:"
    echo "  xcode-select --install"
    exit 1
fi

# 2. Download source
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

if [ -d "swarm" ]; then
    echo "Updating existing source..."
    cd swarm && git pull
else
    echo "Downloading source..."
    git clone git@github.com:jeandregreyling/swarm.git
    cd swarm
fi

# 3. Install Tauri CLI
if ! cargo tauri --version >/dev/null 2>&1; then
    echo "Installing Tauri CLI..."
    cargo install tauri-cli --version '^2'
fi

# 4. Build
echo "Building Seven Desktop (this takes 3-5 minutes on first run)..."
cd desktop/src-tauri
cargo tauri build

# 5. Find DMG
DMG=$(find target/release/bundle/dmg -name '*.dmg' | head -1)
if [ -z "$DMG" ]; then
    echo "ERROR: DMG not found after build"
    exit 1
fi

echo ""
echo "=== Build Complete ==="
echo "DMG: $PWD/$DMG"
echo ""
echo "Installing..."

# 6. Mount and copy
MOUNT_POINT="/Volumes/Seven"
open "$DMG"
sleep 2

if [ -d "$MOUNT_POINT/Seven.app" ]; then
    cp -R "$MOUNT_POINT/Seven.app" /Applications/
    echo "Seven.app copied to /Applications"
else
    echo "Please drag Seven.app to Applications manually from the mounted DMG"
    open "$MOUNT_POINT"
    exit 0
fi

# 7. Unmount
hdiutil detach "$MOUNT_POINT" 2>/dev/null || true

echo ""
echo "=== Done ==="
echo "Seven is installed in /Applications/Seven.app"
echo "First launch: Right-click → Open (Gatekeeper workaround)"
echo ""
echo "Leader URL: $LEADER"
