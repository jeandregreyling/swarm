"""core.hive.enrolment — node tokens + handshake helpers.

Enrolment flow:
    1. Operator runs ``mint_token(node_id, label=...)`` on the executive
       (or ``POST /api/hive/enrol``). A 32-byte URL-safe token is stored
       hashed (sha256) in $SWARM_HIVE_TOKENS file.
    2. Operator copies the token + executive URL to the candidate node.
    3. Node POSTs telemetry with header ``X-Hive-Token: <token>``; the
       blueprint verifies via ``verify_token`` before accepting.

Tokens are single-use for first telemetry (binds the node) and then
reused as the long-lived auth header. Revoke with ``revoke_token``.

Storage format (one record per line, JSON):
    {"node_id": "...", "hash": "sha256-hex", "minted_ts": 1777, "label": "..."}

This module is filesystem-backed (no external deps) and threadsafe
within a single process via a module-level lock. Multi-process safety
relies on atomic line-append via os.write.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

DEFAULT_PATH = os.environ.get(
    'SWARM_HIVE_TOKENS',
    str(Path(__file__).resolve().parents[2] / 'swarm_hive_tokens.jsonl'),
)

_LOCK = threading.RLock()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _read_all(path: str = DEFAULT_PATH) -> list[dict]:
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_all(rows: list[dict], path: str = DEFAULT_PATH) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, separators=(',', ':')) + '\n')
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mint_token(node_id: str, *, label: str = '',
               path: str = DEFAULT_PATH) -> str:
    """Create + persist a fresh token for ``node_id``. Returns the
    plaintext token (caller must hand it to the node — we only keep the
    hash).
    """
    if not node_id or not isinstance(node_id, str):
        raise ValueError('node_id required')
    token = secrets.token_urlsafe(32)
    record = {
        'node_id': node_id,
        'hash': _hash(token),
        'minted_ts': int(time.time()),
        'label': label or '',
    }
    with _LOCK:
        rows = _read_all(path)
        # Replace any existing token for this node_id (rotation).
        rows = [r for r in rows if r.get('node_id') != node_id]
        rows.append(record)
        _write_all(rows, path)
    return token


def verify_token(node_id: str, token: str | None,
                 path: str = DEFAULT_PATH) -> bool:
    """Return True iff (node_id, token) matches a stored record."""
    if not node_id or not token:
        return False
    digest = _hash(token)
    with _LOCK:
        for r in _read_all(path):
            if r.get('node_id') == node_id and hmac.compare_digest(
                    r.get('hash', ''), digest):
                return True
    return False


def revoke_token(node_id: str, path: str = DEFAULT_PATH) -> bool:
    """Drop any token bound to ``node_id``. Returns True if a row was
    removed.
    """
    with _LOCK:
        rows = _read_all(path)
        new_rows = [r for r in rows if r.get('node_id') != node_id]
        if len(new_rows) == len(rows):
            return False
        _write_all(new_rows, path)
        return True


def list_tokens(path: str = DEFAULT_PATH) -> list[dict]:
    """List enrolment records (without exposing the hash)."""
    return [
        {'node_id': r.get('node_id'),
         'minted_ts': r.get('minted_ts'),
         'label': r.get('label', '')}
        for r in _read_all(path)
    ]
