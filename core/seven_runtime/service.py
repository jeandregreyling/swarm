"""Standalone Seven runtime service.

The service deliberately uses Python's stdlib HTTP server. It is not a Flask
blueprint and it does not call Ollama unless the operator explicitly overrides
Seven's model to an Ollama model.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from multiprocessing import get_context
from typing import Any


DEFAULT_HOST = os.environ.get("SEVEN_RUNTIME_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("SEVEN_RUNTIME_PORT", "17777"))
DEFAULT_CHAT_TIMEOUT_S = int(os.environ.get("SEVEN_RUNTIME_CHAT_TIMEOUT_S", "90"))
SERVICE_NAME = "seven-runtime"


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def health_snapshot() -> dict[str, Any]:
    """Return current service/runtime facts without starting model inference."""
    snap: dict[str, Any] = {
        "ok": True,
        "service": SERVICE_NAME,
        "pid": os.getpid(),
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "flask_required": False,
        "ollama_required": False,
        "model": os.environ.get("SEVEN_MODEL", "seven-direct:daily"),
        "chat_timeout_s": DEFAULT_CHAT_TIMEOUT_S,
        "time": time.time(),
        "direct": {},
    }
    try:
        from core.seven_runtime.model_operator import SPEAKER_LOCK
        from core.seven_llm import registry
        from core.seven_llm import llama_server

        model = str(snap["model"])
        entry = registry.get(model)
        direct_models = [
            {
                "name": item.name,
                "role": item.role,
                "path": item.path,
                "exists": bool(item.path and os.path.isfile(item.path)),
                "ram_gb": item.ram_gb,
            }
            for item in registry.list_models()
            if item.driver == "llamacpp"
        ]
        snap["direct"] = {
            "registered": bool(entry and entry.driver == "llamacpp"),
            "models": direct_models,
            "resources": llama_server.resource_snapshot(),
            "speaker_active": SPEAKER_LOCK.locked(),
        }
        if not snap["direct"]["registered"]:
            snap["ok"] = False
            snap["warning"] = f"Seven model is not a registered direct GGUF model: {model}"
    except Exception as exc:
        snap["ok"] = False
        snap["warning"] = f"direct runtime snapshot failed: {type(exc).__name__}: {exc}"
    return snap


def _chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or payload.get("prompt") or "").strip()
    history = payload.get("history") or payload.get("messages") or []
    if not message and isinstance(history, list):
        for row in reversed(history):
            if isinstance(row, dict) and str(row.get("role") or "").lower() == "user":
                message = str(row.get("content") or "").strip()
                break
    if not message:
        return {"ok": False, "error": "message required", "content": "", "tokens": 0}

    from agents.seven import seven_agent

    stages: list[str] = []

    def _stage(text: str, _eta: Any = None) -> None:
        if text:
            stages.append(str(text))

    answer, tokens = seven_agent.chat(
        message,
        conversation_history=history if isinstance(history, list) else [],
        stage_cb=_stage,
        conversation_id=payload.get("conversation_id"),
    )
    return {
        "ok": bool(answer),
        "content": str(answer or ""),
        "tokens": int(tokens or 0),
        "stages": stages,
        "model": seven_agent.SEVEN_MODEL,
    }


def _chat_worker(payload: dict[str, Any], queue: Any) -> None:
    model = os.environ.get("SEVEN_MODEL", "seven-direct:daily")
    try:
        queue.put(_chat(payload))
    except Exception as exc:
        queue.put({
            "ok": False,
            "content": "",
            "tokens": 0,
            "error": f"seven chat failed: {type(exc).__name__}: {exc}",
        })
    finally:
        _cleanup_direct_model_process(model)


def _cleanup_direct_model_process(model: str) -> None:
    try:
        from core.seven_llm import llama_server
        llama_server.stop(model)
    except Exception:
        pass
    try:
        from core.seven_llm import registry
        entry = registry.get(model)
        marker = os.path.basename(str(entry.path or "")) if entry and entry.path else ""
        if marker:
            subprocess.run(
                ["pkill", "-f", f"llama-server.*{marker}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
    except Exception:
        pass


def guarded_chat(payload: dict[str, Any], *, timeout_s: int = DEFAULT_CHAT_TIMEOUT_S) -> dict[str, Any]:
    """Run Seven chat with a service-level timeout so callers never hang."""
    started = time.time()
    timeout = max(1, int(payload.get("timeout_seconds") or timeout_s or DEFAULT_CHAT_TIMEOUT_S))
    from core.seven_runtime.model_operator import SPEAKER_LOCK
    acquired = SPEAKER_LOCK.acquire(timeout=timeout)
    if not acquired:
        return {
            "ok": False,
            "content": "",
            "tokens": 0,
            "error": "another local speaker is active",
            "elapsed_s": round(time.time() - started, 3),
        }
    ctx = get_context("spawn")
    queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_chat_worker, args=(payload, queue), name="seven-runtime-chat")
    try:
        proc.start()
        proc.join(timeout)
        if proc.is_alive():
            proc.terminate()
            proc.join(3)
            if proc.is_alive():
                proc.kill()
                proc.join(3)
            _cleanup_direct_model_process(os.environ.get("SEVEN_MODEL", "seven-direct:daily"))
            return {
                "ok": False,
                "content": "",
                "tokens": 0,
                "error": f"seven runtime chat timeout after {timeout}s",
                "elapsed_s": round(time.time() - started, 3),
            }
        if not queue.empty():
            out = queue.get()
        elif proc.exitcode not in (0, None):
            out = {
                "ok": False,
                "content": "",
                "tokens": 0,
                "error": f"seven runtime chat exited {proc.exitcode}",
            }
        else:
            out = {"ok": False, "content": "", "tokens": 0, "error": "seven runtime chat returned no result"}
        out["elapsed_s"] = round(time.time() - started, 3)
        return out
    finally:
        SPEAKER_LOCK.release()


class SevenRuntimeHandler(BaseHTTPRequestHandler):
    server_version = "SevenRuntime/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("SEVEN_RUNTIME_LOG", "").strip():
            super().log_message(fmt, *args)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(_jsonable(payload), ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:
        if self.path in {"/health", "/snapshot", "/"}:
            self._send(200, health_snapshot())
            return
        if self.path == "/v1/models":
            snap = health_snapshot()
            models = [{"id": item.get("name"), "object": "model"} for item in (snap.get("direct") or {}).get("models") or []]
            self._send(200, {"object": "list", "data": models})
            return
        if self.path == "/api/tags":
            from core.seven_runtime import model_operator
            self._send(200, model_operator.inventory())
            return
        if self.path == "/api/ps":
            from core.seven_runtime import model_operator
            snap = model_operator.inventory()
            self._send(200, {"ok": snap.get("ok"), "models": snap.get("resident") or [], "warnings": snap.get("warnings") or []})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/chat":
            self._send(200, guarded_chat(self._read_json()))
            return
        if self.path in {"/api/chat", "/api/generate"}:
            from core.seven_runtime import model_operator
            payload = self._read_json()
            prompt = str(payload.get("prompt") or "").strip()
            if not prompt:
                messages = payload.get("messages") or []
                for row in reversed(messages if isinstance(messages, list) else []):
                    if isinstance(row, dict) and str(row.get("role") or "").lower() == "user":
                        prompt = str(row.get("content") or "").strip()
                        break
            result = model_operator.run(
                payload.get("model"),
                prompt,
                timeout_seconds=payload.get("timeout_seconds") or 120,
                keep_alive=payload.get("keep_alive", "60s"),
            )
            self._send(200 if result.get("ok") else 400, result)
            return
        if self.path == "/api/stop":
            from core.seven_runtime import model_operator
            result = model_operator.stop(self._read_json().get("model"))
            self._send(200 if result.get("ok") else 400, result)
            return
        if self.path == "/api/roll-call":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.roll_call(
                payload.get("model"),
                timeout_seconds=payload.get("timeout_seconds") or 120,
            )
            self._send(200, result)
            return
        if self.path == "/api/peer-turn":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.peer_turn(
                payload.get("peer"),
                payload.get("question") or payload.get("prompt"),
                conversation_id=payload.get("conversation_id"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 180,
            )
            self._send(200 if result.get("ok") else 400, result)
            return
        if self.path == "/api/constrained-peer-turn":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.constrained_peer_turn(
                payload.get("peer"),
                payload.get("question") or payload.get("prompt"),
                contract_name=str(payload.get("contract_name") or ""),
                conversation_id=payload.get("conversation_id"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 180,
            )
            self._send(200 if result.get("ok") or result.get("fallback_used") else 400, result)
            return
        if self.path == "/api/consult":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.consult(
                payload.get("question") or payload.get("prompt"),
                conversation_id=payload.get("conversation_id"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 180,
            )
            self._send(200 if result.get("ok") else 400, result)
            return
        if self.path == "/api/routed-acceptance-review":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.routed_acceptance_review(
                payload.get("peer"),
                project_id=str(payload.get("project_id") or ""),
                rounds=payload.get("rounds") or 2,
                timeout_seconds=payload.get("timeout_seconds") or 180,
            )
            self._send(200, result)
            return
        if self.path == "/api/instruction-drill":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.instruction_drill(
                payload.get("peer"),
                project_id=str(payload.get("project_id") or ""),
                rounds=payload.get("rounds") or 1,
                timeout_seconds=payload.get("timeout_seconds") or 120,
            )
            self._send(200, result)
            return
        if self.path == "/api/grounded-transfer-lesson":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.grounded_transfer_lesson(
                payload.get("peer"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 120,
            )
            self._send(200, result)
            return
        if self.path == "/api/bounded-repair-lesson":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.bounded_repair_lesson(
                payload.get("peer"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 120,
            )
            self._send(200, result)
            return
        if self.path == "/api/schema-constrained-lesson":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.schema_constrained_lesson(
                payload.get("peer"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 120,
            )
            self._send(200, result)
            return
        if self.path == "/api/schema-robustness-lesson":
            from core.seven_runtime import model_operator
            payload = self._read_json()
            result = model_operator.schema_robustness_lesson(
                payload.get("peer"),
                project_id=str(payload.get("project_id") or ""),
                timeout_seconds=payload.get("timeout_seconds") or 120,
            )
            self._send(200, result)
            return
        self._send(404, {"ok": False, "error": "not found"})


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, int(port)), SevenRuntimeHandler)


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    httpd = make_server(host, port)
    print(f"{SERVICE_NAME} listening on http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the standalone Seven runtime service.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
