#!/bin/bash
# Shell integration for DOES Framework
# Add these functions to seven.sh or source this file

# DOES Framework: Submit code for adversarial audit
does-audit() {
    local file_or_code="$1"
    local context="${2:-No context provided}"
    
    if [[ ! -f "$file_or_code" && -f "$SWARM_ROOT/$file_or_code" ]]; then
        file_or_code="$SWARM_ROOT/$file_or_code"
    fi
    
    if [[ -f "$file_or_code" ]]; then
        # Read file
        local code=$(cat "$file_or_code")
        local filename=$(basename "$file_or_code")
        context="Audit of: $filename"
    else
        # Treat as code string
        local code="$file_or_code"
    fi
    
    python3 - "$code" "$context" <<'PYTHON'
import sys
import json
from pathlib import Path

# Add swarm root to path
swarm_root = Path(__file__).parent.parent if Path(__file__).exists() else Path.cwd()
sys.path.insert(0, str(swarm_root))

from core.does_router import submit_for_audit

code = sys.argv[1]
context = sys.argv[2]

result = submit_for_audit(code, context=context, max_iterations=5)

print(f"Execution ID: {result['execution_id']}")
print(f"Status: {result['status']}")
print(f"Iterations: {result['iterations']}")

if result['final_audit']:
    audit = result['final_audit']
    print(f"\nFinal Verdict: {audit['verdict']}")
    print(f"Structural Flaws: {audit['structural_flaws']}")
    print(f"Efficiency Score: {audit['efficiency_score']}")
    
    if audit['objections']:
        print("\nObjections:")
        for obj in audit['objections']:
            print(f"  - {obj}")
    
    if audit['recommendations']:
        print("\nRecommendations:")
        for rec in audit['recommendations']:
            print(f"  - {rec}")

sys.exit(0)
PYTHON
}

# DOES Framework: Retrieve audit results
does-audit-result() {
    local execution_id="$1"
    
    if [[ -z "$execution_id" ]]; then
        echo "Usage: does-audit-result <execution_id>"
        echo "Example: does-audit-result does-abc123def456"
        return 1
    fi
    
    python3 - "$execution_id" <<'PYTHON'
import sys
import json
from pathlib import Path

swarm_root = Path(__file__).parent.parent if Path(__file__).exists() else Path.cwd()
sys.path.insert(0, str(swarm_root))

from core.does_router import get_audit_results

execution_id = sys.argv[1]
history = get_audit_results(execution_id)

if 'error' in history:
    print(f"Error: {history['error']}")
    sys.exit(1)

print(f"Execution: {execution_id}")
print(f"Phase: {history['state']['phase']}")
print(f"Iterations: {history['state']['loop_iteration']} / {history['state']['max_iterations']}")
print()

for i, gen in enumerate(history['generations'], 1):
    print(f"─── Iteration {gen['iteration']}: GENERATION ───")
    payload_preview = gen['payload'][:200] + "..." if len(gen['payload']) > 200 else gen['payload']
    print(f"Payload (first 200 chars):\n{payload_preview}")
    print()
    
    # Find corresponding audit
    audit = next((a for a in history['audits'] if a['iteration'] == gen['iteration']), None)
    if audit:
        print(f"─── Iteration {audit['iteration']}: AUDIT ───")
        print(f"Verdict: {audit['verdict']}")
        print(f"Structural Flaws: {audit['structural_flaws']}")
        print(f"Efficiency Score: {audit.get('efficiency_score', 'N/A')}")
        
        if audit['objections']:
            print("Objections:")
            objections = json.loads(audit['objections']) if isinstance(audit['objections'], str) else audit['objections']
            for obj in objections:
                print(f"  • {obj}")
        
        if audit['recommendations']:
            print("Recommendations:")
            recommendations = json.loads(audit['recommendations']) if isinstance(audit['recommendations'], str) else audit['recommendations']
            for rec in recommendations:
                print(f"  • {rec}")
        print()

sys.exit(0)
PYTHON
}

# DOES Framework: Setup (register Villain node)
does-setup() {
    echo "Setting up DOES Framework..."
    if [[ -f "$SWARM_ROOT/setup_does.sh" ]]; then
        bash "$SWARM_ROOT/setup_does.sh"
    else
        echo "Error: setup_does.sh not found"
        return 1
    fi
}

# DOES Framework: Check status
does-status() {
    echo "Checking DOES Framework status..."
    python3 - <<'PYTHON'
import sys
from pathlib import Path

swarm_root = Path.cwd()
sys.path.insert(0, str(swarm_root))

from core.ollama import get_ollama_manager

manager = get_ollama_manager()

print("Ollama Service: ", end="")
if manager.is_running():
    print("✓ Running")
else:
    print("✗ Not running")
    sys.exit(1)

models = manager.list_models()
print(f"Available models: {len(models)}")

required = ['qwen', 'villain-node', 'gemma3']
for model_name in required:
    found = any(model_name in m for m in models)
    status = "✓" if found else "✗"
    print(f"  {status} {model_name}")

print("\nDOES Framework Status: Ready")
PYTHON
}

# Export functions
export -f does-audit
export -f does-audit-result
export -f does-setup
export -f does-status
