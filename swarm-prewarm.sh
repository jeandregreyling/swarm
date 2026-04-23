#!/usr/bin/env bash
# swarm-prewarm.sh — load all swarm models into memory on boot
# Runs as a oneshot systemd service after ollama.service is ready.
# Each model is loaded with keep_alive=300 (5 minutes). After the idle window
# expires, ollama unloads automatically. Agents re-pin on next call with the
# same 1800s window (see agents/*/...agent.py). Never pin Forever — it defeats
# the resource gate and caused the April 2026 CPU runaway.
# Unique models derived from core/pipeline/orchestrator.py AGENTS dict.

set -euo pipefail

OLLAMA_URL="http://localhost:11434"
MAX_WAIT=60   # seconds to wait for Ollama to become ready

log() { echo "[prewarm] $(date '+%H:%M:%S') $*"; }

# Per-model timeouts (seconds). Unset = default 180s.
# Cold loads on CPU-only are slow; gemma3 and qwen2.5 both missed 180s in
# earlier runs. Give each hot-path model plenty of head-room.
declare -A MODEL_TIMEOUT=(
  ["gemma4:26b"]=600
  ["gemma3:latest"]=420
  ["qwen2.5:latest"]=420
  ["llama3.2:latest"]=300
  ["qwen:latest"]=300
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

# ── Models to warm ────────────────────────────────────────────────────────
# Session 30 (2026-04-23): re-enabled for the 4 hot-path local agents so
# first-call timeouts (e.g. "[llama] background run failed: llama timed out
# after 2000s") don't happen from a cold start. Total footprint ≈ 12.3 GB:
#   - gemma3:latest      3.3 GB  (Gemma)
#   - llama3.2:latest    2.0 GB  (LLaMA)
#   - qwen2.5:latest     4.7 GB  (Duck)
#   - qwen:latest        2.3 GB  (Vortex / librarian)
# This lets Qwen3.6 (23 GB) page to NVMe swap instead of blocking hot agents.
# Warm in size order (largest first) so the big one grabs contiguous RAM
# before the smaller ones fragment it.
MODELS=(
  "qwen2.5:latest"
  "gemma3:latest"
  "qwen:latest"
  "llama3.2:latest"
)

LOADED=0
SKIPPED=0
FAILED=0

for MODEL in "${MODELS[@]}"; do
  # Check if this model is installed locally (case-insensitive — ollama stores
  # original casing like "Qwen2.5:latest" but accepts lowercase at inference).
  if ! curl -sf --max-time 5 "$OLLAMA_URL/api/tags" | MODEL_LC="${MODEL,,}" python3 -c "
import json, os, sys
data = json.load(sys.stdin)
needle = os.environ['MODEL_LC']
names = [m.get('name','').lower() for m in data.get('models', [])]
sys.exit(0 if any(needle in n for n in names) else 1)
" 2>/dev/null; then
    log "SKIP  $MODEL — not installed"
    ((SKIPPED++)) || true
    continue
  fi

  TVAL="${MODEL_TIMEOUT[$MODEL]:-180}"
  log "LOAD  $MODEL  (timeout ${TVAL}s)..."
  # Ollama convention: empty prompt = "load model into memory, no generation".
  # A space-prompt (" ") would make the model generate until context fills,
  # spinning the runner at 99% CPU indefinitely even after curl disconnects.
  # num_predict=0 is belt-and-braces in case a future Ollama version changes
  # the empty-prompt behavior.
  HTTP_CODE=$(curl -s -o /tmp/prewarm_resp.json -w "%{http_code}" \
    --max-time "$TVAL" \
    -X POST "$OLLAMA_URL/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"prompt\":\"\",\"keep_alive\":1800,\"options\":{\"num_predict\":0}}" 2>/dev/null || echo "000")

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
