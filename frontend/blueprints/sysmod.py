"""frontend/blueprints/sysmod.py — settings-surface for the sysmod pack.

Stores the "system modifications enabled" flag plus per-capability opt-ins in
the central Swarm DB. The toggle surface in Settings calls these endpoints and
operators see the resolved state in the onboarding wizard.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

from flask import Blueprint, jsonify, request

sysmod_bp = Blueprint("sysmod", __name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings_sysmod (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

_DEFAULT = {
    "enabled": False,
    "capabilities": {
        "fan_controller": False,
        "desktop_shortcut": False,
        "autostart": False,
        "prewarm": False,
    },
}


def _db() -> sqlite3.Connection:
    override = os.environ.get("SWARM_DB")
    if override:
        conn = sqlite3.connect(override)
    else:
        from utils.db._connection import get_connection
        conn = get_connection()
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _load() -> dict:
    conn = _db()
    try:
        rows = conn.execute("SELECT key, value FROM settings_sysmod").fetchall()
    finally:
        conn.close()
    state = dict(_DEFAULT)
    state["capabilities"] = dict(_DEFAULT["capabilities"])
    for r in rows:
        try:
            val = json.loads(r["value"])
        except (TypeError, ValueError):
            val = r["value"]
        if r["key"] == "enabled":
            state["enabled"] = bool(val)
        elif r["key"].startswith("cap:"):
            state["capabilities"][r["key"][4:]] = bool(val)
    return state


def _store(key: str, value: object) -> None:
    conn = _db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings_sysmod (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


@sysmod_bp.route("/api/settings/sysmod")
def api_sysmod_get():
    return jsonify({"ok": True, **_load()})


@sysmod_bp.route("/api/settings/sysmod", methods=["POST"])
def api_sysmod_set():
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        _store("enabled", bool(data.get("enabled")))
    caps = data.get("capabilities") or {}
    for name, on in caps.items():
        if not isinstance(name, str):
            continue
        _store(f"cap:{name}", bool(on))
    return jsonify({"ok": True, **_load()})


# ── MD-FEATURE-C6D59801C77C — per-helper Settings panel ─────────────────────
# Inventory of installable system helpers. Once installed, operators can flip
# each one on/off from Settings. The endpoint returns:
#   - installed: service unit file present under /etc/systemd/system
#   - active:    systemctl is-active reports active (best-effort, no sudo)
#   - install_cmd / enable_cmd / disable_cmd: copy-pasteable shell commands
# Actual systemctl calls require sudo and live in the operator's terminal —
# the UI is read-only + clipboard helpers, never pretends to flip services.
_HELPERS = [
    {
        "id": "swarm-fanctl",
        "title": "Fan controller helper",
        "description": "Runs as root, exposes /run/swarm-fanctl.sock so Swarm can read temps and switch the CPU fan between auto and boost without per-call sudo.",
        "unit": "swarm-fanctl.service",
        "source": "ops/swarm-fanctl.service",
        "capability_key": "fan_controller",
    },
    {
        "id": "swarm-prewarm",
        "title": "Prewarm helper",
        "description": "Boots local model runners (Ollama, LM Studio) on system start so the first chat after a reboot doesn't pay the cold-start tax.",
        "unit": "swarm-prewarm.service",
        "source": "swarm-prewarm.service",
        "capability_key": "prewarm",
    },
]


def _systemctl_state(unit: str) -> dict:
    """Best-effort, no-sudo lookup of unit installation + activity."""
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    installed_path = os.path.join("/etc/systemd/system", unit)
    installed = os.path.exists(installed_path)
    active = False
    if installed:
        try:
            import subprocess
            res = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True, text=True, timeout=2,
            )
            active = (res.stdout.strip() == "active")
        except Exception:
            active = False
    return {
        "installed": installed,
        "active": active,
        "install_cmd": (
            f"sudo cp {repo}/ops/{unit} /etc/systemd/system/ && "
            f"sudo systemctl daemon-reload && "
            f"sudo systemctl enable --now {unit}"
        ),
        "enable_cmd": f"sudo systemctl enable --now {unit}",
        "disable_cmd": f"sudo systemctl disable --now {unit}",
        "status_cmd": f"systemctl status {unit}",
    }


@sysmod_bp.route("/api/settings/sysmod/helpers")
def api_sysmod_helpers():
    state = _load()
    out = []
    for h in _HELPERS:
        s = _systemctl_state(h["unit"])
        out.append({
            **h,
            **s,
            "capability_on": bool(state.get("capabilities", {}).get(h["capability_key"])),
        })
    return jsonify({
        "ok": True,
        "sysmod_enabled": bool(state.get("enabled")),
        "helpers": out,
    })
