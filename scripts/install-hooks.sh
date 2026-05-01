#!/usr/bin/env bash
# Install the project pre-commit hook.
# Hook runs the bullshit detector and aborts the commit on RED.
# Bypass with `git commit --no-verify` (use sparingly).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_PATH="$ROOT/.git/hooks/pre-commit"

if [ ! -d "$ROOT/.git" ]; then
  echo "[install-hooks] not a git repo: $ROOT"
  exit 1
fi

mkdir -p "$ROOT/.git/hooks"
cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
# Auto-installed by scripts/install-hooks.sh.
# Aborts the commit if ops/bullshit_detector.py reports RED.
ROOT="$(git rev-parse --show-toplevel)"
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PY" ]; then
  echo "[pre-commit] no python interpreter found; skipping detector"
  exit 0
fi

STAMP=$("$PY" - <<'PY' 2>/dev/null
import sys
sys.path.insert(0, '.')
try:
    from ops.bullshit_detector import scan
    d = scan()
    print(d['stamp'])
except Exception as exc:
    print('UNKNOWN')
PY
)

case "$STAMP" in
  GREEN)
    echo "[pre-commit] detector: GREEN"
    exit 0
    ;;
  AMBER)
    echo "[pre-commit] detector: AMBER (allowed)"
    exit 0
    ;;
  RED)
    echo "[pre-commit] detector: RED — commit aborted."
    echo "[pre-commit] run 'make bullshit' to see the hits, or bypass with --no-verify."
    exit 1
    ;;
  *)
    echo "[pre-commit] detector: $STAMP — allowing commit (could not classify)"
    exit 0
    ;;
esac
HOOK
chmod +x "$HOOK_PATH"
echo "[install-hooks] installed $HOOK_PATH"
echo "[install-hooks] bypass with: git commit --no-verify"
