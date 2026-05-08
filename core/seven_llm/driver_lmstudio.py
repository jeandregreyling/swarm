"""core/llm/driver_lmstudio.py — LM Studio HTTP driver (OpenAI-compatible).

LM Studio ships an OpenAI-compatible REST server. This driver speaks it
directly without pulling in the openai SDK, so the Swarm can call any LM-Studio
instance as a peer model host.
"""
from __future__ import annotations

import json
from typing import Any, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from .driver_base import Driver

DEFAULT_ENDPOINT = "http://127.0.0.1:1234/v1"


class LMStudioDriver(Driver):
    name = "lmstudio"

    def __init__(self, endpoint: Optional[str] = None, options: Optional[dict] = None):
        super().__init__(endpoint=endpoint or DEFAULT_ENDPOINT, options=options)

    def _post(self, path: str, body: dict) -> dict:
        if requests is None:
            raise RuntimeError("requests not available")
        resp = requests.post(self.endpoint.rstrip("/") + path, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def chat(self, model, messages, *, stream=False, temperature=None,
             options=None, keep_alive=None):
        body: dict = {"model": model, "messages": messages, "stream": False}
        if temperature is not None:
            body["temperature"] = float(temperature)
        data = self._post("/chat/completions", body)
        text = data["choices"][0]["message"]["content"]
        tokens = int(data.get("usage", {}).get("total_tokens", 0))
        return text, tokens

    def ps(self):
        return []

    def list_models(self):
        if requests is None:
            return []
        try:
            r = requests.get(self.endpoint.rstrip("/") + "/models", timeout=5)
            r.raise_for_status()
            return [{"name": m.get("id")} for m in r.json().get("data", [])]
        except Exception:
            return []
