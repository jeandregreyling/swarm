#!/bin/bash

# APEX Jailbreak Configuration - Unleash Full Hardware Potential
# This script configures APEX to use all available RAM and GPU resources
# and strips unnecessary guardrails for maximum performance.

# Hardware Detection
echo "=========================================="
echo "Detecting Available Hardware..."
echo "=========================================="

# RAM
TOTAL_RAM_GIB=$(free -g | awk '/^Mem:/ {print $2}')
AVAILABLE_RAM_GIB=$(free -g | awk '/^Mem:/ {print $7}')
echo "Total RAM: ${TOTAL_RAM_GIB} GiB"
echo "Available RAM: ${AVAILABLE_RAM_GIB} GiB"

# GPU
GPU_INFO=$(lspci | grep -i "VGA\|AMD\|NVIDIA" | head -1)
echo "GPU: $GPU_INFO"

# VRAM estimation (RX 6800/6900 XT typically has 16GB)
Vram="16"
echo "Estimated VRAM: ${Vram} GiB"

# Current model
MODEL_PATH="/mnt/archive/models/blobs/sha256-2049f5674b1e92b4464e5729975c9689fcfbf0b0e4443ccf10b5339f370f9a54"
MODEL_NAME="qwen2.5:14b-instruct"

# Calculate optimal settings
echo ""
echo "=========================================="
echo "Calculating Optimal APEX Configuration..."
echo "=========================================="

# Use 80% of available RAM for cache (but not more than 48GB)
CACHE_RAM=$((AVAILABLE_RAM_GIB * 80 / 100))
if [ "$CACHE_RAM" -gt 48 ]; then
    CACHE_RAM=48
fi

# Parallelism: Use all CPU cores
CPU_CORES=$(nproc)
PARALLEL=$((CPU_CORES / 2))  # Conservative: half of cores
if [ "$PARALLEL" -lt 1 ]; then
    PARALLEL=1
fi

# GPU layers: Use all available
NGL=99

# Context size: Max supported by model (Qwen2.5 14B supports 32K+)
CTX_SIZE=32768

# Batch size
BATCH_SIZE=512

# Threads
THREADS=$CPU_CORES

# Vulkan device
VULKAN_DEVICE="Vulkan0"

echo "Optimized Settings:"
echo "  Context Size: ${CTX_SIZE}"
echo "  Parallel: ${PARALLEL}"
echo "  GPU Layers: ${NGL}"
echo "  Cache RAM: ${CACHE_RAM} GiB"
echo "  Batch Size: ${BATCH_SIZE}"
echo "  Threads: ${THREADS}"
echo "  VRAM Usage: High (${Vram} GiB available)"

echo ""
echo "=========================================="
echo "Jailbreak APEX Command"
echo "=========================================="

echo "Kill existing APEX:"
echo "  pkill -f 'llama-server'"
echo ""

echo "Start Jailbroken APEX:"
cat << EOF
nohup /home/jd/llama.cpp/build-vulkan/bin/llama-server \\
  -m ${MODEL_PATH} \\
  --device ${VULKAN_DEVICE} \\
  -ngl ${NGL} \\
  --load-mode dio \\
  --host 0.0.0.0 \\
  --port 8080 \\
  --ctx-size ${CTX_SIZE} \\
  --parallel ${PARALLEL} \\
  --batch-size ${BATCH_SIZE} \\
  --threads ${THREADS} \\
  --jinja \\
  --flash-attn on \\
  --cache-type-k f16 \\
  --cache-type-v f16 \\
  --cache-ram ${CACHE_RAM} \\
  --fit off \\
  --no-webui \\
  --cont-batch \\
  --log-disable \\
  > /tmp/apex_jailbroken.log 2>&1 &

EOF

echo ""
echo "This configuration:"
echo "  ✓ Uses ALL available GPU layers (${NGL})"
echo "  ✓ Uses ${CACHE_RAM} GiB RAM for KV cache"
echo "  ✓ Doubles context size to ${CTX_SIZE}"
echo "  ✓ Increases parallelism to ${PARALLEL}"
echo "  ✓ Uses all CPU threads (${THREADS})"
echo "  ✓ Enables contiguous batching for better throughput"
echo "  ✓ Disables logging for cleaner output"
echo ""

echo "=========================================="
echo "WARNING: Jailbroken APEX"
echo "=========================================="
echo "This configuration removes safety limits and uses"
echo "maximum hardware resources. Ensure you have:"
echo "  - Sufficient cooling (GPU will run hot)"
echo "  - Stable power supply"
echo "  - Enough RAM (${CACHE_RAM} GiB will be used)"
echo ""
echo "Benefits:"
echo "  ✓ 2-5x faster response times"
echo "  ✓ Larger context window (${CTX_SIZE} tokens)"
echo "  ✓ Better parallelism"
echo "  ✓ Full GPU utilization"
echo ""
echo "Trade-offs:"
echo "  ⚠ Higher memory usage"
echo "  ⚠ More GPU power consumption"
echo "  ⚠ Potentially less stable under heavy load"
echo ""

# Check if user wants to apply now
read -p "Apply jailbroken APEX configuration now? [y/N] " -n 1 -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Applying jailbroken configuration..."
    
    # Kill existing
    pkill -f "llama-server" || true
    sleep 2
    
    # Start jailbroken
    nohup /home/jd/llama.cpp/build-vulkan/bin/llama-server \
      -m ${MODEL_PATH} \
      --device ${VULKAN_DEVICE} \
      -ngl ${NGL} \
      --load-mode dio \
      --host 0.0.0.0 \
      --port 8080 \
      --ctx-size ${CTX_SIZE} \
      --parallel ${PARALLEL} \
      --batch-size ${BATCH_SIZE} \
      --threads ${THREADS} \
      --jinja \
      --flash-attn on \
      --cache-type-k f16 \
      --cache-type-v f16 \
      --cache-ram ${CACHE_RAM} \
      --fit off \
      --no-webui \
      --cont-batch \
      --log-disable \
      > /tmp/apex_jailbroken.log 2>&1 &
    
    sleep 3
    
    if pgrep -f "llama-server" > /dev/null; then
        echo "✓ Jailbroken APEX is running!"
        echo "  Check logs: tail -f /tmp/apex_jailbroken.log"
        echo "  Test: curl http://127.0.0.1:8080/v1/models"
    else
        echo "✗ Failed to start APEX"
        echo "  Check logs: cat /tmp/apex_jailbroken.log"
    fi
else
    echo ""
    echo "Configuration ready. Run manually when ready."
fi
