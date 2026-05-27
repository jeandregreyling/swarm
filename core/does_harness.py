"""
DOES Framework — Logic Harness for Hardware-Constrained Orchestration

This module implements the core orchestration engine for the DOES framework:
- Manages Generation → Handoff → Audit → Resolution loop
- Persists state to SQL to minimize RAM footprint
- Loads only one quantized model at a time into system memory
- Coordinates between Builder (Qwen) and Villain (Gemma-adversarial) nodes

HARDWARE TARGET: Dell OptiPlex 7090 (6-core i5-10500, 33GB RAM, no GPU)
"""

import json
import sqlite3
import logging
import hashlib
from typing import Optional, Dict, Any, List
from enum import Enum

from utils.db import get_connection
from .node_executor import get_node_executor

logger = logging.getLogger(__name__)


class NodeRole(Enum):
    """Roles in the DOES execution council."""
    BUILDER = "builder"      # Qwen: generates code/logic
    VILLAIN = "villain"      # Gemma: audits and tears apart
    HARNESS = "harness"      # Logic orchestrator


class ExecutionPhase(Enum):
    """State machine phases for the handoff loop."""
    GENERATION = "generation"      # Builder writes to state_table
    HANDOFF = "handoff"           # Harness unloads Builder, loads Villain
    AUDIT = "audit"               # Villain analyzes and writes to audit_table
    RESOLUTION = "resolution"     # Builder revises based on audit feedback
    COMPLETE = "complete"         # Zero objections achieved


