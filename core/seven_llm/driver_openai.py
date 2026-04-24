"""core/llm/driver_openai.py — OpenAI / Azure OpenAI / any OpenAI-compatible
HTTP driver.

Endpoint + API key are taken from the registry entry options, or the env vars
``OPENAI_API_KEY`` / ``OPENAI_BASE_URL``. No SDK required — pure HTTP.
"""
from __future__ import annotations

import os
from typing import Any, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

from .driver_base import Driver


class OpenAIDriver(Driver):
    name = "openai"

    def __init__(self, endpoint: Optional[str] = None, options: Optional[dict] = None):
        endpoint = endpoint or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        super().__init__(endpoint=endpoint, options=options)
        self.api_key = (options or {}).get("api_key") or os.environ.get("OPENAI_API_KEY")

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def chat(self, model, messages, *, stream=False, temperature=None,
             options=None, keep_alive=None):
        if requests is None:
            raise RuntimeError("requests not available")
        body: dict = {"model": model, "messages": messages, "stream": False}
        if temperature is not None:
            body["temperature"] = float(temperature)
        r = requests.post(self.endpoint.rstrip("/") + "/chat/completions",
                          json=body, headers=self._headers(), timeout=120)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        tokens = int(data.get("usage", {}).get("total_tokens", 0))
        return text, tokens

    def ps(self):
        return []

    def list_models(self):
        if requests is None or not self.api_key:
            return []
        try:
            r = requests.get(self.endpoint.rstrip("/") + "/models",
                             headers=self._headers(), timeout=10)
            r.raise_for_status()
            return [{"name": m.get("id")} for m in r.json().get("data", [])]
        except Exception:
            return []
