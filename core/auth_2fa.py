"""core/auth_2fa.py — TOTP 2-factor authentication primitives.

Pure stdlib TOTP (RFC 6238) so the Swarm does not need pyotp. Secrets are
stored in SQLite via `user_2fa` table (created on demand). Each user has at
most one active secret. Enrolment issues a provisioning URI that GitHub /
Google / Authy accept.

This module is designed to be used by :mod:`frontend.blueprints.auth` and any
other blueprint that wants 2FA enforcement. The storage layer is deliberately
minimal — the production DB schema may wrap these primitives with richer audit
columns without rewriting the crypto.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import struct
import time
import urllib.parse
from typing import Optional


ISSUER = os.environ.get("SWARM_2FA_ISSUER", "Swarm")


# ── TOTP primitives ─────────────────────────────────────────────────────────
def _b32_secret(nbytes: int = 20) -> str:
    """Generate a fresh base32 secret."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_now(secret_b32: str, step: int = 30, digits: int = 6, t: Optional[float] = None) -> str:
    t = t if t is not None else time.time()
    return _hotp(secret_b32, int(t // step), digits=digits)


def totp_verify(secret_b32: str, code: str, *, window: int = 1, step: int = 30) -> bool:
    """Verify a TOTP code. ``window=1`` accepts prev/current/next step."""
    code = (code or "").strip()
    if not code.isdigit():
        return False
    now = int(time.time() // step)
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, now + offset), code):
            return True
    return False


def provisioning_uri(username: str, secret_b32: str, issuer: str = ISSUER) -> str:
    label = urllib.parse.quote(f"{issuer}:{username}")
    params = urllib.parse.urlencode({"secret": secret_b32, "issuer": issuer})
    return f"otpauth://totp/{label}?{params}"


# ── Storage ─────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS user_2fa (
    username TEXT PRIMARY KEY,
    secret TEXT NOT NULL,
    verified_at REAL,
    created_at REAL NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    override = os.environ.get("SWARM_2FA_DB")
    if override:
        conn = sqlite3.connect(override)
    else:
        from utils.db._connection import get_connection
        conn = get_connection()
    conn.executescript(SCHEMA)
    return conn


def enroll(username: str) -> dict:
    """Create or replace a pending 2FA enrolment. Returns provisioning data."""
    secret = _b32_secret()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_2fa (username, secret, verified_at, created_at) VALUES (?, ?, NULL, ?)",
            (username, secret, time.time()),
        )
    return {
        "username": username,
        "secret": secret,
        "otpauth_url": provisioning_uri(username, secret),
    }


def verify(username: str, code: str) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT secret FROM user_2fa WHERE username=?", (username,)).fetchone()
        if not row:
            return False
        secret = row[0]
        ok = totp_verify(secret, code)
        if ok:
            conn.execute("UPDATE user_2fa SET verified_at=? WHERE username=?", (time.time(), username))
        return ok


def is_enrolled(username: str, *, verified_only: bool = True) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT verified_at FROM user_2fa WHERE username=?", (username,)).fetchone()
        if not row:
            return False
        if verified_only:
            return row[0] is not None
        return True


def drop(username: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM user_2fa WHERE username=?", (username,))
        return cur.rowcount > 0
