"""frontend/blueprints/enrollment.py — user-account enrolment endpoints.

Onboarding step 2 (Phase-5 BIG S-5E5BD3C268): create the owner account plus
optional co-owner / assistant accounts during first-boot. Delegates to
``login_bp`` primitives where possible so the password hashing and session
columns stay consistent with regular logins.
"""
from __future__ import annotations

import secrets
import os
import sqlite3
import time
from typing import Optional

from flask import Blueprint, jsonify, request

enrollment_bp = Blueprint("enrollment", __name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS enrollment_invites (
    token TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    email TEXT,
    created_at REAL NOT NULL,
    consumed_at REAL
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
    conn.executescript(SCHEMA)
    return conn


@enrollment_bp.route("/api/enrollment/status")
def api_enrollment_status():
    """Report whether the owner account exists and how many invites are open."""
    conn = _db()
    try:
        try:
            owner_row = conn.execute(
                "SELECT username FROM user_profiles WHERE role='owner' LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            owner_row = None
        open_invites = conn.execute(
            "SELECT COUNT(*) FROM enrollment_invites WHERE consumed_at IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    return jsonify({
        "ok": True,
        "owner_exists": bool(owner_row),
        "open_invites": int(open_invites or 0),
    })


@enrollment_bp.route("/api/enrollment/create", methods=["POST"])
def api_enrollment_create():
    """Create the owner account (first-boot) or a new member account via invite."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()
    display_name = (data.get("display_name") or username).strip()
    email = (data.get("email") or "").strip().lower() or None
    role = (data.get("role") or "owner").strip().lower()
    invite_token = (data.get("invite") or "").strip()

    if not username or not password:
        return jsonify({"ok": False, "error": "username and password required"}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "password must be at least 8 characters"}), 400

    # Use the shared hasher (utils.password) so this blueprint does not
    # cross-import a sibling blueprint (A.4.1 no-cross-imports rule).
    from utils.password import hash_password as _hash_password

    conn = _db()
    try:
        # Owner role: only allowed when no owner yet.
        if role == "owner":
            try:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM user_profiles WHERE role='owner'"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                existing = 0
            if existing:
                return jsonify({"ok": False, "error": "owner account already exists; use an invite"}), 409
        else:
            row = conn.execute(
                "SELECT role, consumed_at FROM enrollment_invites WHERE token=?",
                (invite_token,),
            ).fetchone()
            if not row or row["consumed_at"] is not None:
                return jsonify({"ok": False, "error": "invalid or used invite"}), 403
            role = row["role"]
            conn.execute(
                "UPDATE enrollment_invites SET consumed_at=? WHERE token=?",
                (time.time(), invite_token),
            )

        try:
            conn.execute(
                """INSERT INTO user_profiles
                   (username, display_name, email, role, password_hash, approved, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, 1, ?)""",
                (username, display_name, email, role, _hash_password(password), time.time()),
            )
        except sqlite3.OperationalError as exc:
            return jsonify({"ok": False, "error": f"schema missing: {exc}"}), 500
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "username": username, "role": role})


@enrollment_bp.route("/api/enrollment/invite", methods=["POST"])
def api_enrollment_invite():
    """Owner issues a new invite token for a co-owner / assistant."""
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "assistant").strip().lower()
    email = (data.get("email") or "").strip().lower() or None
    if role not in {"assistant", "coowner", "guest"}:
        return jsonify({"ok": False, "error": f"role '{role}' not allowed"}), 400
    token = secrets.token_urlsafe(18)
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO enrollment_invites (token, role, email, created_at) VALUES (?, ?, ?, ?)",
            (token, role, email, time.time()),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "token": token, "role": role, "email": email})
