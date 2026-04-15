"""
utils.db.tools — Tool build registry CRUD (C.1.2)
═══════════════════════════════════════════════════════════════════════════════
Table: tool_builds
Tracks everything agents build through the governed ALM flow.
"""

import json
import datetime
from ._connection import get_connection


VALID_STATUSES = (
    'scaffolded', 'building', 'validating', 'testing',
    'passed', 'failed', 'registered',
)
VALID_TOOL_TYPES = ('script', 'skill', 'widget', 'cron', 'shell')
VALID_LANGUAGES = ('python', 'javascript', 'shell', 'html')


# ── Build CRUD ────────────────────────────────────────────────────────────

def create_build(tool_name, tool_type='script', *, description='',
                 building_agent='', language='python', proposal_id='',
                 conn=None):
    """Create a new tool build record. Returns the new build id."""
    if tool_type not in VALID_TOOL_TYPES:
        raise ValueError(f"Invalid tool_type {tool_type!r}, must be one of {VALID_TOOL_TYPES}")
    if language not in VALID_LANGUAGES:
        raise ValueError(f"Invalid language {language!r}, must be one of {VALID_LANGUAGES}")
    own = conn is None
    if own:
        conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO tool_builds
               (tool_name, tool_type, description, building_agent, language,
                proposal_id, status)
               VALUES (?, ?, ?, ?, ?, ?, 'scaffolded')""",
            (tool_name, tool_type, description, building_agent, language,
             proposal_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


def get_build(build_id, *, conn=None):
    """Return a build dict or None."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tool_builds WHERE id = ?", (build_id,)
        ).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM tool_builds LIMIT 0").description]
        return dict(zip(cols, row))
    finally:
        if own:
            conn.close()


def update_build(build_id, *, status=None, entry_path=None, test_path=None,
                 test_output=None, proposal_id=None, conn=None):
    """Update mutable fields on a build record."""
    sets, vals = [], []
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status {status!r}")
        sets.append("status = ?")
        vals.append(status)
    if entry_path is not None:
        sets.append("entry_path = ?")
        vals.append(entry_path)
    if test_path is not None:
        sets.append("test_path = ?")
        vals.append(test_path)
    if test_output is not None:
        sets.append("test_output = ?")
        vals.append(test_output)
    if proposal_id is not None:
        sets.append("proposal_id = ?")
        vals.append(proposal_id)
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    vals.append(build_id)
    own = conn is None
    if own:
        conn = get_connection()
    try:
        conn.execute(
            f"UPDATE tool_builds SET {', '.join(sets)} WHERE id = ?",
            vals,
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def list_builds(*, status=None, building_agent=None, limit=50, conn=None):
    """Return recent builds, optionally filtered."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        sql = "SELECT * FROM tool_builds WHERE 1=1"
        params = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if building_agent:
            sql += " AND building_agent = ?"
            params.append(building_agent)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM tool_builds LIMIT 0").description]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        if own:
            conn.close()


def get_build_by_proposal(proposal_id, *, conn=None):
    """Get the build linked to a proposal, or None."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM tool_builds WHERE proposal_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM tool_builds LIMIT 0").description]
        return dict(zip(cols, row))
    finally:
        if own:
            conn.close()
