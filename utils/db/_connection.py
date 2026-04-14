"""
db._connection — Shared database primitives.

DB_PATH resolves via SWARM_DB_PATH env var so DEV/UAT worktrees can point
to the shared production database rather than creating isolated copies.
Default is /home/seven/swarm/swarm_memory.db (the canonical location).
"""
import os
import sqlite3
import logging

logger = logging.getLogger('seven.database')
DB_PATH = os.environ.get('SWARM_DB_PATH', '/home/seven/swarm/swarm_memory.db')

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

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
