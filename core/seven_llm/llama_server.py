"""Warm llama.cpp server manager for Seven direct GGUF models."""
from __future__ import annotations

import contextlib
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import signal
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
# Host RAM all resident models may claim together; least-recently-used models
# are evicted to stay under it and above the live RAM_RESERVE_GB headroom.
RAM_BUDGET_GB = float(os.environ.get("SEVEN_LLAMA_RAM_BUDGET_GB", "60"))
SINGLE_RESIDENT = os.environ.get("SEVEN_LLAMA_SINGLE_RESIDENT", "0").strip().lower() not in {"0", "false", "no", ""}
# llama-server keeps up to 8 GiB of prompt cache per server in host RAM by default.
CACHE_RAM_MIB = int(os.environ.get("SEVEN_LLAMA_CACHE_RAM_MIB", "256"))
# Make the kernel pick a model server before editors/browsers under memory pressure.
OOM_SCORE_ADJ = int(os.environ.get("SEVEN_LLAMA_OOM_SCORE_ADJ", "900"))
SYSTEMD_SCOPE = os.environ.get("SEVEN_LLAMA_SYSTEMD_SCOPE", "auto").strip().lower()
LOCK_PATH = os.environ.get("SEVEN_LLAMA_LOCK_PATH", f"/tmp/seven-llama-server-{os.getuid()}.lock")
STATE_PATH = os.environ.get("SEVEN_LLAMA_STATE_PATH", f"/tmp/seven-llama-server-{os.getuid()}.state.json")


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
    configured = os.environ.get("SEVEN_LLAMA_SERVER")
    if configured:
        return configured
    repo_build = os.path.join(_root(), "agents", "seven", "llama.cpp", "build", "bin", "llama-server")
    if os.path.isfile(repo_build):
        return repo_build
    releases = sorted(glob.glob(os.path.expanduser("~/llama.cpp/llama-b*/llama-server")),
                      key=lambda p: int(re.sub(r"\D", "", os.path.basename(os.path.dirname(p))) or 0))
    if releases:
        return releases[-1]
    return shutil.which("llama-server") or repo_build


def _server_environment(binary: str) -> dict[str, str]:
    env = os.environ.copy()
    library_dir = os.path.dirname(os.path.abspath(binary))
    existing = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        path for path in (library_dir, existing) if path
    )
    return env


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


def _vram_free_gb() -> float | None:
    """Free dedicated VRAM across amdgpu cards, or None when not reported."""
    free = 0.0
    found = False
    for total_path in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
        try:
            with open(total_path, encoding="utf-8") as fh:
                total = int(fh.read().strip())
            with open(total_path.replace("_total", "_used"), encoding="utf-8") as fh:
                used = int(fh.read().strip())
        except (OSError, ValueError):
            continue
        found = True
        free += max(0, total - used) / 1024 ** 3
    return free if found else None


def _foreign_servers() -> list[dict[str, Any]]:
    """llama-server processes owned by this user but not tracked in _PROCS.

    _PROCS is per Python process and servers outlive their parent, so without
    this every worker/service process would launch its own copy of a model.
    """
    own = {proc.pid for proc in _PROCS.values()}
    uid = os.getuid()
    found: list[dict[str, Any]] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) in own:
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid != uid:
                continue
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                argv = [a.decode("utf-8", "replace") for a in fh.read().split(b"\0") if a]
        except OSError:
            continue
        if not argv or os.path.basename(argv[0]) != "llama-server" or "--alias" not in argv:
            continue
        try:
            alias = argv[argv.index("--alias") + 1]
            port = int(argv[argv.index("--port") + 1])
        except (ValueError, IndexError):
            continue
        found.append({"pid": int(entry), "model": alias, "port": port})
    return found


def _kill_pid(pid: int, *, timeout: int = 10) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not os.path.exists(f"/proc/{pid}"):
            return
        time.sleep(0.2)
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)


@contextlib.contextmanager
def _cross_process_lock():
    with open(LOCK_PATH, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _load_state() -> dict[str, dict[str, Any]]:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict[str, dict[str, Any]]) -> None:
    tmp = f"{STATE_PATH}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, STATE_PATH)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


