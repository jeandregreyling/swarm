"""
utils/config_validator.py — Configuration validation & node config (D.4)
═══════════════════════════════════════════════════════════════════════════════
Validates required env vars, DB connectivity, and agent registry.
Provides node-level config overrides stored in node_config table.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

# Required env vars for a functional swarm node
REQUIRED_ENV = [
    'SWARM_ROOT',
]

# Optional but recommended
RECOMMENDED_ENV = [
    'SWARM_ENV',
    'SWARM_NAME',
    'AGENT_API_KEY',
]

# Config defaults
CONFIG_DEFAULTS = {
    'heartbeat_interval': '60',
    'stale_threshold': '300',
    'relay_batch_size': '50',
    'relay_max_age': '3600',
    'rate_limit_per_minute': '60',
    'max_request_size_mb': '1',
}


def validate_config():
    """Run preflight checks on configuration.
    Returns (ok: bool, errors: list[str], warnings: list[str]).
    """
    errors = []
    warnings = []

    # 1. Check required env vars
    for var in REQUIRED_ENV:
        if not os.environ.get(var):
            errors.append(f'Missing required env var: {var}')

    for var in RECOMMENDED_ENV:
        if not os.environ.get(var):
            warnings.append(f'Recommended env var not set: {var}')

    # 2. Check DB connectivity
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
    except Exception as e:
        errors.append(f'Database connection failed: {e}')

    # 3. Check agent registry
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        conn.close()
        if count == 0:
            warnings.append('Agent registry is empty — run setup_node.py')
    except Exception as e:
        warnings.append(f'Agent registry check failed: {e}')

    # 4. Check SWARM_ROOT exists and is writable
    swarm_root = os.environ.get('SWARM_ROOT', '')
    if swarm_root:
        if not os.path.isdir(swarm_root):
            errors.append(f'SWARM_ROOT directory not found: {swarm_root}')
        elif not os.access(swarm_root, os.W_OK):
            errors.append(f'SWARM_ROOT not writable: {swarm_root}')

    ok = len(errors) == 0
    return ok, errors, warnings


# ── Node Config Override (D.4.2) ─────────────────────────────────────────────

def get_config(key, default=None, *, conn=None):
    """Get a config value. Checks: node_config table → env var → default."""
    # Try node_config table first
    try:
        own = conn is None
        if own:
            from utils.db._connection import get_connection
            conn = get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM node_config WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return row[0] if isinstance(row, tuple) else row['value']
        finally:
            if own:
                conn.close()
    except Exception:
        pass  # Table may not exist yet

    # Try env var (uppercase)
    env_val = os.environ.get(key.upper()) or os.environ.get(f'SWARM_{key.upper()}')
    if env_val is not None:
        return env_val

    # Fall back to defaults
    return CONFIG_DEFAULTS.get(key, default)


def set_config(key, value, *, conn=None):
    """Set a config value in node_config table."""
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO node_config (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
               value=excluded.value, updated_at=datetime('now')""",
            (key, str(value))
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def list_config(*, conn=None):
    """List all node config overrides."""
    own = conn is None
    if own:
        from utils.db._connection import get_connection
        conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM node_config ORDER BY key"
        ).fetchall()
        return [{'key': r[0], 'value': r[1], 'updated_at': r[2]}
                if isinstance(r, tuple) else dict(r) for r in rows]
    except Exception:
        return []
    finally:
        if own:
            conn.close()