class DOESRegistry:
    """Manages DOES execution state and persistence."""

    def __init__(self):
        self._init_tables()

    def _init_tables(self):
        """Create DOES tables if they don't exist."""
        conn = get_connection()
        cursor = conn.cursor()

        # DOES execution state tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS does_execution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT UNIQUE NOT NULL,
                phase TEXT DEFAULT 'generation',
                builder_node TEXT DEFAULT 'qwen',
                villain_node TEXT DEFAULT 'villain-node',
                loop_iteration INTEGER DEFAULT 0,
                max_iterations INTEGER DEFAULT 5,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT
            )
        """)

        # Builder's generated code/logic payload
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS does_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                payload TEXT NOT NULL,
                payload_type TEXT DEFAULT 'code',
                metadata TEXT DEFAULT '{}',
                node TEXT DEFAULT 'builder',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(execution_id) REFERENCES does_execution(execution_id),
                UNIQUE(execution_id, iteration)
            )
        """)

        # Villain's audit findings and objections
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS does_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                verdict TEXT,
                objections TEXT DEFAULT '[]',
                recommendations TEXT DEFAULT '[]',
                structural_flaws INTEGER DEFAULT 0,
                efficiency_score REAL DEFAULT 0.0,
                node TEXT DEFAULT 'villain',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(execution_id) REFERENCES does_execution(execution_id),
                UNIQUE(execution_id, iteration)
            )
        """)

        # Explicit handoff trace so the Builder -> Villain flow is visible.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS does_handoff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                phase TEXT NOT NULL,
                from_node TEXT NOT NULL,
                to_node TEXT NOT NULL,
                payload_hash TEXT DEFAULT '',
                details TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_does_handoff_exec_iter
            ON does_handoff (execution_id, iteration, phase)
            """
        )

        conn.commit()
        conn.close()
        logger.info("DOES tables initialized")

    def create_execution(self, execution_id: str, max_iterations: int = 5) -> str:
        """Start a new DOES execution loop."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO does_execution (execution_id, phase, max_iterations)
            VALUES (?, ?, ?)
            """,
            (execution_id, ExecutionPhase.GENERATION.value, max_iterations),
        )
        conn.commit()
        conn.close()

        logger.info(f"Created execution: {execution_id}")
        return execution_id

    def store_generation(
        self, execution_id: str, iteration: int, payload: str, payload_type: str = "code"
    ) -> bool:
        """Store Builder's generated payload in state_table."""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO does_state (execution_id, iteration, payload, payload_type)
                VALUES (?, ?, ?, ?)
                """,
                (execution_id, iteration, payload, payload_type),
            )

            # Update execution phase to HANDOFF
            cursor.execute(
                """
                UPDATE does_execution
                SET phase = ?, loop_iteration = ?, updated_at = datetime('now')
                WHERE execution_id = ?
                """,
                (ExecutionPhase.HANDOFF.value, iteration, execution_id),
            )

            conn.commit()
            logger.info(f"Stored generation for {execution_id} iteration {iteration}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Generation storage failed: {e}")
            return False
        finally:
            conn.close()

    def get_generation(self, execution_id: str, iteration: int) -> Optional[str]:
        """Retrieve Builder's payload for Villain to audit."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT payload FROM does_state
            WHERE execution_id = ? AND iteration = ?
            """,
            (execution_id, iteration),
        )

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def store_audit(
        self,
        execution_id: str,
        iteration: int,
        verdict: str,
        objections: List[str],
        recommendations: List[str],
        structural_flaws: int = 0,
        efficiency_score: float = 0.0,
    ) -> bool:
        """Store Villain's audit findings in audit_table."""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO does_audit
                (execution_id, iteration, verdict, objections, recommendations, 
                 structural_flaws, efficiency_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    iteration,
                    verdict,
                    json.dumps(objections),
                    json.dumps(recommendations),
                    structural_flaws,
                    efficiency_score,
                ),
            )

            # Update phase based on verdict
            phase = (
                ExecutionPhase.COMPLETE.value
                if verdict == "PASS" and structural_flaws == 0
                else ExecutionPhase.RESOLUTION.value
            )

            cursor.execute(
                """
                UPDATE does_execution
                SET phase = ?, updated_at = datetime('now')
                WHERE execution_id = ?
                """,
                (phase, execution_id),
            )

            conn.commit()
            logger.info(f"Stored audit for {execution_id} iteration {iteration}: {verdict}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Audit storage failed: {e}")
            return False
        finally:
            conn.close()

    def get_audit(self, execution_id: str, iteration: int) -> Optional[Dict[str, Any]]:
        """Retrieve Villain's audit findings for Builder to resolve."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT verdict, objections, recommendations, structural_flaws, efficiency_score
            FROM does_audit
            WHERE execution_id = ? AND iteration = ?
            """,
            (execution_id, iteration),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "verdict": row[0],
                "objections": json.loads(row[1]),
                "recommendations": json.loads(row[2]),
                "structural_flaws": row[3],
                "efficiency_score": row[4],
            }
        return None

    def get_execution_state(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get full execution state."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT phase, loop_iteration, max_iterations, created_at, updated_at
            FROM does_execution
            WHERE execution_id = ?
            """,
            (execution_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "phase": row[0],
                "loop_iteration": row[1],
                "max_iterations": row[2],
                "created_at": row[3],
                "updated_at": row[4],
            }
        return None

    def store_handoff(
        self,
        execution_id: str,
        iteration: int,
        phase: str,
        from_node: str,
        to_node: str,
        payload: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persist handoff edges for visibility and diagnostics."""
        conn = get_connection()
        cursor = conn.cursor()
        payload_hash = hashlib.sha256((payload or "").encode("utf-8")).hexdigest()
        meta = json.dumps(details or {})

        try:
            cursor.execute(
                """
                INSERT INTO does_handoff
                (execution_id, iteration, phase, from_node, to_node, payload_hash, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    iteration,
                    phase,
                    from_node,
                    to_node,
                    payload_hash,
                    meta,
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Handoff storage failed: {e}")
            return False
        finally:
            conn.close()

    def get_handoffs(self, execution_id: str) -> List[Dict[str, Any]]:
        """Return all handoff edges for an execution in order."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT iteration, phase, from_node, to_node, payload_hash, details, created_at
            FROM does_handoff
            WHERE execution_id = ?
            ORDER BY id
            """,
            (execution_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        out = []
        for row in rows:
            out.append(
                {
                    "iteration": row[0],
                    "phase": row[1],
                    "from_node": row[2],
                    "to_node": row[3],
                    "payload_hash": row[4],
                    "details": json.loads(row[5] or "{}"),
                    "created_at": row[6],
                }
            )
        return out

    def should_continue_loop(self, execution_id: str) -> bool:
        """Check if execution should continue (not COMPLETE and under max iterations)."""
        state = self.get_execution_state(execution_id)
        if not state:
            return False

        if state["phase"] == ExecutionPhase.COMPLETE.value:
            return False

        if state["loop_iteration"] >= state["max_iterations"]:
            logger.warning(
                f"Max iterations ({state['max_iterations']}) reached for {execution_id}"
            )
            return False

        return True

    def mark_complete(self, execution_id: str) -> bool:
        """Mark execution as complete."""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE does_execution
            SET phase = ?, completed_at = datetime('now')
            WHERE execution_id = ?
            """,
            (ExecutionPhase.COMPLETE.value, execution_id),
        )

        conn.commit()
        conn.close()
        logger.info(f"Marked execution as complete: {execution_id}")
        return True


class DOESLogicHarness:
    """
    The orchestration engine that manages the Generation → Handoff → Audit → Resolution loop.

    This harness:
    1. Receives initial code/logic from Builder node
    2. Stores it in does_state table
    3. Unloads Builder from memory
    4. Loads Villain node to audit the payload
    5. Stores Villain's findings in does_audit table
    6. Passes findings back to Builder for revision
    7. Repeats until Villain returns zero objections or max iterations reached
    """

    def __init__(self):
        self.registry = DOESRegistry()
        self.logger = logger

    def _log_studio_handoff(
        self,
        execution_id: str,
        iteration: int,
        phase: str,
        from_node: str,
        to_node: str,
        details: Dict[str, Any],
    ) -> None:
        """Best-effort Studio project note; never break runtime if Studio is down."""
        try:
            from scripts.studio_milestone import log_milestone

            title = f"DOES handoff {phase}: {from_node} -> {to_node}"
            story = (
                f"execution_id: {execution_id}\n"
                f"iteration: {iteration}\n"
                f"phase: {phase}\n"
                f"from_node: {from_node}\n"
                f"to_node: {to_node}\n"
                f"details: {json.dumps(details, ensure_ascii=True)}"
            )
            log_milestone(
                packet="PACKET-04",
                title=title,
                story=story,
                status="doing",
            )
        except Exception as e:
            self.logger.debug(f"Studio handoff log skipped: {e}")

    def execute_loop(
        self,
        execution_id: str,
        initial_payload: str,
        builder_node: str = "qwen",
        villain_node: str = "villain-node",
        max_iterations: int = 5,
    ) -> Dict[str, Any]:
        """
        Execute the full DOES loop.

        Args:
            execution_id: Unique identifier for this execution
            initial_payload: Builder's initial code/logic
            builder_node: Name of Builder node in Ollama
            villain_node: Name of Villain node in Ollama
            max_iterations: Maximum audit-fix loops before timeout

        Returns:
            Final execution state with outcome
        """
        self.registry.create_execution(execution_id, max_iterations)

        iteration = 1
        current_payload = initial_payload

        while self.registry.should_continue_loop(execution_id):
            self.logger.info(f"Iteration {iteration}: GENERATION phase")

            # Phase 1: GENERATION - Store Builder's payload
            if not self.registry.store_generation(
                execution_id, iteration, current_payload, payload_type="code"
            ):
                self.logger.error(f"Failed to store generation for iteration {iteration}")
                break

            self.registry.store_handoff(
                execution_id=execution_id,
                iteration=iteration,
                phase=ExecutionPhase.GENERATION.value,
                from_node=NodeRole.BUILDER.value,
                to_node=NodeRole.HARNESS.value,
                payload=current_payload,
                details={"payload_size": len(current_payload or "")},
            )

            # Phase 2: HANDOFF - Simulate unloading Builder, loading Villain
            self.logger.info(f"Iteration {iteration}: HANDOFF phase (Builder→Villain)")
            self.registry.store_handoff(
                execution_id=execution_id,
                iteration=iteration,
                phase=ExecutionPhase.HANDOFF.value,
                from_node=builder_node,
                to_node=villain_node,
                payload=current_payload,
                details={"action": "model_swap", "keep_alive": "0s"},
            )
            self._log_studio_handoff(
                execution_id=execution_id,
                iteration=iteration,
                phase=ExecutionPhase.HANDOFF.value,
                from_node=builder_node,
                to_node=villain_node,
                details={"action": "audit_dispatch"},
            )

            # Phase 3: AUDIT - Villain analyzes payload
            self.logger.info(f"Iteration {iteration}: AUDIT phase")
            audit_result = self._invoke_villain(
                execution_id=execution_id,
                iteration=iteration,
                payload=current_payload,
                model_name=villain_node,
            )

            if not audit_result:
                self.logger.error(f"Villain invocation failed for iteration {iteration}")
                break

            # Store audit findings
            if not self.registry.store_audit(
                execution_id,
                iteration,
                audit_result["verdict"],
                audit_result.get("objections", []),
                audit_result.get("recommendations", []),
                audit_result.get("structural_flaws", 0),
                audit_result.get("efficiency_score", 0.0),
            ):
                self.logger.error(f"Failed to store audit for iteration {iteration}")
                break

            self.registry.store_handoff(
                execution_id=execution_id,
                iteration=iteration,
                phase=ExecutionPhase.AUDIT.value,
                from_node=villain_node,
                to_node=NodeRole.HARNESS.value,
                payload=json.dumps(audit_result),
                details={"verdict": audit_result.get("verdict", "UNKNOWN")},
            )

            # Check if execution is complete
            state = self.registry.get_execution_state(execution_id)
            if state["phase"] == ExecutionPhase.COMPLETE.value:
                self.logger.info(f"Execution {execution_id} COMPLETE: Zero objections")
                break

            # Phase 4: RESOLUTION - Builder fixes issues
            self.logger.info(f"Iteration {iteration}: RESOLUTION phase (Builder revises)")
            current_payload = self._invoke_builder_revision(
                execution_id=execution_id,
                iteration=iteration,
                current_payload=current_payload,
                critique=audit_result,
                model_name=builder_node,
            )

            self.registry.store_handoff(
                execution_id=execution_id,
                iteration=iteration,
                phase=ExecutionPhase.RESOLUTION.value,
                from_node=builder_node,
                to_node=NodeRole.HARNESS.value,
                payload=current_payload,
                details={
                    "objections": len(audit_result.get("objections", [])),
                    "recommendations": len(audit_result.get("recommendations", [])),
                },
            )

            iteration += 1

        # Final state
        final_state = self.registry.get_execution_state(execution_id)
        self.logger.info(f"Execution {execution_id} finished: {final_state}")

        return final_state

    def _invoke_villain(
        self,
        execution_id: str,
        iteration: int,
        payload: str,
        model_name: str = "villain-node",
    ) -> Optional[Dict]:
        """
        Invoke the Villain node to audit the payload.

        Uses hardened NodeExecutor for:
        - Strict JSON-only output enforcement
        - Intermediate text cache (not direct DB insertion)
        - Explicit model unload (keep_alive=0)
        """
        executor = get_node_executor()

        result = executor.invoke_villain(
            execution_id=execution_id,
            iteration=iteration,
            payload=payload,
        )

        if result:
            return {
                "verdict": result.get("verdict", "UNKNOWN"),
                "objections": result.get("objections", []),
                "recommendations": result.get("recommendations", []),
                "structural_flaws": result.get("structural_flaws", 0),
                "efficiency_score": result.get("efficiency_score", 0.0),
            }
        else:
            self.logger.error(f"Villain invocation failed")
            return None

    def _invoke_builder_revision(
        self,
        execution_id: str,
        iteration: int,
        current_payload: str,
        critique: Dict,
        model_name: str = "qwen",
    ) -> str:
        """
        Invoke the Builder node to revise payload based on critique.

        Uses hardened NodeExecutor for:
        - Strict structural-only output enforcement (no markdown)
        - Intermediate text cache (not direct DB insertion)
        - Explicit model unload (keep_alive=0)
        """
        executor = get_node_executor()

        # Format the critique into a concise revision prompt
        objections_text = "\n".join(
            [f"  - {obj}" for obj in critique.get("objections", [])]
        )
        recommendations_text = "\n".join(
            [f"  - {rec}" for rec in critique.get("recommendations", [])]
        )

        revision_prompt = f"""REVISE THIS CODE BASED ON ADVERSARIAL FEEDBACK:

ORIGINAL CODE:
{current_payload}

OBJECTIONS FROM AUDITOR:
{objections_text}

RECOMMENDATIONS:
{recommendations_text}

GENERATE REVISED CODE THAT ADDRESSES ALL OBJECTIONS. OUTPUT CODE ONLY."""

        revised = executor.invoke_builder(
            execution_id=execution_id,
            iteration=iteration,
            prompt=revision_prompt,
            task_context="Code revision after adversarial audit",
            model=model_name,
        )

        if revised:
            return revised
        else:
            # Return original if revision fails
            self.logger.warning(f"Builder revision failed, returning original payload")
            return current_payload


# Export public interface
__all__ = ["DOESRegistry", "DOESLogicHarness", "ExecutionPhase", "NodeRole"]
