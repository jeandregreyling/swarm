#!/usr/bin/env bash
# swarm-prewarm.sh — load all swarm models into memory on boot
# Runs as a oneshot systemd service after ollama.service is ready.
# Each model is loaded with keep_alive=300 (5 minutes). After the idle window
# expires, ollama unloads automatically. Agents re-pin on next call with the
# same 300s window (see agents/*/...agent.py). Never pin Forever — it defeats
# the resource gate and caused the April 2026 CPU runaway.
# Unique models derived from core/pipeline/orchestrator.py AGENTS dict.

set -euo pipefail

OLLAMA_URL="http://localhost:11434"
MAX_WAIT=60   # seconds to wait for Ollama to become ready

log() { echo "[prewarm] $(date '+%H:%M:%S') $*"; }

# Per-model timeouts (seconds). Unset = default 180s.
declare -A MODEL_TIMEOUT=(
  ["gemma4:26b"]=420
)

# ── Wait for Ollama to accept connections ─────────────────────────────────
log "Waiting for Ollama..."
for i in $(seq 1 $MAX_WAIT); do
  if curl -sf --max-time 2 "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    log "Ollama ready after ${i}s"
    break
  fi
  if [[ $i -eq $MAX_WAIT ]]; then
    log "ERROR: Ollama did not become ready in ${MAX_WAIT}s — aborting"
    exit 1
  fi
  sleep 1
done

# ── Models to warm (unique set from orchestrator.py AGENTS) ───────────────
# gemma4:26b FIRST — at 18.5 GB it must claim RAM before the smaller models
# fill it. Smaller models page to NVMe swap as needed.
# gemma4:26b removed — too large for CPU-only (19GB), disabled in agents DB
MODELS=(
  # PREWARM DISABLED (Session 24, 2026-04-22): loading multiple models on a
  # CPU-only box spikes load avg to 10+ and pegs all cores for 60-90s per
  # model. Unit is now disabled in systemd; this list is also empty as a
  # belt-and-braces safeguard. Agents will load their model on first call
  # (with keep_alive=300s), which amortises cost over actual usage.
  # If you re-enable, add AT MOST one small model (e.g. "qwen:latest").
)

LOADED=0
SKIPPED=0
FAILED=0

for MODEL in "${MODELS[@]}"; do
  # Check if this model is installed locally.
  # /api/tags lists installed models; /api/ps only lists currently loaded ones.
  if ! curl -sf --max-time 5 "$OLLAMA_URL/api/tags" | python3 -c "
import json, sys
data = json.load(sys.stdin)
models = [m.get('name','') for m in data.get('models', [])]
sys.exit(0 if any('$MODEL' in n for n in models) else 1)
" 2>/dev/null; then
    log "SKIP  $MODEL — not installed"
    ((SKIPPED++)) || true
    continue
  fi

  TVAL="${MODEL_TIMEOUT[$MODEL]:-180}"
  log "LOAD  $MODEL  (timeout ${TVAL}s)..."
  HTTP_CODE=$(curl -s -o /tmp/prewarm_resp.json -w "%{http_code}" \
    --max-time "$TVAL" \
    -X POST "$OLLAMA_URL/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"prompt\":\" \",\"keep_alive\":300}" 2>/dev/null || echo "000")

  if [[ "$HTTP_CODE" == "200" ]]; then
    log "OK    $MODEL"
    ((LOADED++)) || true
  else
    log "FAIL  $MODEL — HTTP $HTTP_CODE"
    ((FAILED++)) || true
  fi
done

log "Done: ${LOADED} loaded, ${SKIPPED} skipped (not installed), ${FAILED} failed"

# ── Final report ──────────────────────────────────────────────────────────
log "Resident models:"
curl -s --max-time 5 "$OLLAMA_URL/api/ps" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('models', []):
    gb = m.get('size', 0) / 1024**3
    perm = 'PERMANENT' if '2318' in str(m.get('expires_at','')) else ''
    print(f'  {m[\"name\"]:<30} {gb:.1f} GB  {perm}')
" 2>/dev/null || true

[[ $FAILED -eq 0 ]] && exit 0 || exit 1
