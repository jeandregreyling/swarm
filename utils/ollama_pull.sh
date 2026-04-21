#!/usr/bin/env bash
# Resilient ollama pull — retries forever on network drop, resumes from partial blobs.
# Usage: ./ollama_pull.sh <model> [model2] ...

set -euo pipefail

RETRY_WAIT=15
MAX_TRIES=0  # 0 = infinite

pull_model() {
  local model="$1"
  local attempt=0

  echo "[ollama-pull] Starting: $model"
  while true; do
    attempt=$((attempt + 1))
    echo "[ollama-pull] $model — attempt $attempt ($(date '+%H:%M:%S'))"

    if ollama pull "$model"; then
      echo "[ollama-pull] Done: $model"
      return 0
    fi

    echo "[ollama-pull] $model failed — waiting ${RETRY_WAIT}s before retry..."
    sleep "$RETRY_WAIT"
  done
}

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <model> [model2] ..."
  exit 1
fi

for model in "$@"; do
  pull_model "$model"
done

echo "[ollama-pull] All models done."
