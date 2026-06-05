"""Warm llama.cpp server manager for Seven direct GGUF models."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from . import registry
from .prompt_profiles import default_stops


HOST = os.environ.get("SEVEN_LLAMA_SERVER_HOST", "127.0.0.1")
BASE_PORT = int(os.environ.get("SEVEN_LLAMA_SERVER_BASE_PORT", "18080"))
STARTUP_TIMEOUT_S = int(os.environ.get("SEVEN_LLAMA_SERVER_STARTUP_TIMEOUT", "180"))
RAM_RESERVE_GB = float(os.environ.get("SEVEN_LLAMA_RAM_RESERVE_GB", "3"))
SINGLE_RESIDENT = os.environ.get("SEVEN_LLAMA_SINGLE_RESIDENT", "1").strip().lower() not in {"0", "false", "no"}


@dataclass
class ServerHandle:
    model: str
    endpoint: str
    port: int
    pid: int
    started_at: float


_LOCK = threading.RLock()
_PROCS: dict[str, subprocess.Popen] = {}
_PORTS: dict[str, int] = {}


def _root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def default_binary() -> str:
    return os.environ.get("SEVEN_LLAMA_SERVER") or os.path.join(
        _root(), "agents", "seven", "llama.cpp", "build", "bin", "llama-server"
    )


def _preferred_port(model: str) -> int:
    digest = hashlib.sha1(model.encode("utf-8")).hexdigest()
    return BASE_PORT + (int(digest[:4], 16) % 1000)


def _port_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _port_for(model: str) -> int:
    existing = _PORTS.get(model)
    if existing:
        return existing
    start = _preferred_port(model)
    for offset in range(1000):
        port = BASE_PORT + ((start - BASE_PORT + offset) % 1000)
        if _port_free(port):
            _PORTS[model] = port
            return port
    raise RuntimeError("no free llama-server port in configured range")


def _server_alive(endpoint: str) -> bool:
    for path in ("/health", "/v1/models"):
        try:
            resp = requests.get(endpoint.rstrip("/") + path, timeout=2)
            if resp.status_code in (200, 401):
                return True
        except Exception:
            pass
    return False


def _meminfo_gb() -> dict[str, float]:
    values: dict[str, float] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                key, rest = line.split(":", 1)
                parts = rest.strip().split()
                if not parts:
                    continue
                values[key] = int(parts[0]) / 1024 / 1024
    except OSError:
        pass
    return {
        "total_gb": values.get("MemTotal", 0.0),
        "available_gb": values.get("MemAvailable", 0.0),
        "reserve_gb": RAM_RESERVE_GB,
        "single_resident": SINGLE_RESIDENT,
    }


def resource_snapshot() -> dict[str, Any]:
    snap = _meminfo_gb()
    snap["servers"] = snapshot()
    return snap


def _admit(model: str) -> None:
    entry = registry.get(model)
    if not entry:
        raise RuntimeError(f"no direct GGUF model registered for '{model}'")
    mem = _meminfo_gb()
    need = float(entry.ram_gb or 4.0)
    total = float(mem.get("total_gb") or 0.0)
    available = float(mem.get("available_gb") or 0.0)
    reserve = float(mem.get("reserve_gb") or 0.0)
    if total and need + reserve > total:
        raise RuntimeError(
            f"direct runtime resource guard blocked {model}: "
            f"requires {need:.1f}GB + {reserve:.1f}GB reserve, system total {total:.1f}GB"
        )
    if SINGLE_RESIDENT:
        for other, proc in list(_PROCS.items()):
            if other != model and proc.poll() is None:
                _stop_locked(other)
        mem = _meminfo_gb()
        available = float(mem.get("available_gb") or available)
    if available and need + reserve > available:
        raise RuntimeError(
            f"direct runtime resource guard blocked {model}: "
            f"requires {need:.1f}GB + {reserve:.1f}GB reserve, available {available:.1f}GB"
        )


def ensure(model: str, *, timeout_s: int = STARTUP_TIMEOUT_S) -> ServerHandle:
    entry = registry.get(model)
    if not entry or entry.driver != "llamacpp" or not entry.path:
        raise RuntimeError(f"no direct GGUF model registered for '{model}'")
    if not os.path.isfile(entry.path):
        raise RuntimeError(f"GGUF path missing for '{model}': {entry.path}")

    with _LOCK:
        proc = _PROCS.get(model)
        port = _port_for(model)
        endpoint = f"http://{HOST}:{port}"
        if proc is not None and proc.poll() is None and _server_alive(endpoint):
            return ServerHandle(model, endpoint, port, proc.pid, time.time())

        if proc is not None and proc.poll() is None:
            _stop_locked(model, timeout=5)

        _admit(model)

        binary = str((entry.options or {}).get("server") or default_binary())
        if not os.path.isfile(binary):
            raise RuntimeError(f"llama-server not found: {binary}")

        opts = dict(entry.options or {})
        ctx = int(opts.get("ctx") or entry.ctx or 2048)
        slots = int(opts.get("slots") or 1)
        cmd = [
            binary,
            "-m", str(entry.path),
            "--alias", model,
            "--host", HOST,
            "--port", str(port),
            "--ctx-size", str(ctx),
            "--parallel", str(slots),
            "--no-webui",
            "--no-slots",
            "--log-disable",
        ]
        if "threads" in opts:
            cmd.extend(["--threads", str(int(opts["threads"]))])
        if bool(opts.get("embedding")):
            cmd.append("--embedding")

        log_path = os.path.join("/tmp", f"seven-llama-server-{model.replace(':', '_')}.log")
        log_fh = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
            close_fds=True,
        )
        _PROCS[model] = proc

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited during startup for {model}; see {log_path}")
        if _server_alive(endpoint):
            return ServerHandle(model, endpoint, port, proc.pid, time.time())
        time.sleep(1)
    raise RuntimeError(f"llama-server startup timeout for {model}; see {log_path}")


def _chat_payload(model: str, messages: list[dict], *, temperature: float | None, options: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": int(options.get("num_predict") or options.get("max_tokens") or 256),
        "temperature": float(0.7 if temperature is None else temperature),
    }
    stops = options.get("stop") or default_stops(model, explicit=str(options.get("profile") or ""))
    if stops:
        payload["stop"] = [stops] if isinstance(stops, str) else list(stops)
    return payload


def chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    options: dict | None = None,
    on_token: Any = None,
) -> tuple[str, int]:
    opts = dict(options or {})
    handle = ensure(model, timeout_s=int(opts.get("startup_timeout") or STARTUP_TIMEOUT_S))
    payload = _chat_payload(model, messages, temperature=temperature, options=opts)
    if callable(on_token) or opts.get("stream"):
        return _chat_stream(handle, payload, timeout=int(opts.get("timeout") or 180), on_token=on_token)
    resp = requests.post(
        handle.endpoint.rstrip("/") + "/v1/chat/completions",
        json=payload,
        timeout=int(opts.get("timeout") or 180),
    )
    if resp.status_code >= 400:
        detail = (resp.text or "").strip()[:500]
        raise requests.HTTPError(
            f"{resp.status_code} Client Error for {resp.url}: {detail}",
            response=resp,
        )
    data = resp.json()
    text = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
    tokens = int((data.get("usage") or {}).get("completion_tokens") or len(text.split()) or 0)
    return text, tokens


def embeddings(model: str, prompt: str, *, options: dict | None = None) -> list[float]:
    opts = dict(options or {})
    handle = ensure(model, timeout_s=int(opts.get("startup_timeout") or STARTUP_TIMEOUT_S))
    resp = requests.post(
        handle.endpoint.rstrip("/") + "/v1/embeddings",
        json={"model": model, "input": str(prompt or "")},
        timeout=int(opts.get("timeout") or 120),
    )
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("data") if isinstance(data, dict) else None
    if isinstance(rows, list) and rows:
        embedding = (rows[0] or {}).get("embedding")
        if isinstance(embedding, list):
            return [float(x) for x in embedding]
    embedding = data.get("embedding") if isinstance(data, dict) else None
    if isinstance(embedding, list):
        return [float(x) for x in embedding]
    return []


def _chat_stream(handle: ServerHandle, payload: dict[str, Any], *, timeout: int, on_token: Any = None) -> tuple[str, int]:
    payload = dict(payload)
    payload["stream"] = True
    content_parts: list[str] = []
    tokens = 0
    with requests.post(
        handle.endpoint.rstrip("/") + "/v1/chat/completions",
        json=payload,
        stream=True,
        timeout=timeout,
    ) as resp:
        if resp.status_code >= 400:
            detail = (resp.text or "").strip()[:500]
            raise requests.HTTPError(
                f"{resp.status_code} Client Error for {resp.url}: {detail}",
                response=resp,
            )
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = str(raw_line)
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            piece = str(delta.get("content") or "")
            if piece:
                content_parts.append(piece)
                tokens += 1
                if on_token is not None:
                    try:
                        on_token(piece)
                    except Exception:
                        pass
            usage = data.get("usage") or {}
            if usage.get("completion_tokens") is not None:
                try:
                    tokens = int(usage.get("completion_tokens") or tokens)
                except Exception:
                    pass
    text = "".join(content_parts).strip()
    return text, tokens or len(text.split())


def snapshot() -> list[dict]:
    with _LOCK:
        out = []
        for model, proc in _PROCS.items():
            port = _PORTS.get(model)
            endpoint = f"http://{HOST}:{port}" if port else ""
            out.append({
                "model": model,
                "pid": proc.pid,
                "running": proc.poll() is None,
                "endpoint": endpoint,
                "port": port,
                "healthy": bool(endpoint and proc.poll() is None and _server_alive(endpoint)),
                "ram_gb": float((registry.get(model).ram_gb if registry.get(model) else 0.0) or 0.0),
            })
        return out


def _stop_locked(name: str, *, timeout: int = 10) -> bool:
    proc = _PROCS.pop(name, None)
    if not proc:
        return False
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
    return True


def stop(model: str | None = None) -> int:
    with _LOCK:
        targets = [model] if model else list(_PROCS)
        stopped = 0
        for name in targets:
            if _stop_locked(name):
                stopped += 1
        return stopped