def _residents() -> list[dict[str, Any]]:
    """Every running llama-server of this user, ours and other processes'."""
    out = [
        {"model": name, "pid": proc.pid, "port": _PORTS.get(name), "own": True}
        for name, proc in list(_PROCS.items()) if proc.poll() is None
    ]
    out.extend({**item, "own": False} for item in _foreign_servers())
    return out


def _stop_resident(resident: dict[str, Any]) -> None:
    if resident.get("own"):
        _stop_locked(str(resident["model"]))
    else:
        _kill_pid(int(resident["pid"]))


def _uses_gpu(entry: registry.ModelEntry) -> bool:
    ngl = (entry.options or {}).get("ngl")
    return ngl is None or int(ngl) != 0


def _host_need_gb(entry: registry.ModelEntry) -> float:
    """Host RAM a model will occupy once loaded, given current free VRAM."""
    ram = float(entry.ram_gb or 4.0)
    ngl = (entry.options or {}).get("ngl")
    if ngl is not None and int(ngl) == 0:
        return ram
    vram_free = _vram_free_gb()
    if vram_free is None:
        return min(ram, 4.0) if ngl is not None else ram
    # Auto-fit keeps ~1 GiB VRAM margin and leaves remaining layers in normal
    # RAM; a forced ngl spills the overflow into GTT, which is pinned host RAM.
    margin = 0.0 if ngl is not None else 1.0
    spill = max(0.0, ram - max(0.0, vram_free - margin))
    return max(min(ram, 1.0), spill)


def _charged_gb(resident: dict[str, Any], state: dict[str, dict[str, Any]]) -> float:
    info = state.get(resident["model"]) or {}
    if info.get("host_gb") is not None:
        return float(info["host_gb"])
    entry = registry.get(resident["model"])
    return float(entry.ram_gb) if entry else 4.0


def _pick_victim(
    others: list[dict[str, Any]], state: dict[str, dict[str, Any]], *, prefer_gpu: bool,
) -> dict[str, Any] | None:
    if not others:
        return None

    def on_gpu(resident: dict[str, Any]) -> bool:
        info = state.get(resident["model"]) or {}
        if "gpu" in info:
            return bool(info["gpu"])
        entry = registry.get(resident["model"])
        return bool(entry and _uses_gpu(entry))

    pool = [r for r in others if on_gpu(r)] if prefer_gpu else []
    pool = pool or others
    return min(pool, key=lambda r: float((state.get(r["model"]) or {}).get("last_used") or 0.0))


def _reap_idle(state: dict[str, dict[str, Any]], *, keep: str) -> None:
    """Stop servers idle past their ttl_seconds (0 keeps them until evicted)."""
    now = time.time()
    running = set()
    for resident in _residents():
        name = resident["model"]
        running.add(name)
        if name == keep:
            continue
        info = state.setdefault(name, {"last_used": now})
        entry = registry.get(name)
        ttl = int(entry.ttl_seconds or 0) if entry else 0
        if ttl > 0 and now - float(info.get("last_used") or now) > ttl:
            _stop_resident(resident)
            running.discard(name)
    for name in list(state):
        if name not in running and name != keep:
            state.pop(name, None)


def resource_snapshot() -> dict[str, Any]:
    snap = _meminfo_gb()
    snap["servers"] = snapshot()
    snap["foreign_servers"] = _foreign_servers()
    state = _load_state()
    snap["residents"] = [
        {**r, "host_gb": round(_charged_gb(r, state), 2),
         "last_used": (state.get(r["model"]) or {}).get("last_used")}
        for r in _residents()
    ]
    snap["charged_gb"] = round(sum(r["host_gb"] for r in snap["residents"]), 2)
    return snap


