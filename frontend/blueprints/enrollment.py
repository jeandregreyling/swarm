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
    # Y.56: type-check before .strip() (Y.50 class).
    for col in ("username", "password", "display_name", "email", "role", "invite"):
        v = data.get(col)
        if v is not None and not isinstance(v, str):
            return jsonify({"ok": False, "error": f"{col} must be a string"}), 400
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


@enrollment_bp.route("/api/enrollment/invite", methods=["GET", "POST"])
def api_enrollment_invite():
    """Issue or list invite tokens for non-owner enrolment.

    POST {"role": "co_owner"|"assistant"|"member", "email": optional}
    GET  → list of open (un-consumed) invites.

    Y.52: filling the gap that was advertised by /api/enrollment/create
    (which only consumed tokens). Owner must already exist before invites
    can be issued; otherwise first-boot bootstrap is bypassed.
    """
    conn = _db()
    try:
        try:
            owner_exists = conn.execute(
                "SELECT 1 FROM user_profiles WHERE role='owner' LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            owner_exists = None

        if request.method == "GET":
            try:
                rows = conn.execute(
                    "SELECT token, role, email, created_at, consumed_at "
                    "FROM enrollment_invites ORDER BY created_at DESC LIMIT 50"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            invites = [
                {
                    "token": r["token"],
                    "role": r["role"],
                    "email": r["email"],
                    "created_at": r["created_at"],
                    "consumed": r["consumed_at"] is not None,
                }
                for r in rows
            ]
            return jsonify({"ok": True, "invites": invites, "count": len(invites)})

        # POST → create invite
        if not owner_exists:
            return jsonify({"ok": False, "error": "owner account must exist before issuing invites"}), 409

        data = request.get_json(silent=True) or {}
        raw_role = data.get("role")
        if not isinstance(raw_role, str):
            return jsonify({"ok": False, "error": "role must be a string"}), 400
        role = raw_role.strip().lower()
        _ALLOWED_INVITE_ROLES = {"co_owner", "assistant", "member"}
        if role not in _ALLOWED_INVITE_ROLES:
            return jsonify({
                "ok": False,
                "error": f"role must be one of {sorted(_ALLOWED_INVITE_ROLES)}",
            }), 400

        raw_email = data.get("email")
        if raw_email is not None and not isinstance(raw_email, str):
            return jsonify({"ok": False, "error": "email must be a string"}), 400
        email: Optional[str] = (raw_email or "").strip().lower() or None
        if email and ("@" not in email or len(email) > 254):
            return jsonify({"ok": False, "error": "invalid email"}), 400

        token = secrets.token_urlsafe(24)
        conn.execute(
            "INSERT INTO enrollment_invites (token, role, email, created_at) VALUES (?, ?, ?, ?)",
            (token, role, email, time.time()),
        )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "token": token, "role": role, "email": email})


# ── MD-FEATURE-2F07F65F10F3 — system-email linkage ──────────────────────
# When an enrolled user's email address matches a config-managed system
# account (utils/config.SEVEN_EMAIL etc.) or an existing runtime registry
# entry, we surface the linkage so the Email tile and inbox routing can
# treat that user's mailbox as the canonical system mailbox. This is a
# read-only probe — it does not mutate either side; the registry stays
# the source of truth for accounts.

def _system_email_pool() -> set[str]:
    pool: set[str] = set()
    try:
        from utils import config as _cfg
        for attr in ("SEVEN_EMAIL", "NINE_EMAIL", "GHOST_EMAIL", "GMAIL_ADDRESS"):
            val = getattr(_cfg, attr, None)
            if isinstance(val, str) and "@" in val:
                pool.add(val.strip().lower())
        bulk = getattr(_cfg, "_EMAIL_ACCOUNTS", None) or []
        for v in bulk:
            if isinstance(v, str) and "@" in v:
                pool.add(v.strip().lower())
    except Exception:
        pass
    return pool


@enrollment_bp.route("/api/enrollment/email-link/<path:username>")
def api_enrollment_email_link(username: str):
    """Return whether the given user's email matches a system account."""
    username = (username or "").strip().lower()
    conn = _db()
    try:
        try:
            row = conn.execute(
                "SELECT username, email, role FROM user_profiles WHERE username=?",
                (username,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        runtime_emails: set[str] = set()
        try:
            for r in conn.execute("SELECT email FROM settings_email_accounts").fetchall():
                if r and r[0]:
                    runtime_emails.add(str(r[0]).strip().lower())
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()
    if not row:
        return jsonify({"ok": False, "error": "user not found"}), 404
    email = (row["email"] or "").strip().lower()
    pool_config = _system_email_pool()
    linked = bool(email and (email in pool_config or email in runtime_emails))
    return jsonify({
        "ok": True,
        "username": row["username"],
        "email": email,
        "linked": linked,
        "source": "config" if email in pool_config else ("runtime" if email in runtime_emails else None),
        "role": row["role"],
    })


# Bug fix 2026-05-03: an orphan second copy of `api_enrollment_invite`
# (no @route decorator) was redefining the symbol with stale role
# validation ({assistant, coowner, guest} vs the live route's
# {co_owner, assistant, member}). The orphan never served traffic but
# its presence was confusing — and any future code that called the
# function by name would have hit the wrong validation. Removed.
