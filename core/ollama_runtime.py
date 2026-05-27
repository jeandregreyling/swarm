"""
DOES Ollama Runtime — single-model RAM custodian.

Enforces the Zero-Overhead RAM Principle:
  - Exactly one model resident at a time.
  - num_ctx pinned (default 4096) so Ollama cannot pre-allocate larger cushions
    that swallow the INT4/GGUF quantization gain.
  - keep_alive=0 forces unload the instant a call returns.
  - HTTP API only (CLI does not accept per-call num_ctx).
  - Active model tracked in process; explicit eject before next load.

This is a hard runtime contract. If Ollama is unreachable, callers must
return HARNESS_BREAK upstream — never silently fall back to a different model.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_NUM_CTX = int(os.environ.get("DOES_NUM_CTX", "4096"))
DEFAULT_TIMEOUT = int(os.environ.get("DOES_OLLAMA_TIMEOUT", "180"))


class OllamaUnavailable(RuntimeError):
    pass


class OllamaRuntime:
    _lock = threading.Lock()
    _active_model: Optional[str] = None

    @classmethod
    def _post(cls, path: str, body: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        url = f"{OLLAMA_HOST}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise OllamaUnavailable(f"ollama {path} unreachable: {e}") from e
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise OllamaUnavailable(f"ollama {path} returned non-JSON: {e}") from e

    @classmethod
    def eject(cls, model: Optional[str] = None) -> None:
        """Force-unload a specific model (or the currently active one)."""
        target = model or cls._active_model
        if not target:
            return
        try:
            # keep_alive=0 with empty prompt triggers immediate unload.
            cls._post(
                "/api/generate",
                {"model": target, "prompt": "", "keep_alive": 0, "stream": False},
                timeout=15,
            )
            logger.info("ollama_runtime: ejected %s", target)
        except OllamaUnavailable as e:
            logger.warning("ollama_runtime: eject failed for %s: %s", target, e)
        finally:
            if cls._active_model == target:
                cls._active_model = None

    @classmethod
    def generate(
        cls,
        model: str,
        prompt: str,
        *,
        num_ctx: int = DEFAULT_NUM_CTX,
        temperature: float = 0.3,
        top_p: float = 0.8,
        num_predict: int = -1,
        timeout: int = DEFAULT_TIMEOUT,
        system: Optional[str] = None,
        format_json: bool = False,
    ) -> str:
        """
        Run a single sequential generation. Returns raw model text.
        Enforces single-resident-model invariant under a lock.
        """
        with cls._lock:
            # Hot-swap: eject the previous resident first.
            if cls._active_model and cls._active_model != model:
                cls.eject(cls._active_model)
                cls._active_model = None

            body: Dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": 0,
                "options": {
                    "num_ctx": num_ctx,
                    "temperature": temperature,
                    "top_p": top_p,
                    "num_predict": num_predict,
                },
            }
            if system:
                body["system"] = system
            if format_json:
                body["format"] = "json"

            cls._active_model = model
            try:
                resp = cls._post("/api/generate", body, timeout=timeout)
            finally:
                # keep_alive=0 should have unloaded; clear our tracker either way.
                cls._active_model = None

            return resp.get("response", "") or ""


__all__ = ["OllamaRuntime", "OllamaUnavailable", "DEFAULT_NUM_CTX"]