def _admit(model: str, state: dict[str, dict[str, Any]]) -> float:
    """Evict LRU servers until ``model`` fits; returns its host RAM charge."""
    entry = registry.get(model)
    if not entry:
        raise RuntimeError(f"no direct GGUF model registered for '{model}'")
    mem = _meminfo_gb()
    total = float(mem.get("total_gb") or 0.0)
    reserve = float(mem.get("reserve_gb") or 0.0)
    need = _host_need_gb(entry)
    if total and need + reserve > total:
        raise RuntimeError(
            f"direct runtime resource guard blocked {model}: "
            f"requires {need:.1f}GB + {reserve:.1f}GB reserve, system total {total:.1f}GB"
        )
    if SINGLE_RESIDENT:
        for resident in _residents():
            if resident["model"] != model:
                _stop_resident(resident)
                state.pop(resident["model"], None)
    tried: set[int] = set()
    while True:
        others = [r for r in _residents() if r["model"] != model and int(r["pid"]) not in tried]
        need = _host_need_gb(entry)
        charged = sum(_charged_gb(r, state) for r in others)
        available = float(_meminfo_gb().get("available_gb") or 0.0)
        over_budget = charged + need > RAM_BUDGET_GB
        over_live = bool(available) and need + reserve > available
        if not over_budget and not over_live:
            return need
        spilling = _uses_gpu(entry) and need > min(float(entry.ram_gb or 4.0), 1.0)
        victim = _pick_victim(others, state, prefer_gpu=spilling)
        if victim is None:
            raise RuntimeError(
                f"direct runtime resource guard blocked {model}: "
                f"requires {need:.1f}GB + {reserve:.1f}GB reserve, available {available:.1f}GB "
                f"(models charged {charged:.1f}GB of {RAM_BUDGET_GB:.0f}GB budget)"
            )
        tried.add(int(victim["pid"]))
        _stop_resident(victim)
        state.pop(victim["model"], None)


_SCOPE_OK: bool | None = None


def _launcher_prefix(model: str, port: int) -> list[str]:
    """Run each server in its own systemd scope.

    Children otherwise inherit the caller's cgroup (e.g. VS Code's scope), and
    systemd stops that whole scope when one member is OOM-killed.
    """
    global _SCOPE_OK
    if SYSTEMD_SCOPE in {"0", "false", "no", "off"}:
        return []
    exe = shutil.which("systemd-run")
    # System services (e.g. swarm-terminal.service) run without a session
    # environment; reach the user manager through its runtime dir instead.
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if not exe or not os.path.exists(os.path.join(runtime_dir, "bus")):
        return []
    prefix = ["env", f"XDG_RUNTIME_DIR={runtime_dir}",
              f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir}/bus", exe]
    if _SCOPE_OK is None:
        try:
            _SCOPE_OK = subprocess.run(
                prefix + ["--user", "--scope", "--quiet", "--collect", "true"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            _SCOPE_OK = False
    if not _SCOPE_OK:
        return []
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-")[:40] or "model"
    return prefix + ["--user", "--scope", "--quiet", "--collect",
                     f"--unit=swarm-llama-{slug}-{port}-{int(time.time())}", "-p", "OOMPolicy=continue"]


def _set_oom_score(pid: int) -> None:
    with contextlib.suppress(OSError, ValueError):
        with open(f"/proc/{pid}/oom_score_adj", "w", encoding="ascii") as fh:
            fh.write(str(OOM_SCORE_ADJ))


def ensure(model: str, *, timeout_s: int = STARTUP_TIMEOUT_S) -> ServerHandle:
    entry = registry.get(model)
    if not entry or entry.driver != "llamacpp" or not entry.path:
        raise RuntimeError(f"no direct GGUF model registered for '{model}'")
    if not os.path.isfile(entry.path):
        raise RuntimeError(f"GGUF path missing for '{model}': {entry.path}")
    model = entry.name

    with _LOCK, _cross_process_lock():
        state = _load_state()

        def touch(charge: float | None = None) -> None:
            info = state.setdefault(model, {})
            info["last_used"] = time.time()
            info.setdefault("gpu", _uses_gpu(entry))
            if charge is not None:
                info["host_gb"] = round(charge, 2)
            _save_state(state)

        proc = _PROCS.get(model)
        if proc is None:
            for foreign in _foreign_servers():
                if foreign["model"] != model:
                    continue
                endpoint = f"http://{HOST}:{foreign['port']}"
                if _server_alive(endpoint):
                    _PORTS[model] = foreign["port"]
                    touch()
                    return ServerHandle(model, endpoint, foreign["port"], foreign["pid"], time.time())
                # Same model but unresponsive (stuck or half-started): replace it.
                _kill_pid(foreign["pid"], timeout=5)
        port = _port_for(model)
        endpoint = f"http://{HOST}:{port}"
        if proc is not None and proc.poll() is None and _server_alive(endpoint):
            touch()
            return ServerHandle(model, endpoint, port, proc.pid, time.time())

        if proc is not None and proc.poll() is None:
            _stop_locked(model, timeout=5)

        _reap_idle(state, keep=model)
        charge = _admit(model, state)
        _save_state(state)

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
            # Read weights into anonymous memory so MemAvailable reflects what
            # the model really holds (mmap'd weights look reclaimable).
            "--load-mode", str(opts.get("load_mode") or "none"),
            "--cache-ram", str(int(opts.get("cache_ram_mib", CACHE_RAM_MIB))),
        ]
        if "threads" in opts:
            cmd.extend(["--threads", str(int(opts["threads"]))])
        if "ngl" in opts:
            cmd.extend(["--n-gpu-layers", str(int(opts["ngl"]))])
        if opts.get("chat_template_file"):
            # e.g. gpt-oss blobs from an Ollama store carry a ChatML template;
            # harmony models need their own jinja or channels leak into content.
            cmd.extend(["--chat-template-file", str(opts["chat_template_file"])])
        if opts.get("mmproj"):
            cmd.extend(["--mmproj", str(opts["mmproj"])])
        if bool(opts.get("embedding")):
            cmd.append("--embedding")

        log_path = os.path.join("/tmp", f"seven-llama-server-{model.replace(':', '_').replace('/', '_')}.log")
        log_fh = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            _launcher_prefix(model, port) + cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
            close_fds=True,
            start_new_session=True,
            env=_server_environment(binary),
        )
        _PROCS[model] = proc
        _set_oom_score(proc.pid)

        if timeout_s == STARTUP_TIMEOUT_S:
            # 24B weights from slow disk take ~130s on CPU; scale with model size.
            timeout_s = max(timeout_s, int(float(entry.ram_gb or 0) * 15))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if proc.poll() is not None:
                _PROCS.pop(model, None)
                raise RuntimeError(f"llama-server exited during startup for {model}; see {log_path}")
            if _server_alive(endpoint):
                touch(charge)
                return ServerHandle(model, endpoint, port, proc.pid, time.time())
            time.sleep(1)
        _stop_locked(model, timeout=5)
    raise RuntimeError(f"llama-server startup timeout for {model}; see {log_path}")


