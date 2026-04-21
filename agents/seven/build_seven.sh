#!/usr/bin/env bash
# build_seven.sh — Full build pipeline for the Seven merged LLM
# Run from: /home/seven/swarm/agents/seven/
# Prerequisites: mergekit installed, models downloaded, llama.cpp built
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODELS_DIR="./models"
MERGE_OUTPUT="./models/Seven-7B-merged"
GGUF_OUTPUT="./models/seven-7b-fp16.gguf"
QUANTIZED_OUTPUT="./models/seven-7b-q8_0.gguf"
LLAMA_CPP_DIR="./llama.cpp"

echo "============================================"
echo "  Building Seven — Custom Merged LLM"
echo "============================================"

# Step 1: Verify models exist
echo ""
echo "[1/5] Verifying donor models..."
if [[ ! -d "$MODELS_DIR/Qwen2.5-7B-Instruct" ]]; then
    echo "ERROR: Qwen2.5-7B-Instruct not found in $MODELS_DIR"
    exit 1
fi
if [[ ! -d "$MODELS_DIR/DeepSeek-R1-Distill-Qwen-7B" ]]; then
    echo "ERROR: DeepSeek-R1-Distill-Qwen-7B not found in $MODELS_DIR"
    exit 1
fi
echo "  ✓ Both models found"

# Step 2: Run mergekit
echo ""
echo "[2/5] Merging models with SLERP..."
echo "  Config: seven_merge.yaml"
echo "  Output: $MERGE_OUTPUT"
echo "  This will take 1-3 hours on CPU..."

if [[ -d "$MERGE_OUTPUT" ]] && [[ -f "$MERGE_OUTPUT/config.json" ]]; then
    echo "  ✓ Merged model already exists, skipping merge step"
else
    mergekit-yaml seven_merge.yaml "$MERGE_OUTPUT" \
        --copy-tokenizer \
        --allow-crimes \
        --out-shard-size 2B \
        --lazy-unpickle
    echo "  ✓ Merge complete"
fi

# Step 3: Convert to GGUF
echo ""
echo "[3/5] Converting to GGUF format..."
if [[ -f "$GGUF_OUTPUT" ]]; then
    echo "  ✓ GGUF already exists, skipping conversion"
else
    python3 "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" "$MERGE_OUTPUT" \
        --outfile "$GGUF_OUTPUT" \
        --outtype f16
    echo "  ✓ GGUF conversion complete"
fi

# Step 4: Quantize to Q8_0
echo ""
echo "[4/5] Quantizing to Q8_0 (~7GB)..."
if [[ -f "$QUANTIZED_OUTPUT" ]]; then
    echo "  ✓ Quantized model already exists, skipping"
else
    "$LLAMA_CPP_DIR/build/bin/llama-quantize" "$GGUF_OUTPUT" "$QUANTIZED_OUTPUT" Q8_0
    echo "  ✓ Quantization complete"
fi

# Step 5: Register in Ollama
echo ""
echo "[5/5] Registering Seven in Ollama..."
cd "$SCRIPT_DIR"

# Update Modelfile to point to the quantized GGUF
GGUF_ABSPATH="$(realpath "$QUANTIZED_OUTPUT")"
sed -i "s|^FROM .*|FROM $GGUF_ABSPATH|" Modelfile

ollama create seven -f Modelfile
echo "  ✓ Seven registered in Ollama"

echo ""
echo "============================================"
echo "  Seven is alive!"
echo "============================================"
echo ""
echo "Test with: ollama run seven 'Hello, I am your human. Who are you?'"
echo ""
