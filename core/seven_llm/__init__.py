"""core.seven_llm — Seven Runtime model orchestration layer.

Successor to the monolithic ``core/llm.py`` gateway. Provides Swarm's own
model catalogue (:mod:`core.seven_llm.registry`), warm-pool
(:mod:`core.seven_llm.pool`), and pluggable drivers so Ollama becomes just
one peer alongside llama.cpp in-process, LM Studio, and any
OpenAI-compatible HTTP endpoint.

Feature-flagged via ``SEVEN_RUNTIME`` env var. When unset, callers continue
to use ``core.llm`` (legacy module) unchanged. When set, routing flows
through registry + pool + drivers here.

Public surface::

    from core.seven_llm import registry, pool
    from core.seven_llm.driver_base import Driver
"""
from __future__ import annotations

__all__ = ["registry", "pool", "driver_base"]
