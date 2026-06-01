#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_ROOT="$(wslpath -w "$ROOT_DIR")"

mode="${1:-start}"

case "$mode" in
  install)
    script='set FRIDAYS_NO_PAUSE=1 && pushd "__WIN_ROOT__" && call windows\install-fridays.bat'
    ;;
  start)
    script='set FRIDAYS_NO_PAUSE=1 && pushd "__WIN_ROOT__" && call windows\start-fridays.bat'
    ;;
  *)
    echo "Usage: windows/run-fridays-from-wsl.sh [install|start]" >&2
    exit 1
    ;;
esac

script="${script/__WIN_ROOT__/$WIN_ROOT}"
cmd.exe /c "$script"
