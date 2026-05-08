"""frontend/blueprints/studio_evidence.py — pin partial trails to Studio.

STEP-CHAT-THOUGHT-BUBBLES-PERSIST-TO-STUDIO-20260430.

When a chat thinking-trail bubble freezes (timeout, failure, stall, or just
finishes), the operator can hit "Pin to Studio" to keep the partial reasoning
attached to the project's evidence ledger so it doesn't get lost when Studio
re-renders or the thread scrolls away.

Schema is tiny on purpose — this is a notebook, not a fact store.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

from flask import Blueprint, jsonify, request

studio_evidence_bp = Blueprint("studio_evidence", __name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    conversation_id INTEGER,
    job_id TEXT,
    agent TEXT,
    status TEXT,
    stage TEXT,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_studio_evidence_conv
    ON studio_evidence(conversation_id, created_at);
"""


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


@studio_evidence_bp.route("/api/studio/evidence/pin", methods=["POST"])
def api_studio_evidence_pin():
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind") or "thinking_trail")[:64]
    conv = data.get("conversation_id")
    try:
        conv_id = int(conv) if conv is not None else None
    except (TypeError, ValueError):
        conv_id = None
    job_id = str(data.get("job_id") or "")[:128] or None
    agent = str(data.get("agent") or "")[:64] or None
    status = str(data.get("status") or "")[:32] or None
    stage = str(data.get("stage") or "")[:256] or None
    payload = json.dumps(data, default=str)[:32_000]
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO studio_evidence "
            "(kind, conversation_id, job_id, agent, status, stage, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, conv_id, job_id, agent, status, stage, payload, time.time()),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"ok": True, "id": new_id})


@studio_evidence_bp.route("/api/studio/evidence")
def api_studio_evidence_list():
    conv = request.args.get("conversation_id")
    try:
        conv_id = int(conv) if conv is not None else None
    except (TypeError, ValueError):
        conv_id = None
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except (TypeError, ValueError):
        limit = 50
    conn = _db()
    try:
        if conv_id is not None:
            rows = conn.execute(
                "SELECT id, kind, conversation_id, job_id, agent, status, stage, "
                "payload, created_at FROM studio_evidence "
                "WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?",
                (conv_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, kind, conversation_id, job_id, agent, status, stage, "
                "payload, created_at FROM studio_evidence "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        try:
            payload = json.loads(r["payload"]) if r["payload"] else {}
        except (TypeError, ValueError):
            payload = {}
        items.append({
            "id": r["id"], "kind": r["kind"],
            "conversation_id": r["conversation_id"], "job_id": r["job_id"],
            "agent": r["agent"], "status": r["status"], "stage": r["stage"],
            "payload": payload, "created_at": r["created_at"],
        })
    return jsonify({"ok": True, "items": items})
