#!/bin/bash
# DOES Framework Setup: Register Villain Node in Ollama
# 
# This script prepares the DOES framework for execution by:
# 1. Verifying Ollama is running
# 2. Creating the Villain-Node model from Modelfile_Villain
# 3. Verifying both Builder (Qwen) and Villain nodes are available
#
# Usage: ./setup_does.sh
# Prerequisites: Ollama must be running (ollama serve)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELFILE_PATH="$SCRIPT_DIR/Modelfile_Villain"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ DOES Framework Setup: Villain Node Registration                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Ollama is running
echo "⧖ Checking Ollama service..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "❌ Ollama is not running. Start it with: ollama serve"
    exit 1
fi
echo "✓ Ollama is running"
echo ""

# Verify Modelfile exists
if [ ! -f "$MODELFILE_PATH" ]; then
    echo "❌ Modelfile_Villain not found at $MODELFILE_PATH"
    exit 1
fi
echo "✓ Modelfile_Villain found"
echo ""

# Check if Gemma-3 base model is available (required for Villain)
echo "⧖ Checking for gemma3:4b-instruct-q4_K_M base model..."
MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | grep gemma3)
if [ -z "$MODELS" ]; then
    echo "⚠ gemma3:4b-instruct-q4_K_M not found locally"
    echo "  Pulling it now (this may take a few minutes)..."
    ollama pull gemma3:4b-instruct-q4_K_M
else
    echo "✓ gemma3:4b-instruct-q4_K_M is available"
fi
echo ""

# Create the villain-node model
echo "⧖ Creating villain-node model from Modelfile_Villain..."
if ollama create villain-node -f "$MODELFILE_PATH"; then
    echo "✓ Successfully created villain-node"
else
    echo "❌ Failed to create villain-node"
    exit 1
fi
echo ""

# Verify both models are available
echo "⧖ Verifying DOES nodes..."
AVAILABLE_MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"')

if echo "$AVAILABLE_MODELS" | grep -q "villain-node"; then
    echo "✓ Villain-Node is registered"
else
    echo "❌ Villain-Node is not registered"
    exit 1
fi

if echo "$AVAILABLE_MODELS" | grep -q "qwen"; then
    echo "✓ Builder (Qwen) is registered"
else
    echo "⚠ Builder (Qwen) not found — install with: ollama pull qwen"
fi
echo ""

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║ ✓ DOES Framework Setup Complete                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "1. Start the DOES harness: python -c 'from core.does_router import submit_for_audit; ...'"
echo "2. Or use the shell: source seven.sh; does-audit <code_file>"
echo ""
