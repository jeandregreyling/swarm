"""
utils.db.node_skills — Federated skill registry CRUD (D.2)
═══════════════════════════════════════════════════════════════════════════════
Table: node_skills
Tracks which skills are available on which nodes for cross-node routing.
"""

from ._connection import get_connection


def upsert_node_skills(node_id, skills, *, conn=None):
    """Insert or update skills for a node. skills = list of dicts with
    skill_name, trust_level, description."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        for s in skills:
            conn.execute(
                """INSERT INTO node_skills (node_id, skill_name, trust_level,
                   description, available, last_seen)
                   VALUES (?, ?, ?, ?, 1, datetime('now'))
                   ON CONFLICT(node_id, skill_name) DO UPDATE SET
                   trust_level=excluded.trust_level,
                   description=excluded.description,
                   available=1, last_seen=datetime('now')""",
                (node_id, s.get('skill_name', ''),
                 s.get('trust_level', 0), s.get('description', '')),
            )
        conn.commit()
    finally:
        if own:
            conn.close()


def find_skill_node(skill_name, *, conn=None):
    """Find a node that has the given skill available.
    Returns dict with node_id, url, trust_level or None."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            """SELECT ns.node_id, ns.trust_level, sn.url
               FROM node_skills ns
               JOIN swarm_nodes sn ON sn.node_id = ns.node_id
               WHERE ns.skill_name = ? AND ns.available = 1
               ORDER BY ns.last_seen DESC LIMIT 1""",
            (skill_name,)
        ).fetchone()
        if row is None:
            return None
        return {
            'node_id': row['node_id'] if hasattr(row, 'keys') else row[0],
            'trust_level': row['trust_level'] if hasattr(row, 'keys') else row[1],
            'url': row['url'] if hasattr(row, 'keys') else row[2],
        }
    finally:
        if own:
            conn.close()


def list_node_skills(node_id=None, *, conn=None):
    """List skills, optionally filtered by node_id."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        if node_id:
            rows = conn.execute(
                "SELECT * FROM node_skills WHERE node_id = ? AND available = 1 "
                "ORDER BY skill_name", (node_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM node_skills WHERE available = 1 "
                "ORDER BY node_id, skill_name"
            ).fetchall()
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM node_skills LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        if own:
            conn.close()


def mark_stale(node_id, *, conn=None):
    """Mark all skills from a node as unavailable (node went stale)."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        conn.execute(
            "UPDATE node_skills SET available = 0 WHERE node_id = ?",
            (node_id,)
        )
        conn.commit()
    finally:
        if own:
            conn.close()
