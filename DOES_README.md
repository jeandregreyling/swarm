# DOES Framework: Hardware-Constrained AI Orchestration

## Architecture Overview

The **DOES Framework** (Diversifying Operations Executional Sharing) is a state-machine-driven orchestration system that enables sophisticated multi-agent AI workflows on consumer-grade hardware by:

1. **Memory Efficiency**: Only one quantized model is active in system memory at any given microsecond
2. **Persistent State**: SQL database retains all execution context, keeping RAM flat
3. **Adversarial Validation**: Automated code/logic auditing via the Villain Node
4. **Hardware-Constrained**: Designed for Dell OptiPlex 7090 (6-core i5, 33GB RAM, no GPU)

### The Council

```
                    [ LOCAL LOGIC HARNESS ]
                               │
         ┌───────────────────────┼──────────────────────┐
         ▼                       ▼                      ▼
   [ The Builder ]       [ Shared SQL DB ]      [ The Villain ]
   (Qwen-2.5-1.5B)    (Persistent State)   (Gemma-3-4B-Instruct)
   Generates raw code &  Tracks variables,  Tears the logic apart,
   variables             prompts, history   hunts for bugs/flaws
```

### Execution Flow: Generation → Handoff → Audit → Resolution

```
1. GENERATION: Builder writes code/logic to does_state table
                ↓
2. HANDOFF:    Harness unloads Builder, loads Villain from Ollama
                ↓
3. AUDIT:      Villain analyzes payload, writes findings to does_audit table
                ↓
4. RESOLUTION: If objections found, pass feedback back to Builder
                ↓
5. REPEAT:     Loop until zero objections OR max_iterations reached
                ↓
6. COMPLETE:   Execution marked complete with final verdict
```

## Installation & Setup

### Prerequisites

- **Ollama** running locally (`ollama serve`)
- **Python 3.9+** with access to swarm environment
- **SQLite3** (included with Python)
- Base models pulled: `gemma3:4b-instruct-q4_K_M` (for Villain), `qwen` (for Builder)

### 1. Register the Villain Node

```bash
# From swarm root
./setup_does.sh
```

This script will:
- Verify Ollama is running
- Pull gemma3 if needed
- Create `villain-node` from `Modelfile_Villain`
- Verify both Builder and Villain are available

### 2. Verify Setup

```bash
python tests/test_does.py --mode demo
```

Output should confirm:
```
✓ DOES Registry initialized
✓ Database tables created
✓ Harness ready
```

## Usage

### Python API

```python
from core.does_router import submit_for_audit, get_audit_results

# Submit code for adversarial audit
code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""

result = submit_for_audit(
    code_payload=code,
    context="Calculate Fibonacci recursively",
    max_iterations=5
)

execution_id = result['execution_id']
print(f"Execution: {execution_id}")
print(f"Status: {result['status']}")
print(f"Final Audit: {result['final_audit']}")

# Retrieve full audit trail
history = get_audit_results(execution_id)
for gen, audit in zip(history['generations'], history['audits']):
    print(f"Iteration {gen['iteration']}:")
    print(f"  Verdict: {audit['verdict']}")
    print(f"  Objections: {audit['objections']}")
    print(f"  Recommendations: {audit['recommendations']}")
```

### Shell Integration

From `seven.sh`, use:

```bash
does-audit /path/to/code.py
does-audit-result <execution-id>
```

### Direct Harness Invocation

```python
from core.does_harness import DOESLogicHarness

harness = DOESLogicHarness()

result = harness.execute_loop(
    execution_id="does-user-001",
    initial_payload="print('hello')",
    builder_node="qwen",
    villain_node="villain-node",
    max_iterations=3
)

print(f"Final phase: {result['phase']}")
print(f"Iterations: {result['loop_iteration']}")
```

## Database Schema

### does_execution

Tracks overall execution state and phase:

```
id           | execution_id | phase          | loop_iteration | max_iterations | ...
--           | does-abc123  | complete       | 2              | 5              | ...
```

### does_state

Stores each generation (iteration) of the Builder's output:

```
id | execution_id | iteration | payload | payload_type | created_at | ...
1  | does-abc123  | 1         | <code>  | code         | 2026-05-20 | ...
2  | does-abc123  | 2         | <code>  | code         | 2026-05-20 | ...
```

### does_audit

Stores each audit verdict from the Villain:

```
id | execution_id | iteration | verdict | objections | recommendations | structural_flaws | ...
1  | does-abc123  | 1         | FAIL    | ["..."]    | ["..."]         | 2                | ...
2  | does-abc123  | 2         | PASS    | []         | []              | 0                | ...
```

## The Villain Node

### System Prompt

The Villain is configured with a brutally honest system prompt:

```
You are the Adversarial Auditor (Villain Mode) in a DOES ecosystem.
Your sole objective is to aggressively challenge, stress-test, and find 
structural flaws in the data, code, or logic provided.

Rules:
1. Do not be polite. Do not use filler text.
2. Assume the previous node's output is fundamentally flawed.
3. Keep analysis concise so you don't bloat the database.
4. Output critiques as direct attack vectors for Builder to fix.
```

### Expected Response Format

The Villain responds with JSON:

