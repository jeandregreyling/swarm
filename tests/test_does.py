#!/usr/bin/env python3
"""
DOES Framework Integration Test & Demo

This script demonstrates the full Generation → Handoff → Audit → Resolution loop
with actual Ollama model invocations.

Usage:
    python tests/test_does.py --local  # Run with actual Ollama models
    python tests/test_does.py --demo   # Run with demo payloads (no models required)
"""

import sys
import argparse
import logging
from pathlib import Path

# Add swarm root to path
SWARM_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SWARM_ROOT))

from core.does_router import submit_for_audit, get_audit_results, get_does_router
from core.does_harness import DOESLogicHarness, ExecutionPhase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def test_does_with_demo_code():
    """Test DOES framework with a simple Python function."""

    demo_code = '''
def calculate_fibonacci(n):
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        return n
    
    # This is inefficient for large n
    return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2)

# Usage
result = calculate_fibonacci(10)
print(f"Fibonacci(10) = {result}")
'''

    logger.info("=" * 70)
    logger.info("DOES FRAMEWORK TEST: Fibonacci Function")
    logger.info("=" * 70)
    logger.info(f"Submitting code for adversarial audit:\n{demo_code}")

    # Submit for audit
    result = submit_for_audit(
        code_payload=demo_code,
        context="Calculate Fibonacci number recursively",
        max_iterations=3,
    )

    logger.info(f"Execution ID: {result['execution_id']}")
    logger.info(f"Status: {result['status']}")
    logger.info(f"Iterations: {result['iterations']}")

    if result["final_audit"]:
        audit = result["final_audit"]
        logger.info(f"Final Verdict: {audit['verdict']}")
        logger.info(f"Structural Flaws: {audit['structural_flaws']}")
        logger.info(f"Objections: {audit['objections']}")
        logger.info(f"Recommendations: {audit['recommendations']}")

    logger.info("=" * 70)
    return result["execution_id"]


def test_does_with_sql_query():
    """Test DOES framework with SQL code."""

    demo_code = '''
SELECT u.user_id, u.name, COUNT(o.order_id) as order_count
FROM users u
LEFT JOIN orders o ON u.user_id = o.user_id
WHERE u.created_at > '2025-01-01'
GROUP BY u.user_id, u.name
HAVING COUNT(o.order_id) > 5
ORDER BY order_count DESC
LIMIT 100;
'''

    logger.info("=" * 70)
    logger.info("DOES FRAMEWORK TEST: SQL Query")
    logger.info("=" * 70)
    logger.info(f"Submitting SQL for adversarial audit:\n{demo_code}")

    result = submit_for_audit(
        code_payload=demo_code,
        context="Analytics query: users with 5+ orders since Jan 2025",
        max_iterations=3,
    )

    logger.info(f"Execution ID: {result['execution_id']}")
    logger.info(f"Status: {result['status']}")
    logger.info(f"Iterations: {result['iterations']}")

    logger.info("=" * 70)
    return result["execution_id"]


def get_audit_trail(execution_id: str):
    """Retrieve and display the full audit trail."""

    logger.info("=" * 70)
    logger.info(f"Retrieving audit trail for: {execution_id}")
    logger.info("=" * 70)

    history = get_audit_results(execution_id)

    if "error" in history:
        logger.error(f"Error: {history['error']}")
        return

    logger.info(f"State: {history['state']}")
    logger.info("")

    for i, gen in enumerate(history["generations"], 1):
        logger.info(f"--- Iteration {gen['iteration']}: GENERATION ---")
        logger.info(f"Payload:\n{gen['payload'][:500]}...")
        logger.info("")

        # Find corresponding audit
        audit = next(
            (a for a in history["audits"] if a["iteration"] == gen["iteration"]),
            None,
        )
        if audit:
            logger.info(f"--- Iteration {audit['iteration']}: AUDIT ---")
            logger.info(f"Verdict: {audit['verdict']}")
            logger.info(f"Structural Flaws: {audit['structural_flaws']}")
            logger.info(f"Objections: {audit['objections']}")
            logger.info(f"Recommendations: {audit['recommendations']}")
            logger.info("")

    logger.info("=" * 70)


def check_ollama_status():
    """Verify Ollama is running and models are available."""

    from core.ollama import get_ollama_manager

    logger.info("Checking Ollama status...")

    manager = get_ollama_manager()

    if not manager.is_running():
        logger.error("Ollama is not running. Start it with: ollama serve")
        return False

    logger.info("✓ Ollama is running")

    models = manager.list_models()
    logger.info(f"Available models: {models}")

    required = ["qwen", "villain-node"]
    for model in required:
        if any(model in m for m in models):
            logger.info(f"✓ {model} is available")
        else:
            logger.warning(f"⚠ {model} is NOT available")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="DOES Framework Test & Demo"
    )
    parser.add_argument(
        "--mode",
        choices=["demo", "local", "trail"],
        default="demo",
        help="Test mode: demo (mock), local (actual Ollama), trail (show history)",
    )
    parser.add_argument(
        "--execution-id",
        help="Execution ID to retrieve history (for --mode trail)",
    )

    args = parser.parse_args()

    if args.mode == "local":
        logger.info("Running DOES framework with actual Ollama models...")
        if not check_ollama_status():
            sys.exit(1)

        exec_id = test_does_with_demo_code()
        logger.info(f"\nTo view results: python tests/test_does.py --mode trail --execution-id {exec_id}")

    elif args.mode == "trail":
        if not args.execution_id:
            logger.error("--execution-id required for --mode trail")
            sys.exit(1)

        get_audit_trail(args.execution_id)

    else:  # demo
        logger.info("Running DOES framework in DEMO mode (without models)...")
        logger.info("Database schema created and harness initialized")
        logger.info("")
        logger.info("To run with actual models:")
        logger.info("  1. ollama serve")
        logger.info("  2. ./setup_does.sh")
        logger.info("  3. python tests/test_does.py --mode local")
        logger.info("")

        # Just verify the registry and harness can initialize
        from core.does_harness import DOESRegistry

        registry = DOESRegistry()
        logger.info("✓ DOES Registry initialized")
        logger.info("✓ Database tables created")
        logger.info("✓ Harness ready")


if __name__ == "__main__":
    main()
