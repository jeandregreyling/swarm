#!/usr/bin/env bash
# desktop/build.sh — Tauri v2 build helper for Seven Desktop App.
#
# Builds a native desktop app (macOS .dmg / .app, Linux .deb / .AppImage).
# The app bundles its own HTML/JS frontend and talks to the SWARM leader
# via Rust-native HTTP commands (no CORS, no localhost dependency).
#
# Usage:
#   ./desktop/build.sh              # dev run (cargo tauri dev)
#   ./desktop/build.sh release      # release bundles (platform-specific)
#   ./desktop/build.sh release dmg  # macOS DMG only
#   ./desktop/build.sh release deb  # Linux .deb only
#
# Prereqs:
#   - Rust + cargo (rustup)
#   - cargo install tauri-cli --version '^2'
#   - Linux libs: libwebkit2gtk-4.1-dev build-essential curl wget file
#                  libssl-dev libayatana-appindicator3-dev librsvg2-dev
#   - macOS: Xcode command line tools
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}/desktop/src-tauri"

MODE="${1:-dev}"
shift || true

if ! command -v cargo >/dev/null 2>&1; then
    echo "ERROR: cargo not on PATH. Install rustup first." >&2
    exit 2
fi
if ! cargo tauri --version >/dev/null 2>&1; then
    echo "INFO: installing cargo-tauri v2..."
    cargo install tauri-cli --version '^2'
fi

case "${MODE}" in
    dev)
        cargo tauri dev
        ;;
    release)
        cargo tauri build "$@"
        echo ""
        echo "=== Build outputs ==="
        find "${ROOT}/desktop/src-tauri/target/release/bundle" -type f -exec ls -lh {} \;
        ;;
    *)
        echo "Usage: $0 [dev|release] [bundle-targets...]" >&2
        exit 1
        ;;
esac
