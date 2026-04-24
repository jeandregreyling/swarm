"""utils.password — shared password hashing helpers.

Extracted from ``frontend.blueprints.login_bp`` so sibling blueprints
(e.g. ``enrollment``) can reuse PBKDF2-SHA256 hashing without
cross-importing another blueprint module (A.4.1 constraint).
"""
from __future__ import annotations

import hashlib
import secrets

__all__ = ["hash_password", "verify_password"]


def hash_password(password: str, salt: str | None = None) -> str:
    """PBKDF2-SHA256 hash with per-user salt. Returns ``'salt:hash'``."""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations=260000
    ).hex()
    return f"{salt}:{h}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against a stored ``'salt:hash'`` value."""
    if not stored_hash or ":" not in stored_hash:
        return False
    salt, _ = stored_hash.split(":", 1)
    return hash_password(password, salt) == stored_hash
