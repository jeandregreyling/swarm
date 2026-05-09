"""core.swarm_platform — runtime capability detection for the swarm.

Every deploy asks the same question: *which of the OS-dependent subsystems
can I use right now, and which must degrade?* This module answers it once,
honestly, with no import-time surprises.

Public surface::

    from core.swarm_platform import capabilities, summary
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
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_CACHE: Optional[Dict[str, Any]] = None
_CACHE_TS: float = 0.0
_CACHE_TTL: float = 30.0  # seconds


# ---------------------------------------------------------------------------
# Individual probes — each returns {"available": bool, ...extras}
# ---------------------------------------------------------------------------

def _probe_systemd() -> Dict[str, Any]:
    """Check whether systemd is the init system and systemctl is reachable."""
    try:
        if _py_platform.system() != "Linux":
            return {"available": False, "reason": "not Linux"}
        # PID 1 comm is "systemd" on systemd systems
        init_comm = ""
        try:
            with open("/proc/1/comm", "r") as f:
                init_comm = f.read().strip()
        except OSError:
            pass
        has_systemctl = shutil.which("systemctl") is not None
        available = init_comm == "systemd" and has_systemctl
        result: Dict[str, Any] = {"available": available}
        if not available:
            reasons = []
            if init_comm != "systemd":
                reasons.append(f"init is '{init_comm}', not systemd")
            if not has_systemctl:
                reasons.append("systemctl not found")
            result["reason"] = "; ".join(reasons)
        return result
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _probe_sensors() -> Dict[str, Any]:
    """Check for lm-sensors / psutil sensor support."""
    try:
        # Prefer psutil.sensors_temperatures if available
        try:
            import psutil  # type: ignore[import-untyped]
            temps = psutil.sensors_temperatures()
            return {"available": True, "source": "psutil", "zones": len(temps)}
        except (ImportError, AttributeError):
            pass
        # Fall back to sensors binary
        if shutil.which("sensors"):
            return {"available": True, "source": "lm-sensors"}
        return {"available": False, "reason": "no psutil or lm-sensors"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _probe_notify() -> Dict[str, Any]:
    """Check desktop notification support (notify-send on Linux)."""
    try:
        if _py_platform.system() == "Linux":
            if shutil.which("notify-send"):
                return {"available": True, "backend": "notify-send"}
            return {"available": False, "reason": "notify-send not found"}
        if _py_platform.system() == "Darwin":
            if shutil.which("osascript"):
                return {"available": True, "backend": "osascript"}
            return {"available": False, "reason": "osascript not found"}
        return {"available": False, "reason": f"unsupported OS: {_py_platform.system()}"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _probe_tauri() -> Dict[str, Any]:
    """Check whether Tauri desktop shell is buildable."""
    try:
        has_cargo = shutil.which("cargo") is not None
        conf = os.path.join(os.path.dirname(__file__), "..", "desktop", "tauri.conf.json")
        has_conf = os.path.isfile(conf)
        available = has_cargo and has_conf
        result: Dict[str, Any] = {"available": available}
        if not available:
            reasons = []
            if not has_cargo:
                reasons.append("cargo not found")
            if not has_conf:
                reasons.append("desktop/tauri.conf.json missing")
            result["reason"] = "; ".join(reasons)
        return result
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _probe_browsers() -> Dict[str, Any]:
    """Detect available browsers for headless/automation work."""
    try:
        found = []
        for name in ("chromium-browser", "chromium", "google-chrome",
                      "firefox", "firefox-esr"):
            if shutil.which(name):
                found.append(name)
        return {"available": len(found) > 0, "browsers": found}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _probe_ollama() -> Dict[str, Any]:
    """Check whether ollama CLI is installed and the daemon is reachable."""
    try:
        if not shutil.which("ollama"):
            return {"available": False, "reason": "ollama binary not found"}
        # Quick version check (fast, no network)
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, text=True, timeout=2,
            )
            version = result.stdout.strip() or result.stderr.strip()
        except Exception:
            version = "unknown"
        return {"available": True, "version": version}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Composite builder
# ---------------------------------------------------------------------------

def _build_capabilities() -> Dict[str, Any]:
    """Run all probes and assemble the full capabilities dict."""
    system = _py_platform.system()

    caps: Dict[str, Any] = {
        "os": {
            "system": system,
            "release": _py_platform.release(),
            "machine": _py_platform.machine(),
        },
        "python": {
            "version": _py_platform.python_version(),
            "executable": sys.executable,
        },
        "systemd": _probe_systemd(),
        "sensors": _probe_sensors(),
        "notify": _probe_notify(),
        "tauri": _probe_tauri(),
        "browsers": _probe_browsers(),
        "ollama": _probe_ollama(),
        "linux_primary": system == "Linux" and _probe_systemd().get("available", False),
        "fan_operator_supported": (
            system == "Linux"
            and _probe_sensors().get("available", False)
        ),
    }
    return caps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capabilities(*, force: bool = False) -> Dict[str, Any]:
    """Return the cached capabilities dict.

    Parameters
    ----------
    force : bool
        If *True*, rebuild the dict even if the cache is fresh.

    Returns
    -------
    dict
        The full capabilities mapping. Cached for ``_CACHE_TTL`` seconds.
    """
    global _CACHE, _CACHE_TS

    now = time.monotonic()
    if not force and _CACHE is not None and (now - _CACHE_TS) < _CACHE_TTL:
        return _CACHE

    _CACHE = _build_capabilities()
    _CACHE_TS = now
    return _CACHE


def summary() -> Dict[str, Any]:
    """Return a JSON-safe summary suitable for ``/api/platform``.

    Always contains ``ok: True`` and a ``capabilities`` sub-dict with
    per-probe availability, plus the ``os`` block at top level.
    """
    caps = capabilities()
    probe_names = ("systemd", "sensors", "notify", "tauri", "browsers", "ollama")
    cap_summary: Dict[str, Any] = {}
    for name in probe_names:
        block = caps.get(name, {})
        cap_summary[name] = block

    return {
        "ok": True,
        "os": caps["os"],
        "capabilities": cap_summary,
        "linux_primary": caps["linux_primary"],
        "fan_operator_supported": caps["fan_operator_supported"],
    }
