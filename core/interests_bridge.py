"""core.interests_bridge — small surface for the Tasker UI bridge and
the Studio provenance display.

Stories:
  * S-3A39AD790A — Tasker bridge UI helpers (server-side payload shape)
  * S-AE36796087 — Provenance display helpers

Both functions take a sqlite3 connection so they can be tested in
isolation. The Studio/Tasker callers wire them to the live db via the
usual `utils.db._connection` accessor.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def list_interests_for_tasker(conn, *, limit: int = 50) -> List[Dict[str, Any]]:
    """Return active interests in the shape the Tasker bridge UI wants
    (S-3A39AD790A). Highest-score first.
    """
    rows = conn.execute(
        "SELECT topic, category, score, source, source_agent "
        "FROM user_interests WHERE active=1 "
        "ORDER BY score DESC, topic ASC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [
        {
            "topic": r[0],
            "category": r[1] or "general",
            "score": float(r[2] or 0.0),
            "source": r[3] or "user",
            "source_agent": r[4] or "",
            # Tasker bridge expects a stable slug to use as topic_key
            "topic_key": _slugify(r[0]),
        }
        for r in rows
    ]


def provenance_for(conn, topic: str) -> Optional[Dict[str, Any]]:
    """Return a provenance record for a single interest (S-AE36796087).

    None when the topic isn't in user_interests. Otherwise:
        {topic, source, source_agent, created_at, updated_at,
         age_label, manual: bool, agent_added: bool}
    """
    if not topic:
        return None
    row = conn.execute(
        "SELECT topic, source, source_agent, created_at, updated_at, score, active "
        "FROM user_interests WHERE topic=? LIMIT 1",
        (topic,),
    ).fetchone()
    if not row:
        return None
    source = (row[1] or "user").strip()
    agent = (row[2] or "").strip()
    return {
        "topic": row[0],
        "source": source,
        "source_agent": agent,
        "created_at": row[3] or "",
        "updated_at": row[4] or "",
        "score": float(row[5] or 0.0),
        "active": bool(row[6]),
        "manual": source in ("user", "manual", ""),
        "agent_added": bool(agent),
        "label": _provenance_label(source, agent),
    }


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "/"):
            out.append("_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_-")[:48]


def _provenance_label(source: str, agent: str) -> str:
    if source in ("user", "manual", ""):
        return "Added by you"
    if agent:
        return f"Suggested by {agent}"
    return f"From {source}"


__all__ = ["list_interests_for_tasker", "provenance_for"]
