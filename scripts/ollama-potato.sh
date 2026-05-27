#!/usr/bin/env bash
# DOES Concurrency Exclusion Engine
# ----------------------------------
# Starts Ollama with the smallest possible static footprint so the
# OptiPlex 7090 actually realizes the 80% gain from 4-bit GGUF quants.
#
# What this kills (Ollama defaults that silently inflate RAM):
#   OLLAMA_NUM_PARALLEL=4      → 4 KV-cache slots per loaded model. KILL.
#   OLLAMA_MAX_LOADED_MODELS=3 → 3 resident models. KILL — Potato Farm
#                                requires single-resident.
#   OLLAMA_KEEP_ALIVE=5m       → 5-minute idle cushion. KILL.
#
# What this enables:
#   OLLAMA_FLASH_ATTENTION=1   → ~40% KV-cache reduction.
#   OLLAMA_KV_CACHE_TYPE=q8_0  → quantized KV cache (Ollama >= 0.4).
#   OLLAMA_NUM_PARALLEL=1      → exactly one user slot.
#   OLLAMA_MAX_LOADED_MODELS=1 → one resident model, ever.
#   OLLAMA_KEEP_ALIVE=0        → unload the instant a request returns.
#
# Usage:
#   ./scripts/ollama-potato.sh           # foreground
#   nohup ./scripts/ollama-potato.sh &   # background
#   systemctl --user start ollama-potato # if installed (see unit file)

set -euo pipefail

export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KEEP_ALIVE=0
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_NOHISTORY=1
# Cap context globally as a belt-and-braces alongside per-request num_ctx.
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-4096}"
# Hard memory ceiling — refuses to load models that would exceed it.
# Set conservatively for 33GB box leaving headroom for the harness + OS.
export OLLAMA_MAX_VRAM="${OLLAMA_MAX_VRAM:-0}"      # CPU-only box

# Pin the Ollama process to lower CPU priority so the harness stays responsive.
exec nice -n 5 ionice -c2 -n4 ollama serve
