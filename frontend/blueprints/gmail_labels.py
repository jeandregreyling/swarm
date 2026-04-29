"""frontend/blueprints/gmail_labels.py — Gmail label sync for Email folders.

Pairs the Swarm's local folder taxonomy (Inbox/Sent/Drafts/Trash + custom
system-notification labels) with the user's Gmail labels so the Email tile
reflects the upstream state rather than a parallel one.

Design:
- The Email tile calls ``GET /api/email/gmail/labels?account=<id>`` to list
  Gmail labels for a given account.
- ``POST /api/email/gmail/labels/sync`` (with optional ``account`` body)
  re-queries Gmail and writes the result to ``gmail_labels_cache`` in the
  central Swarm DB so the UI can render without a round-trip.
- Label mapping for system folders lives in ``GMAIL_SYSTEM_LABEL_MAP`` so
  tests can pin the relationships.

The IMAP/Gmail-API work is performed by the existing mail utilities; this
blueprint is the thin web surface the frontend needs.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Optional

from flask import Blueprint, jsonify, request

gmail_labels_bp = Blueprint("gmail_labels", __name__)


# Gmail's canonical SYSTEM labels mapped to the Swarm's local folder ids.
GMAIL_SYSTEM_LABEL_MAP: dict[str, str] = {
    "INBOX":              "inbox",
    "SENT":               "sent",
    "DRAFT":              "drafts",
    "TRASH":              "trash",
    "SPAM":               "spam",
    "IMPORTANT":          "important",
    "STARRED":            "starred",
    "Notifications":      "notifications",          # custom Swarm label
    "System Notifications": "system_notifications",
}


CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS gmail_labels_cache (
    account TEXT NOT NULL,
    label_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT,
    message_count INTEGER,
    unread_count INTEGER,
    synced_at REAL NOT NULL,
    PRIMARY KEY (account, label_id)
);
"""


def _db() -> sqlite3.Connection:
    override = os.environ.get("SWARM_DB")
    if override:
        conn = sqlite3.connect(override)
    else:
        from utils.db._connection import get_connection
        conn = get_connection()
    conn.row_factory = sqlite3.Row
    conn.executescript(CACHE_SCHEMA)
    return conn


def _fetch_gmail_labels(account: str) -> list[dict]:
    """Return fresh label list from Gmail API. Delegates to existing helpers
    if present; falls back to the system-label map so the surface still works
    in test and first-boot environments."""
    try:
        from utils.gmail_auth import get_imap_client  # type: ignore
    except Exception:
        get_imap_client = None  # type: ignore

    if get_imap_client is None:
        return [
            {"label_id": gl, "name": gl, "type": "system", "message_count": 0, "unread_count": 0}
            for gl in GMAIL_SYSTEM_LABEL_MAP
        ]

    try:
        mail = get_imap_client(account)
        typ, data = mail.list()
        labels: list[dict] = []
        if typ == "OK" and data:
            for raw in data:
                if not raw:
                    continue
                line = raw.decode() if isinstance(raw, bytes) else str(raw)
                name = line.split(' "/" ')[-1].strip().strip('"')
                labels.append({"label_id": name, "name": name, "type": "user",
                               "message_count": 0, "unread_count": 0})
        mail.logout()
        return labels
    except Exception:
        return []


@gmail_labels_bp.route("/api/email/gmail/labels")
def api_gmail_labels():
    account = (request.args.get("account") or "default").strip()
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT label_id, name, type, message_count, unread_count, synced_at "
            "FROM gmail_labels_cache WHERE account=? ORDER BY name ASC",
            (account,),
        ).fetchall()
    finally:
        conn.close()
    labels = [dict(r) for r in rows]
    return jsonify({
        "ok": True,
        "account": account,
        "labels": labels,
        "system_map": GMAIL_SYSTEM_LABEL_MAP,
        "cached": bool(labels),
    })


@gmail_labels_bp.route("/api/email/gmail/labels/sync", methods=["POST"])
def api_gmail_labels_sync():
    data = request.get_json(silent=True) or {}
    account = (data.get("account") or "default").strip()
    labels = _fetch_gmail_labels(account)
    now = time.time()
    conn = _db()
    try:
        conn.execute("DELETE FROM gmail_labels_cache WHERE account=?", (account,))
        for lab in labels:
            conn.execute(
                "INSERT OR REPLACE INTO gmail_labels_cache "
                "(account, label_id, name, type, message_count, unread_count, synced_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account, lab.get("label_id"), lab.get("name"),
                 lab.get("type") or "user",
                 int(lab.get("message_count") or 0),
                 int(lab.get("unread_count") or 0), now),
            )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "account": account, "count": len(labels), "synced_at": now})
