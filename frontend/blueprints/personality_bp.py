"""personality_bp.py — Agent personality + diary system (Tier 4.4).
Each agent has a personality.md and diary entries stored in DB.
"""
import os
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request
from database import get_connection, log_activity

personality_bp = Blueprint('personality', __name__)

_AGENTS_DIR = Path('/home/seven/swarm/agents')


def _ensure_diary_table():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_diary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            entry TEXT NOT NULL,
            mood TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _personality_path(agent_name: str) -> Path:
    """Return path to agent's personality.md file."""
    safe = agent_name.replace('/', '').replace('..', '').strip().lower()
    return _AGENTS_DIR / safe / 'personality.md'


@personality_bp.route('/api/agents/<agent_name>/personality', methods=['GET'])
def get_personality(agent_name):
    """Read an agent's personality file."""
    path = _personality_path(agent_name)
    if not path.is_file():
        return jsonify({'ok': True, 'agent': agent_name, 'personality': '', 'exists': False})
    content = path.read_text(encoding='utf-8', errors='replace')
    return jsonify({'ok': True, 'agent': agent_name, 'personality': content, 'exists': True})


@personality_bp.route('/api/agents/<agent_name>/personality', methods=['PUT'])
def set_personality(agent_name):
    """Write/update an agent's personality file."""
    data = request.get_json(force=True, silent=True) or {}
    content = str(data.get('personality', '')).strip()
    if not content:
        return jsonify({'ok': False, 'error': 'personality content required'}), 400

    path = _personality_path(agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    log_activity('personality', 'update', f'{agent_name} personality updated ({len(content)} chars)')
    return jsonify({'ok': True, 'agent': agent_name, 'size': len(content)})


@personality_bp.route('/api/agents/<agent_name>/diary', methods=['GET'])
def get_diary(agent_name):
    """Return diary entries for an agent."""
    _ensure_diary_table()
    limit = min(int(request.args.get('limit', 30)), 100)
    safe = agent_name.strip().lower()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, entry, mood, created_at FROM agent_diary WHERE agent_name=? ORDER BY id DESC LIMIT ?",
        (safe, limit)
    ).fetchall()
    conn.close()
    return jsonify({'ok': True, 'agent': safe, 'entries': [dict(r) for r in rows], 'count': len(rows)})


@personality_bp.route('/api/agents/<agent_name>/diary', methods=['POST'])
def add_diary_entry(agent_name):
    """Add a diary entry for an agent."""
    _ensure_diary_table()
    data = request.get_json(force=True, silent=True) or {}
    entry = str(data.get('entry', '')).strip()
    mood = str(data.get('mood', '')).strip()[:20]
    if not entry:
        return jsonify({'ok': False, 'error': 'entry required'}), 400

    safe = agent_name.strip().lower()
    conn = get_connection()
    conn.execute(
        "INSERT INTO agent_diary (agent_name, entry, mood) VALUES (?, ?, ?)",
        (safe, entry[:2000], mood)
    )
    conn.commit()
    conn.close()
    log_activity('personality', 'diary_entry', f'{safe}: {entry[:60]}')
    return jsonify({'ok': True, 'agent': safe})
