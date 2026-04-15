"""
db._connection — Shared database primitives.

DB_PATH resolves via SWARM_DB_PATH env var so DEV/UAT worktrees can point
to the shared production database rather than creating isolated copies.
Default auto-detects from SWARM_ROOT or script location.

A.4.3: get_service_connection(service) supports per-service DB paths
via SWARM_DB_{SERVICE}_PATH env vars.  Default: shared DB.
"""
import os
import sqlite3
import logging

logger = logging.getLogger('seven.database')

# SWARM_ROOT: auto-detect from this file's location (utils/db/_connection.py → root)
SWARM_ROOT = os.environ.get(
    'SWARM_ROOT',
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

DB_PATH = os.environ.get('SWARM_DB_PATH', os.path.join(SWARM_ROOT, 'swarm_memory.db'))

# Global mapping to ensure consistency across the swarm
AGENT_POOL_MAP = {
    'llama': 'memory_llama', 'qwen': 'memory_qwen',
    'mistral': 'memory_mistral',
    'gemma': 'memory_gemma', 'eight': 'memory_eight',
    'nine': 'memory_nine', 'librarian': 'memory',
    'duck': 'memory', 'sniffles': 'memory',
    'ten': 'memory_ten', 'twelve': 'memory_twelve',
    'eleven': 'memory_grok', 'grok': 'memory_grok',
    'thirteen': 'memory_thirteen',
    'scholar': 'memory_scholar', 'seeker': 'memory_seeker',
}


def _make_connection(db_path):
    """Create a SQLite connection with standard PRAGMAs."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_connection():
    """Return a connection to the shared (default) database."""
    return _make_connection(DB_PATH)


def get_service_connection(service_name):
    """Return a connection for *service_name*.

    Checks env var ``SWARM_DB_{SERVICE}_PATH`` first. Falls back to the
    shared DB_PATH if no override is set.  This lets each future service
    point to its own DB file without changing call sites.

    Example env:
        SWARM_DB_CHAT_PATH=/data/chat.db
        SWARM_DB_GOVERNANCE_PATH=/data/governance.db
    """
    env_key = f'SWARM_DB_{service_name.upper()}_PATH'
    path = os.environ.get(env_key, DB_PATH)
    return _make_connection(path)
