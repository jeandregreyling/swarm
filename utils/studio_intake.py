"""Studio intake helpers.

Keeps ALM proposals attached to Fridays Studio projects so work does not drift
into loose queue/proposal rows without project context.
"""
from __future__ import annotations

import re
import time

from utils.db._connection import get_connection


CONTROL_PROJECT_ID = "P-00221285D1"
_PROJECT_ID_RE = re.compile(r"\bP-[A-Z0-9]{10}\b", re.IGNORECASE)


def _ensure_link_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS proposal_projects (
            proposal_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (proposal_id, project_id)
        )"""
    )


def _project_exists(conn, project_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM projects WHERE project_id=? LIMIT 1",
        (project_id,),
    ).fetchone()
    return bool(row)


def choose_project_for_work(
    *,
    title: str = "",
    description: str = "",
    requested_project_id: str = "",
) -> str:
    """Pick the Studio project that should own a new work item.

    Priority:
    1. Explicit requested project id.
    2. Project id mentioned in title/description.
    3. The consolidated control project, when present.
    4. The most recently updated active project.
    """
    text = f"{title or ''}\n{description or ''}"
    with get_connection() as conn:
        requested = str(requested_project_id or "").strip().upper()
        if requested and _project_exists(conn, requested):
            return requested

        match = _PROJECT_ID_RE.search(text)
        if match:
            candidate = match.group(0).upper()
            if _project_exists(conn, candidate):
                return candidate

        if _project_exists(conn, CONTROL_PROJECT_ID):
            return CONTROL_PROJECT_ID

        row = conn.execute(
            """SELECT project_id FROM projects
               WHERE status='active'
               ORDER BY COALESCE(updated_at, created_at, 0) DESC
               LIMIT 1"""
        ).fetchone()
        return str(row["project_id"] if row else "")


def link_proposal_to_project(
    proposal_id: str,
    *,
    title: str = "",
    description: str = "",
    requested_project_id: str = "",
) -> str:
    """Link an ALM proposal to a Studio project and return the project id."""
    proposal = str(proposal_id or "").strip()
    if not proposal:
        return ""
    project_id = choose_project_for_work(
        title=title,
        description=description,
        requested_project_id=requested_project_id,
    )
    if not project_id:
        return ""
    with get_connection() as conn:
        _ensure_link_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO proposal_projects (proposal_id, project_id, created_at) VALUES (?, ?, ?)",
            (proposal[:64], project_id, time.time()),
        )
        conn.commit()
    return project_id
