#!/usr/bin/env bash
# desktop/build.sh — Tauri v2 desktop build helper (Phase-5 small S-E7775EAA48).
#
# Builds the Swarm desktop shell that embeds http://127.0.0.1:5050/ui as a
# native window, plus produces .deb and AppImage bundles for Linux. macOS
# and Windows targets are available if cargo-tauri is installed with those
# toolchains, but the CI path targets Linux.
#
# Usage:
#   ./desktop/build.sh              # debug dev run (tauri dev)
#   ./desktop/build.sh release      # release bundles (deb + appimage)
#   ./desktop/build.sh release dmg  # macOS bundle (requires macOS host)
#
# Prereqs:
#   - Rust + cargo (rustup).
#   - cargo install tauri-cli --version '^2'
#   - System libs: libwebkit2gtk-4.1-dev build-essential curl wget file
#                  libssl-dev libayatana-appindicator3-dev librsvg2-dev
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}/desktop"

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
        cargo tauri build --bundles deb,appimage "$@"
        echo "---"
        echo "Bundles in: ${ROOT}/desktop/src-tauri/target/release/bundle/"
        ;;
    dmg|msi)
        cargo tauri build --bundles "${MODE}" "$@"
        ;;
    *)
        echo "Usage: desktop/build.sh [dev|release|dmg|msi] [extra tauri args]" >&2
        exit 1
        ;;
esac