def _chat_payload(model: str, messages: list[dict], *, temperature: float | None, options: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [_openai_message(m) for m in messages],
        "stream": False,
        "max_tokens": int(options.get("num_predict") or options.get("max_tokens") or 2048),
        "temperature": float(temperature if temperature is not None else (
            options.get("temperature") if options.get("temperature") is not None else 0.7)),
    }
    stops = options.get("stop") or default_stops(model, explicit=str(options.get("profile") or ""))
    if stops:
        payload["stop"] = [stops] if isinstance(stops, str) else list(stops)
    if options.get("response_format") is not None:
        payload["response_format"] = _openai_response_format(options["response_format"])
    return payload


def _openai_message(message: dict) -> dict:
    """Convert Ollama-style `images` (base64 strings) into OpenAI content parts."""
    images = message.get("images") if isinstance(message, dict) else None
    if not images:
        return message
    out = {k: v for k, v in message.items() if k != "images"}
    parts: list[dict[str, Any]] = []
    if message.get("content"):
        parts.append({"type": "text", "text": str(message["content"])})
    for image in images:
        url = image if str(image).startswith("data:") else f"data:image/jpeg;base64,{image}"
        parts.append({"type": "image_url", "image_url": {"url": url}})
    out["content"] = parts
    return out


def _openai_response_format(fmt: Any) -> Any:
    """Accept Ollama's `format` ('json' or a bare JSON schema) as well as OpenAI's."""
    if isinstance(fmt, str):
        return {"type": "json_object"} if fmt.strip().lower() == "json" else fmt
    if isinstance(fmt, dict) and fmt.get("type") not in {"json_object", "json_schema", "text"}:
        return {"type": "json_object", "schema": fmt}
    return fmt


