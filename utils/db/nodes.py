"""
utils/db/nodes.py — Node registration CRUD (A.4.5)
═══════════════════════════════════════════════════════
Tables: swarm_nodes
"""

import json
import hashlib
import logging
import datetime
import uuid

from ._connection import get_connection

logger = logging.getLogger(__name__)

VALID_ROLES = {'owner', 'contributor', 'viewer'}


def _hash_key(api_key):
    """SHA-256 hash of an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_local_node_id():
    """Return a stable node_id for this machine (based on DB_PATH hash)."""
    from ._connection import DB_PATH
    return hashlib.sha256(DB_PATH.encode()).hexdigest()[:16]


def register_node(name, url, api_key, *, role='contributor',
                  agents=None, capabilities=None, conn=None):
    """Register a new node or update an existing one. Returns the node_id."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        if role not in VALID_ROLES:
            raise ValueError(f'Invalid role {role!r}. Must be one of {VALID_ROLES}')
        node_id = hashlib.sha256(f'{name}:{url}'.encode()).hexdigest()[:16]
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        agents_json = json.dumps(agents or [])
        caps_json = json.dumps(capabilities or [])
        key_hash = _hash_key(api_key)
        conn.execute(
            """INSERT INTO swarm_nodes
               (node_id, name, url, api_key_hash, role, agents_json, capabilities,
                registered_at, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET
                 url=excluded.url, api_key_hash=excluded.api_key_hash,
                 role=excluded.role, agents_json=excluded.agents_json,
                 capabilities=excluded.capabilities, last_seen=excluded.last_seen""",
            (node_id, name, url, key_hash, role, agents_json, caps_json, now, now)
        )
        if own:
            conn.commit()
        logger.info(f'[Nodes] registered node {node_id} ({name} @ {url})')
        return node_id
    finally:
        if own:
            conn.close()


def get_node(node_id, *, conn=None):
    """Look up a node by id. Returns dict or None."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            'SELECT * FROM swarm_nodes WHERE node_id=?', (node_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if own:
            conn.close()


def list_nodes(*, conn=None):
    """Return all registered nodes."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT * FROM swarm_nodes ORDER BY registered_at'
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def touch_node(node_id, *, conn=None):
    """Update last_seen timestamp for a node (heartbeat)."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            'UPDATE swarm_nodes SET last_seen=? WHERE node_id=?',
            (now, node_id)
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def verify_api_key(node_id, api_key, *, conn=None):
    """Check if the supplied api_key matches the stored hash."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            'SELECT api_key_hash FROM swarm_nodes WHERE node_id=?', (node_id,)
        ).fetchone()
        if not row:
            return False
        return row['api_key_hash'] == _hash_key(api_key)
    finally:
        if own:
            conn.close()


def remove_node(node_id, *, conn=None):
    """Delete a node from the registry."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        conn.execute('DELETE FROM swarm_nodes WHERE node_id=?', (node_id,))
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
