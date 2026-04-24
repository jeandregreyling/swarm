"""core.platform — runtime capability detection for the swarm.

Every deploy asks the same question: *which of the OS-dependent subsystems
can I use right now, and which must degrade?* This module answers it once,
honestly, with no import-time surprises.

Public surface::

    from core.platform import capabilities, summary
    caps = capabilities()   # full dict with boolean flags + hints
    rep  = summary()        # trimmed JSON-safe report for /api/platform

Design rules:
    * Every probe is wrapped — a missing binary or permission error returns
      ``False`` with a ``reason`` string, never an exception.
    * Results are cached for 30 s so dashboard polls don't thrash subprocess.
    * No probe writes to disk, spawns long-running children, or blocks > 1 s.
"""
from __future__ import annotations

import os
import platform as _py_platform
import shutil
import subprocess
import sys
import time
from typing import Any, Dict

_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CACHE_TTL_S = 30.0


def _which(cmd: str) -> str:
    return shutil.which(cmd) or ""


def _run(cmd: list[str], timeout: float = 0.8) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return -1, str(e)


def _probe_systemd() -> Dict[str, Any]:
    path = _which("systemctl")
    if not path:
        return {"available": False, "reason": "systemctl not on PATH"}
    rc, _out = _run([path, "--version"])
    return {"available": rc == 0, "path": path}


def _probe_sensors() -> Dict[str, Any]:
    # The fan operator (V7C-A05) needs either `sensors` or a readable
    # thermal_zone file in /sys/class/thermal.
    sensors_path = _which("sensors")
    thermal_zone = "/sys/class/thermal/thermal_zone0/temp"
    thermal_ok = os.path.exists(thermal_zone) and os.access(thermal_zone, os.R_OK)
    return {
        "available": bool(sensors_path) or thermal_ok,
        "sensors_bin": sensors_path or None,
        "thermal_zone_readable": thermal_ok,
    }


def _probe_notify() -> Dict[str, Any]:
    path = _which("notify-send")
    return {"available": bool(path), "path": path or None}


def _probe_tauri() -> Dict[str, Any]:
    # Desktop shell is optional. Presence of the compiled binary is the truth.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidates = [
        os.path.join(repo_root, "desktop", "src-tauri", "target", "release", "sevens-swarm"),
        os.path.join(repo_root, "desktop", "src-tauri", "target", "debug", "sevens-swarm"),
    ]
    found = next((c for c in candidates if os.path.exists(c)), None)
    return {"available": bool(found), "path": found}


def _probe_browsers() -> Dict[str, Any]:
    browsers = {b: _which(b) for b in ("chromium", "google-chrome", "firefox")}
    browsers = {k: v for k, v in browsers.items() if v}
    return {"available": bool(browsers), "found": browsers}


def _probe_ollama() -> Dict[str, Any]:
    path = _which("ollama")
    if not path:
        return {"available": False, "reason": "ollama not on PATH"}
    rc, out = _run([path, "--version"])
    version = out.splitlines()[0] if rc == 0 and out else None
    return {"available": rc == 0, "version": version}


def _probe_python() -> Dict[str, Any]:
    return {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "venv": os.environ.get("VIRTUAL_ENV") or None,
    }


def _probe_os() -> Dict[str, Any]:
    return {
        "system": _py_platform.system(),       # Linux / Darwin / Windows
        "release": _py_platform.release(),
        "machine": _py_platform.machine(),
        "kernel": _py_platform.version(),
    }


def capabilities(force: bool = False) -> Dict[str, Any]:
    """Return the full capability report, cached for ``_CACHE_TTL_S``."""
    now = time.time()
    if not force and _CACHE["data"] and (now - _CACHE["ts"]) < _CACHE_TTL_S:
        return _CACHE["data"]

    data = {
        "os": _probe_os(),
        "python": _probe_python(),
        "systemd": _probe_systemd(),
        "sensors": _probe_sensors(),
        "notify": _probe_notify(),
        "tauri": _probe_tauri(),
        "browsers": _probe_browsers(),
        "ollama": _probe_ollama(),
        "generated_at": now,
    }
    # Compact "primary path" flag so UIs can render a single banner.
    data["linux_primary"] = (
        data["os"]["system"] == "Linux"
        and data["systemd"]["available"]
    )
    data["fan_operator_supported"] = data["sensors"]["available"]
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data


def summary() -> Dict[str, Any]:
    """JSON-safe shape tailored for the ``/api/platform`` endpoint."""
    caps = capabilities()
    return {
        "ok": True,
        "os": caps["os"],
        "linux_primary": caps["linux_primary"],
        "fan_operator_supported": caps["fan_operator_supported"],
        "capabilities": {
            name: bool(caps[name].get("available"))
            for name in ("systemd", "sensors", "notify", "tauri", "browsers", "ollama")
        },
        "details": {
            name: caps[name]
            for name in ("systemd", "sensors", "notify", "tauri", "browsers", "ollama")
        },
        "python": caps["python"],
        "generated_at": caps["generated_at"],
    }


__all__ = ["capabilities", "summary"]
