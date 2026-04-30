"""Fridays-owned local model runtime gateway.

This is the first slice of the local model control layer that sits above
Ollama. It gives Fridays a place to reason about model health, token heartbeat,
idle-vs-absolute clocks, and model output normalization before callers consume
the result.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import requests


OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass
class RuntimeEvent:
    stage: str
    at: float
    detail: str = ""
    tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "at": self.at,
            "detail": self.detail,
            "tokens": self.tokens,
        }


@dataclass
class RuntimeResult:
    ok: bool
    model: str
    content: str = ""
    tokens: int = 0
    elapsed_s: float = 0.0
    error: str = ""
    events: list[RuntimeEvent] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "content": self.content,
            "tokens": self.tokens,
            "elapsed_s": self.elapsed_s,
            "error": self.error,
            "events": [event.as_dict() for event in self.events],
        }


def _now() -> float:
    return time.time()


def normalize_model_json(text: str) -> dict[str, Any]:
    """Parse useful JSON out of model text.

    Local models often wrap JSON in markdown fences, return a one-item list
    instead of an object, or hit the token cap mid-structure. This helper keeps
    downstream media/task code from failing on harmless formatting noise while
    still flagging truncation.
    """
    raw = str(text or "").strip()
    cleaned = raw
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    parsed = None
    error = ""
    truncated = _looks_unbalanced_json(cleaned)
    for candidate in _json_candidates(cleaned):
        try:
            parsed = json.loads(candidate)
            break
        except Exception as exc:
            error = str(exc)

    if isinstance(parsed, list):
        parsed_value = parsed[0] if parsed else {}
        shape = "list"
    elif isinstance(parsed, dict):
        parsed_value = parsed
        shape = "object"
    else:
        parsed_value = {}
        shape = "text"

    return {
        "ok": bool(parsed_value),
        "value": parsed_value,
        "shape": shape,
        "raw": raw,
        "cleaned": cleaned,
        "truncated": truncated,
        "error": "" if parsed_value else error,
    }


def _json_candidates(text: str) -> Iterable[str]:
    cleaned = str(text or "").strip()
    if cleaned:
        yield cleaned
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start >= 0 and end > start:
            yield cleaned[start:end + 1]


def _looks_unbalanced_json(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if stripped.startswith("{") and not stripped.endswith("}"):
        return True
    if stripped.startswith("[") and not stripped.endswith("]"):
        return True
    return stripped.count("{") != stripped.count("}") or stripped.count("[") != stripped.count("]")


def ollama_health(base_url: str = OLLAMA_BASE_URL, *, ps_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a health snapshot for loaded Ollama models."""
    if ps_payload is None:
        try:
            resp = requests.get(f"{base_url}/api/ps", timeout=5)
            resp.raise_for_status()
            ps_payload = resp.json()
        except Exception as exc:
            return {
                "ok": False,
                "status": "down",
                "models": [],
                "warnings": [f"ollama unreachable: {exc}"],
            }

    models = []
    warnings = []
    for item in ps_payload.get("models") or []:
        name = str(item.get("model") or item.get("name") or "").strip()
        until = str(item.get("expires_at") or item.get("until") or "").strip()
        state = "loaded"
        text = json.dumps(item, default=str).lower()
        if "stopping" in text:
            state = "stopping"
            warnings.append(f"{name or 'model'} is stuck/stopping")
        elif "loading" in text:
            state = "loading"
        models.append({
            "name": name,
            "state": state,
            "expires_at": until,
            "size": item.get("size"),
            "raw": item,
        })

    status = "healthy"
    if any(model["state"] == "stopping" for model in models):
        status = "degraded"
    return {
        "ok": True,
        "status": status,
        "models": models,
        "warnings": warnings,
    }


def chat(
    model: str,
    messages: list[dict[str, str]],
    *,
    base_url: str = OLLAMA_BASE_URL,
    absolute_timeout_s: int = 300,
    idle_timeout_s: int = 60,
    keep_alive: str | int = "60s",
    options: dict[str, Any] | None = None,
) -> RuntimeResult:
    """Run an Ollama chat with structured events and idle/absolute clocks."""
    started = _now()
    events = [RuntimeEvent("queued", started)]
    content_parts: list[str] = []
    tokens = 0
    try:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": options or {},
        }
        events.append(RuntimeEvent("dispatch", _now(), f"absolute={absolute_timeout_s}s idle={idle_timeout_s}s"))
        with requests.post(
            f"{base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=(10, max(1, int(idle_timeout_s))),
        ) as resp:
            resp.raise_for_status()
            last_token_at = _now()
            for line in resp.iter_lines(decode_unicode=True):
                elapsed = _now() - started
                if elapsed > absolute_timeout_s:
                    raise TimeoutError(f"absolute timeout after {int(elapsed)}s")
                if not line:
                    if _now() - last_token_at > idle_timeout_s:
                        raise TimeoutError(f"idle timeout after {int(_now() - last_token_at)}s")
                    continue
                data = json.loads(line)
                piece = ((data.get("message") or {}).get("content") or "")
                if piece:
                    content_parts.append(piece)
                    last_token_at = _now()
                    tokens += 1
                    if tokens == 1:
                        events.append(RuntimeEvent("first_token", last_token_at, tokens=tokens))
                    elif tokens % 25 == 0:
                        events.append(RuntimeEvent("token_heartbeat", last_token_at, tokens=tokens))
                if data.get("done"):
                    tokens = int(data.get("eval_count") or tokens)
                    events.append(RuntimeEvent("completed", _now(), tokens=tokens))
                    break
        return RuntimeResult(True, model, "".join(content_parts), tokens, _now() - started, events=events)
    except Exception as exc:
        events.append(RuntimeEvent("failed", _now(), str(exc), tokens=tokens))
        return RuntimeResult(False, model, "".join(content_parts), tokens, _now() - started, error=str(exc), events=events)
