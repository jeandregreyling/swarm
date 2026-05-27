"""
DOES Router — Interface between frontend/agents and DOES Logic Harness

Routes execution requests through the Generation → Handoff → Audit → Resolution loop.
Integrates with swarm's central routing and message passing.
"""

import uuid
from typing import Dict, Any, Optional
import logging

from .does_harness import DOESLogicHarness, DOESRegistry, ExecutionPhase
from utils.db import get_connection

logger = logging.getLogger(__name__)


class DOESRouter:
    """High-level router for DOES execution requests."""

    def __init__(self):
        self.harness = DOESLogicHarness()
        self.registry = DOESRegistry()

    def audit_code(
        self,
        code_payload: str,
        context: Optional[str] = None,
        max_iterations: int = 5,
    ) -> Dict[str, Any]:
        """
        Submit code for adversarial audit loop.

        Args:
            code_payload: The code/logic to audit
            context: Optional context about the code's purpose
            max_iterations: Max Builder-Villain iterations

        Returns:
            Execution result with final verdict and recommendations
        """
        execution_id = f"does-{uuid.uuid4().hex[:12]}"

        logger.info(f"Submitting code audit: {execution_id}")

        # Execute the full loop
        result = self.harness.execute_loop(
            execution_id=execution_id,
            initial_payload=code_payload,
            max_iterations=max_iterations,
        )

        # Gather final audit trail
        final_audit = self.registry.get_audit(
            execution_id, result.get("loop_iteration", 1)
        )

        return {
            "execution_id": execution_id,
            "status": result.get("phase"),
            "iterations": result.get("loop_iteration"),
            "final_audit": final_audit,
            "context": context,
        }

    def get_execution_history(self, execution_id: str) -> Dict[str, Any]:
        """Retrieve full audit trail for an execution."""
        state = self.registry.get_execution_state(execution_id)

        if not state:
            return {"error": f"Execution not found: {execution_id}"}

        conn = get_connection()
        cursor = conn.cursor()

        # Fetch all generations and audits for this execution
        cursor.execute(
            """
            SELECT iteration, payload
            FROM does_state
            WHERE execution_id = ?
            ORDER BY iteration
            """,
            (execution_id,),
        )
        generations = [
            {"iteration": row[0], "payload": row[1]} for row in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT iteration, verdict, objections, recommendations, structural_flaws
            FROM does_audit
            WHERE execution_id = ?
            ORDER BY iteration
            """,
            (execution_id,),
        )
        audits = [
            {
                "iteration": row[0],
                "verdict": row[1],
                "objections": row[2],
                "recommendations": row[3],
                "structural_flaws": row[4],
            }
            for row in cursor.fetchall()
        ]

        conn.close()
        handoffs = self.registry.get_handoffs(execution_id)

        return {
            "execution_id": execution_id,
            "state": state,
            "generations": generations,
            "audits": audits,
            "handoffs": handoffs,
        }


# Singleton instance for module-level access
_router = None


def get_does_router() -> DOESRouter:
    """Get or create the DOES router singleton."""
    global _router
    if _router is None:
        _router = DOESRouter()
    return _router


def submit_for_audit(
    code_payload: str, context: Optional[str] = None, max_iterations: int = 5
) -> Dict[str, Any]:
    """Convenience function to submit code for adversarial audit."""
    router = get_does_router()
    return router.audit_code(code_payload, context, max_iterations)


def get_audit_results(execution_id: str) -> Dict[str, Any]:
    """Convenience function to retrieve audit history."""
    router = get_does_router()
    return router.get_execution_history(execution_id)