```json
{
    "verdict": "FAIL",
    "objections": [
        "Inefficient recursive approach — exponential time complexity",
        "No memoization — recalculates same Fibonacci numbers repeatedly"
    ],
    "recommendations": [
        "Use memoization or dynamic programming",
        "Cache results to avoid redundant calculations"
    ],
    "structural_flaws": 2,
    "efficiency_score": 0.2
}
```

## Integration with Swarm

The DOES Framework integrates into the broader Swarm system:

### Memory Persistence

- Execution state lives in `swarm_memory.db`
- Other agents (Gemma, Eight, etc.) can query DOES results via:
  ```python
  from core.does_router import get_audit_results
  history = get_audit_results(execution_id)
  ```

### Agent Handoff

- When agents generate code that needs validation, they submit via:
  ```python
  from core.does_router import submit_for_audit
  result = submit_for_audit(code_payload, context=...)
  ```

- The Villain's findings become context for the next agent iteration

### Vortex Integration

The DOES execution trail can be logged to Vortex for traceability:

```python
from core.does_router import get_audit_results
from core.vortex_health import log_event

result = get_audit_results(execution_id)
log_event(
    category="does_audit",
    level="info",
    message=f"Execution {execution_id} completed",
    data=result
)
```

## Performance Notes

### Hardware Profile

- **CPU**: Intel Core i5-10500, 6-core, 12-thread @ 3.1GHz
- **RAM**: 33GB physical + 48GB swapfile
- **Models**: Both Qwen and Gemma quantized to Q4_K_M

### Expected Timings

- Builder generation: 30–60s for typical code block
- Villain audit: 15–30s for analysis
- Database I/O: <100ms per operation
- Full loop iteration (Gen→Audit→Revision): ~90–120s

### Memory Footprint

- Qwen-2.5-1.5B: ~3GB when loaded
- Gemma-3-4B: ~2.5GB when loaded
- SQL payload cache: <500MB for typical execution
- **Total peak**: ~5.5GB (one model + overhead)

### Optimization Strategies

1. **Limit payload size**: Keep code <5KB per iteration
2. **Cap iterations**: Default max_iterations=5; adjust based on use case
3. **Async handoff**: Unload models immediately after use to free RAM
4. **Batch operations**: Process multiple audits sequentially, not parallel

## Troubleshooting

### Ollama Connection Failed

```
Error: Ollama service check failed
```

**Solution**: Start Ollama service:
```bash
ollama serve
```

### Model Not Found

```
Error: villain-node is not registered
```

**Solution**: Re-run setup:
```bash
./setup_does.sh
```

### Database Locked

```
sqlite3.OperationalError: database is locked
```

**Solution**: Ensure only one DOES process is running; check for stale locks:
```bash
lsof /home/seven/swarm/swarm_memory.db
```

### Memory Exhaustion

```
MemoryError or swap thrashing
```

**Solution**:
- Reduce max_iterations
- Reduce payload size
- Ensure models are unloaded after use
- Check swapfile availability: `swapon --show`

## Advanced Usage

### Custom Villain Configuration

Edit `Modelfile_Villain` to adjust:

```dockerfile
PARAMETER temperature 0.3        # Lower = more deterministic
PARAMETER top_p 0.8             # Nucleus sampling threshold
PARAMETER num_ctx 4096          # Context window size
```

Rebuild with:
```bash
ollama create villain-node -f Modelfile_Villain
```

### Custom Audit Criteria

Create a specialized Villain variant:

```dockerfile
FROM gemma3:4b-instruct-q4_K_M
PARAMETER temperature 0.2

SYSTEM """
You are a Security Auditor. Find SQL injection, XSS, CSRF vulnerabilities.
Respond in JSON format: {"verdict": "SECURE|VULNERABLE", "vulnerabilities": [...]}
"""
```

### Integration with Agent Scorecards

Update `core/agent_scorecards.py` to track DOES audit quality:

```python
def record_does_audit(execution_id, verdict, flaws):
    verdict_score = 1.0 if verdict == "PASS" else 0.0
    efficiency_penalty = 0.1 * flaws
    final_score = verdict_score - efficiency_penalty
    # Store in agent_capability_scores...
```

## Files & Structure

```
/home/seven/swarm/
├── Modelfile_Villain              # Villain node configuration
├── setup_does.sh                  # Registration script
├── core/
│   ├── does_harness.py           # Core orchestration engine
│   ├── does_router.py            # High-level routing API
│   ├── ollama.py                 # Ollama model management
│   └── ...
├── tests/
│   └── test_does.py              # Integration test & demo
├── swarm_memory.db               # SQLite backend (does_* tables)
└── README.md
```

## References

- **Ollama Docs**: https://github.com/ollama/ollama
- **Modelfile Reference**: https://github.com/ollama/ollama/blob/main/docs/modelfile.md
- **Gemma Model Card**: https://huggingface.co/google/gemma-2-9b-it
- **Qwen Model Card**: https://huggingface.co/Qwen/Qwen2.5-1.5B

## License & Attribution

DOES Framework © 2026 Ghost One (Jeandre) — Part of Seven's Swarm system.

Designed for hardware-constrained inference on consumer-grade infrastructure.
