#!/bin/bash
# Build llama.cpp with ROCm/HIP for the RX 6800 (gfx1030) into build-rocm, next to build-vulkan. No root needed.
set -e
cd /home/jd/llama.cpp
export HIP_PATH=/opt/rocm ROCM_PATH=/opt/rocm
export HIPCXX="$(/opt/rocm/llvm/bin/clang -print-prog-name=clang 2>/dev/null || echo /opt/rocm/llvm/bin/clang)"
cmake -S . -B build-rocm -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1030 -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
cmake --build build-rocm --config Release -j 14 --target llama-server llama-bench
ls -la build-rocm/bin/llama-server build-rocm/bin/llama-bench