def _raw_completion_chat(handle, messages, *, temperature, opts):
    """gpt-oss via /completion: hand-built harmony prompt, raw text back.

    The OpenAI chat endpoint splits harmony channels and can return empty
    content on action turns; /completion returns the raw continuation with
    SKILL lines intact (measured 2026-10-21, llama.cpp b11756).
    """
    hp = []
    for m in messages or []:
        role = str((m or {}).get("role") or "user")
        content = str((m or {}).get("content") or "")
        if content:
            hp.append(f"<|start|>{role}<|message|>{content}<|end|>")
    hp.append("<|start|>assistant")
    payload = {
        "prompt": "".join(hp),
        "n_predict": int(opts.get("n_predict") or 1024),
        "temperature": float(temperature if temperature is not None else 0.6),
        "stop": ["<|return|>", "<|call|>"],
        "cache_prompt": True,
    }
    resp = requests.post(
        handle.endpoint.rstrip("/") + "/completion",
        json=payload,
        timeout=int(opts.get("timeout") or 180),
    )
    resp.raise_for_status()
    data = resp.json() or {}
    text = str(data.get("content") or "")
    # strip harmony channel tags, keep the bodies (SKILL lines live in there)
    text = re.sub(r"<\|channel\|>[a-z]+<\|message\|>", "\n", text)
    for tag in ("<|start|>", "<|end|>", "<|return|>", "<|call|>"):
        text = text.replace(tag, "")
    text = text.strip()
    tokens = int(data.get("tokens_predicted") or len(text.split()) or 0)
    return text, tokens


def _with_default_system(messages: list[dict], system: str) -> list[dict]:
    """Ollama applies a Modelfile SYSTEM only when the caller sends none."""
    if not system or any(str((m or {}).get("role") or "") == "system" for m in messages or []):
        return messages
    return [{"role": "system", "content": system}, *(messages or [])]


def _retry_if_evicted(model: str, opts: dict, call: Any) -> Any:
    """Re-ensure once when the server vanished (evicted or OOM-killed) mid-request."""
    startup = int(opts.get("startup_timeout") or STARTUP_TIMEOUT_S)
    handle = ensure(model, timeout_s=startup)
    try:
        return call(handle)
    except requests.ConnectionError:
        return call(ensure(model, timeout_s=startup))


def chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float | None = None,
    options: dict | None = None,
    on_token: Any = None,
) -> tuple[str, int]:
    opts = dict(options or {})
    entry = registry.get(model)
    if entry:
        model = entry.name
        opts = {**dict(entry.options or {}), **opts}
        messages = _with_default_system(messages, str(opts.get("default_system") or ""))
    if entry and (entry.options or {}).get("raw_completion"):
        return _retry_if_evicted(model, opts, lambda handle: _raw_completion_chat(
            handle, messages, temperature=temperature, opts=opts))
    payload = _chat_payload(model, messages, temperature=temperature, options=opts)
    if callable(on_token) or opts.get("stream"):
        return _retry_if_evicted(model, opts, lambda handle: _chat_stream(
            handle, payload, timeout=int(opts.get("timeout") or 180), on_token=on_token))
    return _retry_if_evicted(model, opts, lambda handle: _chat_once(handle, payload, opts))


def _chat_once(handle: ServerHandle, payload: dict[str, Any], opts: dict) -> tuple[str, int]:
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
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    text = str(msg.get("content") or "").strip()
    if not text:
        raise RuntimeError('Direct model produced no final answer; reasoning is not an executable reply')
    tokens = int((data.get("usage") or {}).get("completion_tokens") or len(text.split()) or 0)
    return text, tokens


def embeddings(model: str, prompt: str, *, options: dict | None = None) -> list[float]:
    opts = dict(options or {})
    entry = registry.get(model)
    model = entry.name if entry else model

    def call(handle: ServerHandle) -> Any:
        resp = requests.post(
            handle.endpoint.rstrip("/") + "/v1/embeddings",
            json={"model": model, "input": str(prompt or "")},
            timeout=int(opts.get("timeout") or 120),
        )
        resp.raise_for_status()
        return resp.json()

    data = _retry_if_evicted(model, opts, call)
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
    thinking_parts: list[str] = []
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
            think_piece = str(delta.get("reasoning_content") or "")
            if think_piece:
                thinking_parts.append(think_piece)
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
    if not text:
        raise RuntimeError('Direct model produced no final answer; reasoning is not an executable reply')
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
    """Stop our servers (all, or one model's server wherever it was started)."""
    with _LOCK:
        if model:
            entry = registry.get(model)
            model = entry.name if entry else model
        targets = [model] if model else list(_PROCS)
        stopped = 0
        for name in targets:
            if _stop_locked(name):
                stopped += 1
        if model:
            for foreign in _foreign_servers():
                if foreign["model"] == model:
                    _kill_pid(int(foreign["pid"]))
                    stopped += 1
        return stopped
