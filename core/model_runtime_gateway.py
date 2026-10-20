"""Fridays-owned local model runtime gateway.

This is the first slice of the local model control layer that sits above
Ollama. It gives Fridays a place to reason about model health, token heartbeat,
idle-vs-absolute clocks, and model output normalization before callers consume
the result.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import requests


def _resolve_ollama_host() -> str:
    env = os.environ.get('OLLAMA_HOST', '').strip()
    if env:
        return env if env.startswith('http') else f'http://{env}'

    try:
        release = open('/proc/sys/kernel/osrelease', 'r', encoding='utf-8').read().lower()
        if 'microsoft' in release or 'wsl' in release:
            resolv = open('/etc/resolv.conf', 'r', encoding='utf-8').read()
            match = re.search(r'^nameserver\s+([\d.]+)', resolv, re.MULTILINE)
            if match:
                return f'http://{match.group(1)}:11434'
    except OSError:
        pass

    return 'http://127.0.0.1:11434'


OLLAMA_BASE_URL = _resolve_ollama_host()
DEFAULT_IDLE_TIMEOUT_S = 900
DEFAULT_ABSOLUTE_TIMEOUT_S = 2000
FALLBACK_GENERATE_TIMEOUT_S = 60
_LAST_OLLAMA_STATUS: str | None = None


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
            snap = {
                "ok": False,
                "status": "down",
                "models": [],
                "warnings": [f"ollama unreachable: {exc}"],
                "error_code": "RUNTIME_OFFLINE",
            }
            _emit_ollama_runtime_state(snap)
            return snap

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
    snap = {
        "ok": True,
        "status": status,
        "models": models,
        "warnings": warnings,
        "error_code": "" if status != "down" else "RUNTIME_OFFLINE",
    }
    _emit_ollama_runtime_state(snap)
    return snap


def _emit_ollama_runtime_state(snap: dict[str, Any]) -> None:
    global _LAST_OLLAMA_STATUS
    status = str(snap.get("status") or "")
    if not status or status == _LAST_OLLAMA_STATUS:
        return
    _LAST_OLLAMA_STATUS = status
    payload = {
        "kind": "ollama_runtime",
        "status": status,
        "ok": bool(snap.get("ok")),
        "error_code": str(snap.get("error_code") or ""),
        "warnings": list(snap.get("warnings") or []),
        "models": [
            {
                "name": entry.get("name"),
                "state": entry.get("state"),
            }
            for entry in (snap.get("models") or [])
        ],
    }
    try:
        from utils.swarm_bus import publish as bus_publish
        bus_publish("runtime.ollama", payload, source_service="model_runtime_gateway")
    except Exception:
        pass
    try:
        from core import spine
        severity = spine.Severity.WARN if status in {"down", "degraded"} else spine.Severity.INFO
        spine.log(
            spine.EventKind.SYSTEM,
            f"ollama runtime {status}",
            severity=severity,
            source="model_runtime_gateway",
            payload=payload,
        )
    except Exception:
        pass


def force_unload(
    model: str,
    *,
    base_url: str = OLLAMA_BASE_URL,
    poll_seconds: int = 10,
    poll_interval_s: float = 1.0,
    restart_cmds: list[list[str]] | None = None,
    subprocess_runner: Any = None,
) -> dict[str, Any]:
    """Force a stuck Ollama runner to release a model.

    Strategy (matches the failure mode logged in PACKET-05):
      1. POST keep_alive=0 to nudge a clean unload.
      2. Poll /api/ps; if the model disappears (or no longer reports
         "stopping"), declare success.
      3. If still stuck, escalate by attempting a service restart through the
         provided commands (best-effort, no sudo prompt). Re-poll once.

    Returns a structured snapshot so the UI can show what happened and what
    next step the operator should take.
    """
    model = (model or "").strip()
    if not model:
        return {
            "ok": False,
            "model": "",
            "stuck": False,
            "action": "noop",
            "attempted": [],
            "message": "model name required",
        }

    attempted: list[dict[str, Any]] = []

    # Step 1: polite unload
    try:
        requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": " ", "keep_alive": 0},
            timeout=15,
        )
        attempted.append({"step": "unload", "ok": True})
    except Exception as exc:
        attempted.append({"step": "unload", "ok": False, "error": str(exc)})

    def _is_stuck() -> bool:
        snap = ollama_health(base_url=base_url)
        for entry in snap.get("models") or []:
            if entry.get("name") == model and entry.get("state") == "stopping":
                return True
        return False

    def _still_loaded() -> bool:
        snap = ollama_health(base_url=base_url)
        return any(entry.get("name") == model for entry in (snap.get("models") or []))

    # Step 2: poll for unload completion
    waited = 0.0
    stuck = False
    while waited < poll_seconds:
        if not _still_loaded():
            return {
                "ok": True,
                "model": model,
                "stuck": False,
                "action": "unloaded",
                "attempted": attempted,
                "message": f"{model} unloaded cleanly",
            }
        if _is_stuck():
            stuck = True
            break
        time.sleep(poll_interval_s)
        waited += poll_interval_s

    if not stuck and _still_loaded() and _is_stuck():
        stuck = True

    if not stuck:
        return {
            "ok": True,
            "model": model,
            "stuck": False,
            "action": "pending",
            "attempted": attempted,
            "message": f"{model} unload accepted; runner still draining",
        }

    # Step 3: escalate via restart command(s)
    runner = subprocess_runner
    if runner is None:
        import subprocess as _subprocess

        def runner(cmd: list[str]) -> tuple[int, str]:
            try:
                proc = _subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                return proc.returncode, (proc.stderr or proc.stdout or "").strip()
            except Exception as exc:
                return 1, str(exc)

    cmds = restart_cmds or [
        ["systemctl", "--user", "--no-ask-password", "restart", "ollama"],
        ["systemctl", "--no-ask-password", "restart", "ollama"],
    ]
    restart_ok = False
    for cmd in cmds:
        try:
            code, out = runner(cmd)
        except Exception as exc:  # pragma: no cover - defensive
            code, out = 1, str(exc)
        attempted.append({"step": "restart", "cmd": " ".join(cmd), "code": code, "detail": out[:200]})
        if code == 0:
            restart_ok = True
            break

    if restart_ok:
        # Give the daemon a beat to come back
        time.sleep(min(2.0, poll_interval_s * 2))
        return {
            "ok": True,
            "model": model,
            "stuck": True,
            "action": "restarted",
            "attempted": attempted,
            "message": f"{model} runner restarted via systemctl",
        }

    return {
        "ok": False,
        "model": model,
        "stuck": True,
        "action": "needs_operator",
        "attempted": attempted,
        "message": (
            f"{model} runner is stuck in 'Stopping' and could not be restarted "
            "without elevated permissions. Run: sudo systemctl restart ollama"
        ),
    }


def chat(
    model: str,
    messages: list[dict[str, str]],
    *,
    base_url: str = OLLAMA_BASE_URL,
    # Persistent chat jobs can legitimately spend several minutes in local
    # inference. Keep the transport clocks aligned with the chat watchdog
    # policy so the gateway does not fail first with a stale 240s idle cap.
    absolute_timeout_s: int = DEFAULT_ABSOLUTE_TIMEOUT_S,
    idle_timeout_s: int = DEFAULT_IDLE_TIMEOUT_S,
    keep_alive: str | int = "60s",
    options: dict[str, Any] | None = None,
    on_token: Any = None,
    on_event: Any = None,
    prefer_generate: bool = False,
    response_format: str | dict[str, Any] | None = None,
) -> RuntimeResult:
    """Run a local chat with structured events and idle/absolute clocks.

    Optional callbacks let callers stream the work into their own trace:
      * on_token(piece: str): fired for every non-empty token chunk
      * on_event(event_dict): fired for every RuntimeEvent appended (queued,
        dispatch, first_token, token_heartbeat, completed, failed)
    Both callbacks are best-effort — exceptions are swallowed so a noisy
    consumer cannot break model output.
    """
    if _seven_runtime_enabled() or _is_registered_direct_model(model):
        direct = _direct_chat_if_registered(
            model,
            messages,
            absolute_timeout_s=absolute_timeout_s,
            idle_timeout_s=idle_timeout_s,
            options=options,
            on_token=on_token,
            on_event=on_event,
            response_format=response_format,
        )
        if direct is not None:
            return direct

    started = _now()
    events: list[RuntimeEvent] = []

    def _fallback_generate() -> RuntimeResult:
        """Fallback path for runtimes where /api/chat fails but /api/generate still works."""
        system_prompt = ""
        user_turns: list[str] = []
        for msg in messages or []:
            role = str((msg or {}).get("role") or "").strip().lower()
            content = str((msg or {}).get("content") or "").strip()
            if not content:
                continue
            if role == "system" and not system_prompt:
                system_prompt = content
            elif role == "user":
                user_turns.append(content)

        prompt = user_turns[-1] if user_turns else str((messages or [{}])[-1].get("content") or "")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "options": options or {},
        }
        if response_format is not None:
            payload["format"] = response_format
        if system_prompt:
            payload["system"] = system_prompt

        fallback_timeout_s = max(1, min(int(idle_timeout_s), FALLBACK_GENERATE_TIMEOUT_S))
        resp = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=(10, fallback_timeout_s),
        )
        resp.raise_for_status()
        data = resp.json() or {}
        answer = str(data.get("response") or "")
        tok = int(data.get("eval_count") or 0)
        _record(RuntimeEvent("fallback_generate", _now(), "chat->generate fallback", tokens=tok))
        if answer:
            _record(RuntimeEvent("completed", _now(), tokens=tok or len(answer.split())))
            return RuntimeResult(True, model, answer, tok, _now() - started, events=events)
        raise RuntimeError("generate fallback returned empty response")

    def _record(event: RuntimeEvent) -> None:
        events.append(event)
        if on_event is not None:
            try:
                on_event(event.as_dict())
            except Exception:
                pass

    _record(RuntimeEvent("queued", started))
    if prefer_generate:
        _record(RuntimeEvent("fallback", _now(), "generate preferred"))
        try:
            return _fallback_generate()
        except Exception as exc:
            _record(RuntimeEvent("failed", _now(), f"generate preferred failed: {exc}"))
            return RuntimeResult(False, model, "", 0, _now() - started, error=str(exc), events=events)

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    tokens = 0
    try:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": options or {},
        }
        if response_format is not None:
            payload["format"] = response_format
        # gpt-oss thinks in a separate harmony channel; tokens land in
        # message.thinking instead of message.content, which this loop does
        # not read — an all-thinking turn returns an empty answer and the
        # chat layer reports "[agent unavailable]". Worker turns need visible
        # content (SKILL lines), so request think:false. SWARM_LLM_THINK=1
        # re-enables the reasoning channel.
        if model.startswith("gpt-oss") and os.environ.get("SWARM_LLM_THINK", "0") != "1":
            payload["think"] = False
        events.append(RuntimeEvent("dispatch", _now(), f"absolute={absolute_timeout_s}s idle={idle_timeout_s}s"))
        if on_event is not None:
            try:
                on_event(events[-1].as_dict())
            except Exception:
                pass
        # CPU councils can spend more than 45s before the first token while
        # Llama and Qwen are both active. Respect the caller's idle clock,
        # capped at two minutes, so healthy strict-JSON chats are not converted
        # into a less reliable /api/generate fallback.
        chat_read_timeout_s = max(20, min(int(idle_timeout_s), 120))
        with requests.post(
            f"{base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=(10, chat_read_timeout_s),
        ) as resp:
            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                detail = ''
                try:
                    payload = resp.json() or {}
                    detail = str(payload.get('error') or payload.get('message') or '').strip()
                except Exception:
                    detail = (resp.text or '').strip()[:300]
                lowered = detail.lower()
                if 'memory layout cannot be allocated' in lowered:
                    _record(RuntimeEvent('fallback', _now(), 'chat endpoint allocation failed; trying generate'))
                    try:
                        return _fallback_generate()
                    except Exception as fallback_exc:
                        raise requests.HTTPError(f'{exc} — {detail}; generate fallback failed: {fallback_exc}') from exc
                if detail:
                    raise requests.HTTPError(f'{exc} — {detail}') from exc
                raise
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
                think_piece = ((data.get("message") or {}).get("thinking") or "")
                if think_piece:
                    # Reasoning-channel tokens: not the answer, but they prove
                    # the runner is alive, so they still reset the idle clock.
                    thinking_parts.append(think_piece)
                    last_token_at = _now()
                if piece:
                    content_parts.append(piece)
                    last_token_at = _now()
                    tokens += 1
                    if on_token is not None:
                        try:
                            on_token(piece)
                        except Exception:
                            pass
                    if tokens == 1:
                        _record(RuntimeEvent("first_token", last_token_at, tokens=tokens))
                    elif tokens % 25 == 0:
                        _record(RuntimeEvent("token_heartbeat", last_token_at, tokens=tokens))
                if data.get("done"):
                    tokens = int(data.get("eval_count") or tokens)
                    _record(RuntimeEvent("completed", _now(), tokens=tokens))
                    break
        content = "".join(content_parts)
        if not content.strip() and thinking_parts:
            # gpt-oss sometimes puts the whole turn (SKILL lines included) in
            # the thinking channel and leaves content empty — an empty answer
            # here surfaces as "[agent unavailable]" upstream. Fall back to
            # the thinking channel so the skills loop can still parse it.
            _record(RuntimeEvent("thinking_only", _now(), "empty content; falling back to thinking channel"))
            content = "".join(thinking_parts)
        return RuntimeResult(True, model, content, tokens, _now() - started, events=events)
    except requests.ReadTimeout as exc:
        _record(RuntimeEvent("fallback", _now(), f"chat read-timeout ({exc}); trying generate"))
        try:
            return _fallback_generate()
        except Exception as fallback_exc:
            _record(RuntimeEvent("failed", _now(), f"chat timeout + generate fallback failed: {fallback_exc}", tokens=tokens))
            return RuntimeResult(False, model, "".join(content_parts), tokens, _now() - started, error=str(fallback_exc), events=events)
    except Exception as exc:
        _record(RuntimeEvent("failed", _now(), str(exc), tokens=tokens))
        return RuntimeResult(False, model, "".join(content_parts), tokens, _now() - started, error=str(exc), events=events)


def _seven_runtime_enabled() -> bool:
    value = os.environ.get("SEVEN_RUNTIME", "").strip().lower()
    return value in {"1", "true", "yes", "direct", "llamacpp"}


def _is_registered_direct_model(model: str) -> bool:
    try:
        from core.seven_llm import registry
        entry = registry.get(model)
        return bool(entry and entry.driver == "llamacpp")
    except Exception:
        return False


def _direct_chat_if_registered(
    model: str,
    messages: list[dict[str, str]],
    *,
    absolute_timeout_s: int,
    idle_timeout_s: int,
    options: dict[str, Any] | None,
    on_token: Any = None,
    on_event: Any = None,
    response_format: str | dict[str, Any] | None = None,
) -> RuntimeResult | None:
    try:
        from core.seven_llm import registry
        entry = registry.get(model)
    except Exception:
        entry = None
    if not entry or entry.driver != "llamacpp":
        return None

    started = _now()
    events: list[RuntimeEvent] = []

    def _record(stage: str, detail: str = "", tokens: int = 0) -> None:
        event = RuntimeEvent(stage, _now(), detail, tokens=tokens)
        events.append(event)
        if on_event is not None:
            try:
                on_event(event.as_dict())
            except Exception:
                pass

    _record("queued")
    _record("direct_dispatch", f"driver=llamacpp absolute={absolute_timeout_s}s idle={idle_timeout_s}s")
    try:
        from core.seven_llm.driver_llamacpp import LlamaCppDriver
        driver = LlamaCppDriver(options={"timeout": absolute_timeout_s})
        merged_options = dict(options or {})
        merged_options.setdefault("timeout", absolute_timeout_s)
        if response_format is not None:
            merged_options["response_format"] = response_format
        saw_token = False

        def _on_direct_token(piece: str) -> None:
            nonlocal saw_token
            if piece and not saw_token:
                saw_token = True
                _record("first_token", tokens=1)
            if on_token is not None:
                try:
                    on_token(piece)
                except Exception:
                    pass

        text, tokens = driver.chat(
            model,
            messages,
            temperature=merged_options.pop("temperature", None),
            options=merged_options,
            on_token=_on_direct_token if on_token is not None else None,
        )
        if text and not saw_token:
            _record("first_token", tokens=max(1, tokens))
        _record("completed", tokens=tokens)
        return RuntimeResult(True, model, text, tokens, _now() - started, events=events)
    except Exception as exc:
        _record("failed", str(exc))
        return RuntimeResult(False, model, "", 0, _now() - started, error=str(exc), events=events)
