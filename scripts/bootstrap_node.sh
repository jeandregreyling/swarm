#!/usr/bin/env bash
# Reproducible Hummingbird / Potato Farm (Dell OptiPlex / Linux) Node Bootstrap
# Usage: bash scripts/bootstrap_node.sh [--skip-pip]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKIP_PIP=0

for arg in "$@"; do
  case "$arg" in
    --skip-pip) SKIP_PIP=1 ;;
  esac
done

echo "[Hummingbird Bootstrap] Repo root: ${REPO_ROOT}"
cd "${REPO_ROOT}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required." >&2
  exit 1
fi

if [ ! -d "${REPO_ROOT}/.venv" ]; then
  echo "[Hummingbird Bootstrap] Creating Python virtual environment (.venv)..."
  python3 -m venv "${REPO_ROOT}/.venv"
fi

if [ "${SKIP_PIP}" -eq 0 ] && [ -f "${REPO_ROOT}/requirements.txt" ]; then
  echo "[Hummingbird Bootstrap] Installing Python dependencies..."
  "${REPO_ROOT}/.venv/bin/pip" install --upgrade pip >/dev/null
  "${REPO_ROOT}/.venv/bin/pip" install -r "${REPO_ROOT}/requirements.txt"
fi

mkdir -p "${REPO_ROOT}/runtime" "${REPO_ROOT}/artifacts/media_center/library"

if [ ! -f "${REPO_ROOT}/runtime/.hb_nectar_key" ]; then
  echo "[Hummingbird Bootstrap] Generating node-local 0600 Nectar HMAC key..."
  "${REPO_ROOT}/.venv/bin/python" -c "import os, pathlib; p=pathlib.Path('runtime/.hb_nectar_key'); p.write_bytes(os.urandom(32)); os.chmod(p, 0o600)"
fi

if [ ! -f "${REPO_ROOT}/.env" ] && [ -f "${REPO_ROOT}/.env.example" ]; then
  cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
  echo "[Hummingbird Bootstrap] Created .env from .env.example (edit locally as needed)."
fi

echo "[Hummingbird Bootstrap] Running portability & secret-safety gate..."
"${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/verify_portability.py"

echo "[Hummingbird Bootstrap] Ready! Start Hummingbird with:"
echo "  HUMMINGBIRD_PORT=5050 ${REPO_ROOT}/.venv/bin/python -m frontend.app"
