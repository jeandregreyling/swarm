"""frontend/blueprints/email_accounts.py — runtime email accounts registry.

MD-FEATURE-1260A5EFA63E. The Email tile already exposes folder navigation
and an account manager modal, but the modal could only flag changes — there
was no persistent runtime list. This blueprint adds:

  GET    /api/email/accounts              → list configured + runtime accounts
  POST   /api/email/accounts              → add a runtime account
  DELETE /api/email/accounts/<email>      → remove a runtime account
  POST   /api/email/accounts/<email>/note → record the change reason

Runtime accounts live in a tiny settings_email_accounts table. The actual
IMAP/SMTP credentials still live in utils/config.py + swarm-sniffles
secrets — this registry is the user-visible source of truth for which
accounts the Email tile knows about.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time

from flask import Blueprint, jsonify, request

email_accounts_bp = Blueprint("email_accounts", __name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings_email_accounts (
    email TEXT PRIMARY KEY,
    label TEXT,
    note TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def _config_accounts() -> list[str]:
    """Pull the static config-managed account list from utils.config.

    The historical name was ``_EMAIL_ACCOUNTS`` but the module exposes the
    individual ``SEVEN_EMAIL`` / ``NINE_EMAIL`` / ``GHOST_EMAIL`` / Gmail
    address constants instead. We probe both shapes so the registry stays
    accurate without forcing a rename in utils.config.
    """
    try:
        from utils import config as _cfg
    except Exception:
        return []
    accounts: list[str] = []
    bulk = getattr(_cfg, "_EMAIL_ACCOUNTS", None)
    if bulk:
        accounts.extend(str(a).strip().lower() for a in bulk if a)
    for attr in ("SEVEN_EMAIL", "NINE_EMAIL", "GHOST_EMAIL", "GMAIL_ADDRESS"):
        val = getattr(_cfg, attr, None)
        if isinstance(val, str) and "@" in val:
            accounts.append(val.strip().lower())
    seen, out = set(), []
    for e in accounts:
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


@email_accounts_bp.route("/api/email/accounts")
def api_email_accounts_list():
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT email, label, note, created_at, updated_at FROM settings_email_accounts "
            "ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    runtime = [dict(r) for r in rows]
    runtime_set = {r["email"] for r in runtime}
    config_only = [
        {"email": e, "label": "", "note": "from utils/config.py",
         "created_at": None, "updated_at": None, "source": "config"}
        for e in _config_accounts() if e not in runtime_set
    ]
    for r in runtime:
        r["source"] = "runtime"
    return jsonify({"ok": True, "accounts": config_only + runtime})


@email_accounts_bp.route("/api/email/accounts", methods=["POST"])
def api_email_accounts_add():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "invalid email"}), 400
    label = str(data.get("label") or "")[:128]
    note = str(data.get("note") or "")[:512]
    now = time.time()
    conn = _db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings_email_accounts "
            "(email, label, note, created_at, updated_at) VALUES "
            "(?, ?, ?, COALESCE((SELECT created_at FROM settings_email_accounts WHERE email=?), ?), ?)",
            (email, label, note, email, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "email": email})


@email_accounts_bp.route("/api/email/accounts/<path:email>", methods=["DELETE"])
def api_email_accounts_delete(email: str):
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "invalid email"}), 400
    if email in _config_accounts():
        return jsonify({
            "ok": False,
            "error": "config-managed account — edit utils/config.py to remove",
        }), 409
    conn = _db()
    try:
        cur = conn.execute(
            "DELETE FROM settings_email_accounts WHERE email=?", (email,)
        )
        conn.commit()
        removed = cur.rowcount
    finally:
        conn.close()
    return jsonify({"ok": True, "removed": removed})


@email_accounts_bp.route("/api/email/accounts/<path:email>/note", methods=["POST"])
def api_email_accounts_note(email: str):
    email = (email or "").strip().lower()
    data = request.get_json(silent=True) or {}
    note = str(data.get("note") or "")[:512]
    now = time.time()
    conn = _db()
    try:
        conn.execute(
            "UPDATE settings_email_accounts SET note=?, updated_at=? WHERE email=?",
            (note, now, email),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})
