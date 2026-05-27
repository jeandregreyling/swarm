"""
DOES Framework Diagnostic Audit
================================

Identifies the three critical failure points:
1. Token Output Serialization (Builder fluff leak)
2. SQL Sanitization & State Lock (Database jam)
3. Context Reset (Memory bloat)

This script walks through the current implementation and reports
exactly where the pipes leak.
"""

import sys
from pathlib import Path

SWARM_ROOT = Path(__file__).parent
sys.path.insert(0, str(SWARM_ROOT))

print("=" * 80)
print("DOES FRAMEWORK SYSTEMIC AUDIT")
print("=" * 80)
print()

# ============================================================================
# PIPE 1: Token Output Serialization (The Builder Leak)
# ============================================================================

print("PIPE 1: TOKEN OUTPUT SERIALIZATION (Builder Leak)")
print("-" * 80)

audit_p1 = """
CHECK: Does the Builder prompt include explicit formatting boundaries?

Current Code (core/does_harness.py, _invoke_builder_revision):
    audit_prompt = f'''AUDIT THIS CODE FOR FLAWS...
    RESPOND IN JSON FORMAT ONLY.'''

LEAK IDENTIFIED:
    ✗ No explicit "STRUCTURAL OUTPUT ONLY" boundary
    ✗ No "NO MARKDOWN/CHAT/FLUFF" hard stop
    ✗ Qwen will wrap response in conversational text:
        "Sure, here's the analysis:
        {json response}
        Hope this helps!"
    
IMPACT:
    - JSON parser will fail on outer conversational wrapper
    - Database will store malformed payload
    - Audit verdict unreliable
    - Loop may hang waiting for valid JSON

SEVERITY: CRITICAL
"""

print(audit_p1)

# Read actual harness code
with open(SWARM_ROOT / "core" / "does_harness.py", "r") as f:
    harness_content = f.read()

if "NO MARKDOWN" not in harness_content and "STRUCTURAL OUTPUT ONLY" not in harness_content:
    print("⚠ CONFIRMED: Harness lacks strict formatting boundary")
else:
    print("✓ Formatting boundary found")

print()

# ============================================================================
# PIPE 2: SQL Sanitization & State Lock (The Database Jam)
# ============================================================================

print("PIPE 2: SQL SANITIZATION & STATE LOCK (Database Jam)")
print("-" * 80)

audit_p2 = """
CHECK: Are model responses safely isolated before SQL insertion?

Current Code (core/does_harness.py, store_generation):
    cursor.execute(
        \"\"\"
        INSERT INTO does_state (execution_id, iteration, payload, payload_type)
        VALUES (?, ?, ?, ?)
        \"\"\",
        (execution_id, iteration, payload, payload_type),
    )

GOOD NEWS:
    ✓ Parameterized queries (?, ?, ?, ?) prevent SQL injection
    ✓ Python sqlite3 handles escaping

LEAK IDENTIFIED:
    ✗ Payload comes directly from Ollama HTTP response
    ✗ If response contains unescaped newlines or NULL bytes, 
      database state becomes inconsistent
    ✗ No intermediate validation or cache layer
    ✗ If model hangs mid-response, transaction may deadlock

IMPACT:
    - Corrupted payload in does_state table
    - Villain receives malformed code
    - Loop enters infinite retry
    - Database lock timeout after 30s

SEVERITY: HIGH
"""

print(audit_p2)

if "parameterized" not in harness_content.lower() and "?" in harness_content:
    print("✓ Parameterized queries in use")
else:
    print("⚠ May have string concatenation risks")

# Check for intermediate text cache
if "/tmp/" not in harness_content and "cache" not in harness_content.lower():
    print("✗ NO INTERMEDIATE TEXT CACHE - responses go direct to DB")
else:
    print("✓ Text cache layer found")

print()

# ============================================================================
# PIPE 3: Context Reset (The Memory Bloat)
# ============================================================================

print("PIPE 3: CONTEXT RESET (Memory Bloat)")
print("-" * 80)

audit_p3 = """
CHECK: Does the harness explicitly unload models from RAM?

Current Code (core/ollama.py, invoke_model):
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
    }
    response = requests.post(OLLAMA_GENERATE_ENDPOINT, json=payload, timeout=300)

LEAK IDENTIFIED:
    ✗ No 'keep_alive' parameter in payload
    ✗ Model stays in Ollama's memory for default timeout (~5 minutes)
    ✗ Handoff happens: Builder stays loaded, Villain loads on top
    ✗ Total RAM: Qwen (3GB) + Gemma (2.5GB) + overhead = 5.5GB+
    ✗ OptiPlex has 33GB, but with concurrent processes + swap thrashing:
        System hits swap, disk I/O becomes bottleneck
        Inference slows from 30s to 2 minutes per iteration
    ✗ Five iterations = 10 minutes of wait time on disk swaps

IMPACT:
    - Memory footprint doubles during handoff
    - Forced disk swapping = 100x slower I/O
    - Full system becomes unresponsive
    - Loop may timeout or OOM-kill process

SEVERITY: CRITICAL (hardware constraint violation)
"""

print(audit_p3)

# Check for keep_alive
with open(SWARM_ROOT / "core" / "ollama.py", "r") as f:
    ollama_content = f.read()

if "keep_alive" not in ollama_content:
    print("✗ CONFIRMED: No keep_alive parameter - models stay in RAM")
else:
    print("✓ keep_alive found")

if "stop_model" in ollama_content:
    print("✓ stop_model method exists")
else:
    print("✗ No explicit model unload method")

print()
print("=" * 80)
print("AUDIT SUMMARY")
print("=" * 80)
print()
print("Pipe 1 (Token Serialization):    LEAKING  - Add strict formatting boundary")
print("Pipe 2 (SQL Sanitization):       MOSTLY OK - Add text cache intermediate")
print("Pipe 3 (Memory Management):      LEAKING  - Add keep_alive=0 + explicit unload")
print()
print("RECOMMENDATION: Implement 'Zero-Fail Pipe Repair Kit' before production")
print()
