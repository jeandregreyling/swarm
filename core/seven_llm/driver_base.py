"""core/llm/driver_base.py — Driver ABC.

Every backend (Ollama, llama.cpp, LM Studio, OpenAI-compatible HTTP) subclasses
:class:`Driver` and implements three methods. The registry + pool call these.
"""
from __future__ import annotations

import abc
from typing import Any, Iterable, Optional


class Driver(abc.ABC):
    """Abstract backend driver."""

    name: str = "base"

    def __init__(self, endpoint: Optional[str] = None, options: Optional[dict] = None):
        self.endpoint = endpoint
        self.options = dict(options or {})

    @abc.abstractmethod
    def chat(self, model: str, messages: list[dict], *, stream: bool = False,
             temperature: Optional[float] = None, options: Optional[dict] = None,
             keep_alive: Any = None) -> tuple[str, int]:
        """Run a chat completion. Returns (text, tokens)."""

    @abc.abstractmethod
    def ps(self) -> list[dict]:
        """Report running models with age / ram usage if available."""

    @abc.abstractmethod
    def list_models(self) -> list[dict]:
        """Report models this driver knows how to serve."""

    # Optional — default is a no-op
    def unload(self, model: str) -> bool:  # pragma: no cover - override
        return False
