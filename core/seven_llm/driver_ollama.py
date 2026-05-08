"""core/llm/driver_ollama.py — Ollama driver (feature-flagged SCOUT peer).

Thin wrapper around the existing core.llm module so Ollama can coexist as just
one peer driver inside the new registry-driven runtime. The legacy module
remains the production path until SEVEN_RUNTIME=1 flips routing.
"""
from __future__ import annotations

from typing import Any, Optional

from .driver_base import Driver


class OllamaDriver(Driver):
    name = "ollama"

    def chat(self, model, messages, *, stream=False, temperature=None,
             options=None, keep_alive=None):
        from core import llm as legacy  # lazy import — legacy module is heavy
        return legacy.chat(
            model, messages,
            stream=stream, temperature=temperature,
            options=options, keep_alive=keep_alive,
        )

    def ps(self):
        from core import llm as legacy
        try:
            return legacy.ps()
        except Exception:
            return []

    def list_models(self):
        from core import llm as legacy
        try:
            return legacy.list_models()
        except Exception:
            return []
