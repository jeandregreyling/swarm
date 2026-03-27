"""
database.py — Seven's Swarm
Clean version with all needed functions for the REPL.
"""

import sqlite3
import logging
from collections import Counter

logger = logging.getLogger('seven.database')
DB_PATH = '/home/seven/swarm/swarm_memory.db'

AGENT_POOL_MAP = {
    "grok": "memory_grok",
    "llama": "memory_llama",
    "qwen": "memory_qwen",
    "gemma": "memory_gemma",
    "eight": "memory_eight",
    "nine": "memory_nine",
    "librarian": "memory",
    "duck": "memory",
    "sniffles": "memory",
    "ten": "memory_ten"
}

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def initialise_database():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            model TEXT NOT NULL,
            temperature REAL DEFAULT 0.3,
            role TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_grok (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'grok',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 8,
            source TEXT DEFAULT 'session',
            ticket_ref TEXT DEFAULT '',
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_llama (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'llama',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 5,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_qwen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'qwen',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 5,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_gemma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'gemma',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 9,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_eight (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'eight',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_nine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'nine',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS memory_ten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT DEFAULT 'ten',
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            importance INTEGER DEFAULT 7,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sandpit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            operation TEXT NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok',
            reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            event TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    _seed_agents()

def _seed_agents():
    roster = [
        ('grok', 'grok-api', 0.6, 'Ghost Layer Advisor'),
        ('gemma', 'gemma3:latest', 0.3, 'Director'),
        ('llama', 'llama3.2:latest', 0.6, 'Correspondent'),
        ('qwen', 'qwen2.5:latest', 0.7, 'Analyst'),
        ('eight', 'qwen2.5:latest', 0.7, 'SAP specialist'),
        ('nine', 'claude-sonnet-4-6', 0.3, 'System architect'),
        ('ten', 'gemini-1.5-pro', 0.4, 'Engineering Advisor'),
    ]
    conn = get_connection()
    for name, model, temp, role in roster:
        conn.execute(
            "INSERT OR IGNORE INTO agents (name,model,temperature,role) VALUES (?,?,?,?)",
            (name, model, temp, role)
        )
    conn.commit()
    conn.close()

def save_agent_memory(agent_name, subject, content, tags='', importance=5, source='learned'):
    table = AGENT_POOL_MAP.get(agent_name.lower())
    if not table:
        logger.warning(f"No personal pool for agent: {agent_name}")
        return False
    conn = get_connection()
    conn.execute(
        f"INSERT INTO {table} (agent,subject,content,tags,importance,source) VALUES (?,?,?,?,?,?)",
        (agent_name.lower(), subject[:200], content, tags, importance, source)
    )
    conn.commit()
    conn.close()
    return True

def get_activity_log(limit=10):
    conn = get_connection()
    rows = conn.execute("SELECT id, service, event, detail, created_at FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def new_conversation(title, source='email', sender=''):
    """Create a new conversation record. Returns conv_id."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO conversations (title,source,sender) VALUES (?,?,?)",
            (title[:100], source, sender)
        )
        conv_id = cursor.lastrowid
        conn.commit()
        return conv_id
    finally:
        conn.close()

def log_message(conv_id, from_agent, content, to_agent='', message_type='chat', created_at=''):
    """Log a message in a conversation."""
    conn = get_connection()
    try:
        ts = created_at or get_timestamp()
        conn.execute(
            "INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type,created_at) VALUES (?,?,?,?,?,?)",
            (conv_id, from_agent, to_agent, content, message_type, ts)
        )
        conn.commit()
    finally:
        conn.close()

def get_digest_stats():
    conn = get_connection()
    opened = conn.execute("SELECT COUNT(*) FROM tickets WHERE created_at >= datetime('now','-1 day')").fetchone()[0]
    closed = conn.execute("SELECT COUNT(*) FROM tickets WHERE closed_at >= datetime('now','-1 day')").fetchone()[0]
    open_ct = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    duck_yes = 0
    duck_no = 0
    top_tags = []
    conn.close()
    return {
        'opened': opened, 'closed': closed, 'open': open_ct,
        'duck_yes': duck_yes, 'duck_no': duck_no,
        'top_tags': top_tags
    }

if __name__ == '__main__':
    initialise_database()
    print("Database initialised with Grok as Agent 11.")