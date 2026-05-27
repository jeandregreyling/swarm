"""
DOES Potato Farm — 4-tier assembly line for the OptiPlex 7090.

Goal: stretch utility of small quantized GGUF models far beyond the
two-node Builder+Villain loop, without breaking the Zero-Overhead RAM
principle (one model resident at a time, sequential swaps).

Tiers (each writes to does_handoff with sha256 payload hash, then evicts):

  TIER 1 — INTAKE        phi3:mini (~2.3GB)
      Classifies the incoming request: {kind, complexity, target_lang,
      required_tools}. Cheapest router; never touches the answer.

  TIER 2 — BUILDER       qwen2.5:1.5b (~1GB Q4)
      Generates the candidate payload (code/SQL/plan).

  TIER 3 — VILLAIN       villain-node (gemma3:4b Q4, ~3GB)
      Adversarial audit; emits structured JSON verdict.

  TIER 4 — SCRIBE        qwen2.5:0.5b (~0.4GB Q4)
      Final serialization pass: strips residual noise, produces the
      commit-ready artifact + a one-line audit trail summary for Studio.

Every tier transition is recorded as a does_handoff edge with a
payload_hash so the full chain is replayable from the DB alone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from .does_harness import DOESRegistry, ExecutionPhase
from .node_executor import get_node_executor

logger = logging.getLogger(__name__)


TIER1_INTAKE_SYSTEM = (
    "You are TIER-1 INTAKE of the DOES Potato Farm. "
    "Classify the user request. Respond with ONE JSON object only: "
    "{\"kind\": \"code\"|\"sql\"|\"plan\"|\"prose\", "
    "\"complexity\": \"trivial\"|\"moderate\"|\"hard\", "
    "\"target_lang\": string, "
    "\"required_tools\": [string,...]}"
)

TIER2_BUILDER_SYSTEM = (
    "You are TIER-2 BUILDER of the DOES Potato Farm. "
    "Emit ONLY the raw artifact requested. No prose, no fences."
)

TIER4_SCRIBE_SYSTEM = (
    "You are TIER-4 SCRIBE of the DOES Potato Farm. "
    "Given an audited artifact and the verdict JSON, emit the final "
    "commit-ready artifact verbatim, followed by exactly one line: "
    "'### TRAIL: <one-sentence summary of changes>'. No fences, no prose."
)


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class PotatoFarmPipeline:
    """4-tier sequential pipeline; single resident model at any time."""

    TIER_MODELS = {
        "intake": "phi3:mini",
        "builder": "qwen2.5:1.5b",
        "villain": "villain-node",
        "scribe": "qwen2.5:0.5b",
    }

    def __init__(self) -> None:
        self.registry = DOESRegistry()
        self.executor = get_node_executor()

    # -- public entry -----------------------------------------------------
    def run(
        self,
        request: str,
        max_revisions: int = 2,
    ) -> Dict[str, Any]:
        execution_id = f"farm-{uuid.uuid4().hex[:12]}"
        self.registry.create_execution(execution_id, max_iterations=max_revisions + 1)
        iteration = 1

        # TIER 1 — INTAKE
        classification = self._tier_intake(execution_id, iteration, request)
        if classification is None:
            return self._abort(execution_id, "intake_failed")

        # TIER 2 — BUILDER
        artifact = self._tier_builder(execution_id, iteration, request, classification)
        if artifact is None:
            return self._abort(execution_id, "builder_failed")
        self.registry.store_generation(execution_id, iteration, artifact)

        # TIER 3 — VILLAIN (with up to max_revisions resolution passes)
        verdict: Optional[Dict[str, Any]] = None
        for rev in range(max_revisions + 1):
            verdict = self._tier_villain(execution_id, iteration, artifact)
            if verdict is None:
                return self._abort(execution_id, "villain_failed")
            self.registry.store_audit(
                execution_id,
                iteration,
                verdict["verdict"],
                verdict.get("objections", []),
                verdict.get("recommendations", []),
                verdict.get("structural_flaws", 0),
                float(verdict.get("efficiency_score", 0.0)),
            )
            if verdict["verdict"] == "PASS" and verdict.get("structural_flaws", 0) == 0:
                break
            if rev == max_revisions:
                break
            # Resolution pass — re-invoke builder with critique.
            iteration += 1
            artifact = self._tier_builder_revise(execution_id, iteration, artifact, verdict)
            if artifact is None:
                return self._abort(execution_id, "revision_failed")
            self.registry.store_generation(execution_id, iteration, artifact)

        # TIER 4 — SCRIBE
        final = self._tier_scribe(execution_id, iteration, artifact, verdict or {})
        if final is None:
            return self._abort(execution_id, "scribe_failed")

        self.registry.mark_complete(execution_id)
        return {
            "execution_id": execution_id,
            "classification": classification,
            "iterations": iteration,
            "verdict": verdict,
            "final_artifact": final,
        }

    # -- tier implementations --------------------------------------------
    def _record(
        self,
        execution_id: str,
        iteration: int,
        phase: str,
        from_node: str,
        to_node: str,
        payload: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.registry.store_handoff(
            execution_id=execution_id,
            iteration=iteration,
            phase=phase,
            from_node=from_node,
            to_node=to_node,
            payload=payload,
            details={**(details or {}), "payload_sha256": _sha256(payload)},
        )

    def _tier_intake(
        self, execution_id: str, iteration: int, request: str
    ) -> Optional[Dict[str, Any]]:
        out = self.executor.invoke_tier(
            execution_id=execution_id,
            iteration=iteration,
            tier_name="intake",
            model=self.TIER_MODELS["intake"],
            system=TIER1_INTAKE_SYSTEM,
            prompt=request,
            json_mode=True,
            temperature=0.1,
        )
        if not out:
            return None
        self._record(
            execution_id, iteration, "intake",
            from_node="user", to_node="intake", payload=out,
        )
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None

    def _tier_builder(
        self,
        execution_id: str,
        iteration: int,
        request: str,
        classification: Dict[str, Any],
    ) -> Optional[str]:
        prompt = (
            f"CLASSIFICATION: {json.dumps(classification)}\n"
            f"REQUEST:\n{request}"
        )
        out = self.executor.invoke_tier(
            execution_id=execution_id,
            iteration=iteration,
            tier_name="builder",
            model=self.TIER_MODELS["builder"],
            system=TIER2_BUILDER_SYSTEM,
            prompt=prompt,
            json_mode=False,
            temperature=0.2,
        )
        if not out:
            return None
        self._record(
            execution_id, iteration, ExecutionPhase.GENERATION.value,
            from_node="intake", to_node="builder", payload=out,
        )
        return out

    def _tier_builder_revise(
        self,
        execution_id: str,
        iteration: int,
        prior_artifact: str,
        verdict: Dict[str, Any],
    ) -> Optional[str]:
        objections = "\n".join(f"- {o}" for o in verdict.get("objections", []))
        recs = "\n".join(f"- {r}" for r in verdict.get("recommendations", []))
        prompt = (
            "REVISE THE PRIOR ARTIFACT TO ADDRESS ALL OBJECTIONS.\n"
            f"PRIOR ARTIFACT:\n{prior_artifact}\n\n"
            f"OBJECTIONS:\n{objections}\n\nRECOMMENDATIONS:\n{recs}"
        )
        out = self.executor.invoke_tier(
            execution_id=execution_id,
            iteration=iteration,
            tier_name="builder_revise",
            model=self.TIER_MODELS["builder"],
            system=TIER2_BUILDER_SYSTEM,
            prompt=prompt,
            json_mode=False,
            temperature=0.2,
        )
        if not out:
            return None
        self._record(
            execution_id, iteration, ExecutionPhase.RESOLUTION.value,
            from_node="villain", to_node="builder", payload=out,
            details={"objection_count": len(verdict.get("objections", []))},
        )
        return out

    def _tier_villain(
        self, execution_id: str, iteration: int, artifact: str
    ) -> Optional[Dict[str, Any]]:
        self._record(
            execution_id, iteration, ExecutionPhase.HANDOFF.value,
            from_node="builder", to_node="villain", payload=artifact,
            details={"action": "model_swap", "keep_alive": 0},
        )
        result = self.executor.invoke_villain(
            execution_id=execution_id,
            iteration=iteration,
            payload=artifact,
            model=self.TIER_MODELS["villain"],
        )
        if result is None:
            return None
        self._record(
            execution_id, iteration, ExecutionPhase.AUDIT.value,
            from_node="villain", to_node="harness", payload=json.dumps(result),
            details={"verdict": result.get("verdict")},
        )
        return result

    def _tier_scribe(
        self,
        execution_id: str,
        iteration: int,
        artifact: str,
        verdict: Dict[str, Any],
    ) -> Optional[str]:
        prompt = (
            f"AUDITED ARTIFACT:\n{artifact}\n\n"
            f"VERDICT JSON:\n{json.dumps(verdict)}"
        )
        out = self.executor.invoke_tier(
            execution_id=execution_id,
            iteration=iteration,
            tier_name="scribe",
            model=self.TIER_MODELS["scribe"],
            system=TIER4_SCRIBE_SYSTEM,
            prompt=prompt,
            json_mode=False,
            temperature=0.1,
        )
        if not out:
            return None
        self._record(
            execution_id, iteration, ExecutionPhase.COMPLETE.value,
            from_node="harness", to_node="scribe", payload=out,
        )
        return out

    def _abort(self, execution_id: str, reason: str) -> Dict[str, Any]:
        self._record(
            execution_id, 0, "abort",
            from_node="harness", to_node="harness", payload=reason,
        )
        return {"execution_id": execution_id, "error": f"HARNESS_BREAK: {reason}"}


def run_farm(request: str, max_revisions: int = 2) -> Dict[str, Any]:
    return PotatoFarmPipeline().run(request, max_revisions=max_revisions)


__all__ = ["PotatoFarmPipeline", "run_farm"]
