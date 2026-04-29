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
