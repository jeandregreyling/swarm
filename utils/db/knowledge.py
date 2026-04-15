"""
utils/db/knowledge.py — Shared swarm knowledge base CRUD + event broadcasts (A.3)
═══════════════════════════════════════════════════════════════════════════════════
Tables: swarm_knowledge, swarm_events, swarm_event_acks
"""

import json
import logging
import datetime

from ._connection import get_connection

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {'lesson', 'decision', 'fact', 'pattern', 'warning'}


# ── Knowledge CRUD ─────────────────────────────────────────────────────────────

def write_knowledge(key, content, source_agent, *,
                    source_proposal_id='', category='fact',
                    importance=5, conn=None):
    """Insert a new entry into swarm_knowledge. Returns the new row id."""
    if category not in VALID_CATEGORIES:
        raise ValueError(f'Invalid category {category!r}. Must be one of {VALID_CATEGORIES}')
    own = conn is None
    if own:
        conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
        cur = conn.execute(
            """INSERT INTO swarm_knowledge
               (key, content, source_agent, source_proposal_id, category, importance, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, content, source_agent, source_proposal_id, category, importance, now, now)
        )
        row_id = cur.lastrowid
        if own:
            conn.commit()
        # Broadcast a knowledge.new event (A.3.4)
        _emit_event('knowledge.new', {
            'knowledge_id': row_id,
            'key': key,
            'category': category,
            'source_agent': source_agent,
        }, source_agent, conn=conn)
        if own:
            conn.commit()
        return row_id
    finally:
        if own:
            conn.close()


def search_knowledge(query, *, category=None, limit=10, conn=None):
    """Search swarm_knowledge by keyword (LIKE). Optional category filter."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        sql = "SELECT * FROM swarm_knowledge WHERE (key LIKE ? OR content LIKE ?)"
        params = [f'%{query}%', f'%{query}%']
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_knowledge_by_proposal(proposal_id, *, conn=None):
    """Get all knowledge entries linked to a specific proposal."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM swarm_knowledge WHERE source_proposal_id = ? ORDER BY created_at",
            (proposal_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


# ── Event Broadcast (A.3.4) ───────────────────────────────────────────────────

def _emit_event(event_type, payload, source_agent, *, conn=None):
    """Write a new event to swarm_events."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        payload_str = json.dumps(payload) if isinstance(payload, dict) else str(payload)
        conn.execute(
            "INSERT INTO swarm_events (event_type, payload, source_agent) VALUES (?, ?, ?)",
            (event_type, payload_str, source_agent)
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def emit_event(event_type, payload, source_agent, *, conn=None):
    """Public wrapper for broadcasting events."""
    _emit_event(event_type, payload, source_agent, conn=conn)


def get_unacked_events(agent_name, *, event_type=None, limit=20, conn=None):
    """Get events not yet acknowledged by this agent. Newest first."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        sql = """SELECT e.* FROM swarm_events e
                 LEFT JOIN swarm_event_acks a
                   ON e.id = a.event_id AND a.agent = ?
                 WHERE a.event_id IS NULL"""
        params = [agent_name]
        if event_type:
            sql += " AND e.event_type = ?"
            params.append(event_type)
        sql += " ORDER BY e.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def ack_event(event_id, agent_name, *, conn=None):
    """Mark an event as consumed by an agent."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO swarm_event_acks (event_id, agent) VALUES (?, ?)",
            (event_id, agent_name)
        )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def ack_all_events(agent_name, event_ids, *, conn=None):
    """Bulk-ack multiple events for an agent."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        for eid in event_ids:
            conn.execute(
                "INSERT OR IGNORE INTO swarm_event_acks (event_id, agent) VALUES (?, ?)",
                (eid, agent_name)
            )
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()
