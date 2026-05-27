"""
DOES Node Executor — hardened sequential model invoker.

Pipe-leak repairs (vs. the original CLI-based executor):
  - HTTP /api/generate with options.num_ctx=4096 (CLI cannot set num_ctx).
  - keep_alive=0 on EVERY call → no idle 5-minute RAM cushion.
  - Single-resident invariant via OllamaRuntime lock.
  - Output passes through sanitizer.scrub_structural / scrub_json before
    ever touching the SQL state engine.
  - Text-file cache holds raw + scrubbed output for forensic replay.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .ollama_runtime import OllamaRuntime, OllamaUnavailable
from .sanitizer import scrub_json, scrub_structural

logger = logging.getLogger(__name__)

DEFAULT_BUILDER_MODEL = os.environ.get("DOES_BUILDER_MODEL", "qwen")
DEFAULT_VILLAIN_MODEL = os.environ.get("DOES_VILLAIN_MODEL", "villain-node")


BUILDER_SYSTEM = (
    "You are the BUILDER node of the DOES harness. "
    "Emit ONLY raw structural output (code, SQL, or plain logic text). "
    "No prose, no markdown fences, no commentary, no apologies. "
    "Begin output on the first character."
)

VILLAIN_SYSTEM = (
    "You are the VILLAIN node of the DOES harness, an adversarial code auditor. "
    "Respond with a SINGLE JSON object and nothing else. "
    "Schema: {\"verdict\": \"PASS\"|\"FAIL\", \"objections\": [string,...], "
    "\"recommendations\": [string,...], \"structural_flaws\": int, "
    "\"efficiency_score\": float between 0 and 1}."
)


class NodeExecutor:
    CACHE_DIR = Path(tempfile.gettempdir()) / "does_state_cache"

    def __init__(self) -> None:
        self.CACHE_DIR.mkdir(exist_ok=True)

    def _cache_path(self, execution_id: str, iteration, suffix: str) -> Path:
        return self.CACHE_DIR / f"{execution_id}_iter{iteration}_{suffix}.txt"

    def _write_cache(self, execution_id: str, iteration, suffix: str, content: str) -> Path:
        path = self._cache_path(execution_id, iteration, suffix)
        path.write_text(content)
        return path

    def invoke_builder(
        self,
        execution_id: str,
        iteration: int,
        prompt: str,
        task_context: str = "",
        model: Optional[str] = None,
    ) -> Optional[str]:
        model = model or DEFAULT_BUILDER_MODEL
        full_prompt = f"TASK CONTEXT:\n{task_context}\n\nINSTRUCTIONS:\n{prompt}"
        try:
            raw = OllamaRuntime.generate(
                model=model,
                prompt=full_prompt,
                system=BUILDER_SYSTEM,
                temperature=0.2,
                top_p=0.9,
            )
        except OllamaUnavailable as e:
            logger.error("builder unreachable: %s", e)
            return None

        self._write_cache(execution_id, iteration, "builder_raw", raw)
        scrubbed = scrub_structural(raw)
        self._write_cache(execution_id, iteration, "builder_clean", scrubbed)
        if not scrubbed:
            logger.error("builder produced empty payload after scrub")
            return None
        return scrubbed

    def invoke_villain(
        self,
        execution_id: str,
        iteration: int,
        payload: str,
        model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        model = model or DEFAULT_VILLAIN_MODEL
        prompt = (
            "AUDIT THE FOLLOWING PAYLOAD AGAINST THE SCHEMA IN THE SYSTEM PROMPT.\n"
            "---\n"
            f"{payload}\n"
            "---"
        )
        try:
            raw = OllamaRuntime.generate(
                model=model,
                prompt=prompt,
                system=VILLAIN_SYSTEM,
                temperature=0.3,
                top_p=0.8,
                format_json=True,
            )
        except OllamaUnavailable as e:
            logger.error("villain unreachable: %s", e)
            return None

        self._write_cache(execution_id, iteration, "villain_raw", raw)
        parsed = scrub_json(raw)
        if parsed is None:
            logger.error("villain returned unparseable JSON")
            return None
        required = {"verdict", "objections", "recommendations", "structural_flaws"}
        if not required.issubset(parsed.keys()):
            logger.error("villain JSON missing required fields: %s", list(parsed.keys()))
            return None
        parsed.setdefault("efficiency_score", 0.0)
        self._write_cache(execution_id, iteration, "villain_clean", json.dumps(parsed))
        return parsed

    def invoke_tier(
        self,
        execution_id: str,
        iteration,
        tier_name: str,
        model: str,
        system: str,
        prompt: str,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> Optional[str]:
        try:
            raw = OllamaRuntime.generate(
                model=model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                format_json=json_mode,
            )
        except OllamaUnavailable as e:
            logger.error("tier %s unreachable: %s", tier_name, e)
            return None
        self._write_cache(execution_id, iteration, f"{tier_name}_raw", raw)
        if json_mode:
            parsed = scrub_json(raw)
            if parsed is None:
                return None
            cleaned = json.dumps(parsed)
        else:
            cleaned = scrub_structural(raw)
        self._write_cache(execution_id, iteration, f"{tier_name}_clean", cleaned)
        return cleaned or None

    def cleanup_cache(self, execution_id: str) -> None:
        for f in self.CACHE_DIR.glob(f"{execution_id}_*.txt"):
            try:
                f.unlink()
            except OSError:
                pass


_executor: Optional[NodeExecutor] = None


def get_node_executor() -> NodeExecutor:
    global _executor
    if _executor is None:
        _executor = NodeExecutor()
    return _executor


__all__ = ["NodeExecutor", "get_node_executor"]
