#!/usr/bin/env bash
# collect_telemetry.sh
# This script gathers GPU memory usage, CPU load, inference latency, and batch size
# and writes the results to metrics.json.

set -euo pipefail

OUTPUT="metrics.json"

# 1. GPU memory usage (Vulkan)
if command -v vulkaninfo >/dev/null 2>&1; then
    VULKAN_INFO=$(vulkaninfo | grep -i "Memory Heaps" -A 10)
else
    VULKAN_INFO="vulkaninfo not available"
fi

gpu_memory=$(echo "$VULKAN_INFO" | grep -i "size" | awk '{print $2}')

# 2. CPU load (average over 5 seconds)
if command -v mpstat >/dev/null 2>&1; then
    cpu_load=$(mpstat 5 1 | awk 'NR>3{print $NF}')
else
    cpu_load="mpstat not available"
fi

# 3. Inference latency and batch size
# Assume wrapper writes a log file named inference.log with lines like:
# "latency: 123 ms, batch: 8"
if [ -f inference.log ]; then
    latency=$(grep -i "latency" inference.log | awk -F'[: ]+' '{print $3}')
    batch_size=$(grep -i "batch" inference.log | awk -F'[: ]+' '{print $3}')
else
    latency="inference.log not found"
    batch_size="inference.log not found"
fi

# 4. Write metrics to JSON
cat > "$OUTPUT" <<EOF
{
  "gpu_memory": "$gpu_memory",
  "cpu_load": "$cpu_load",
  "latency_ms": "$latency",
  "batch_size": "$batch_size"
}
EOF

echo "Metrics written to $OUTPUT"
