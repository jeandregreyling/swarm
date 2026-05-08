"""core.integration_dashboard — aggregate tile for the Studio
"Integration project" dashboard card (S-737DA6DA1E).

Returns a small, JSON-friendly dict the dashboard widget can render
without further computation.
"""
from __future__ import annotations

from typing import Any, Dict


def dashboard_tile(conn, project_id: str) -> Dict[str, Any]:
    """Return counts + recent activity for *project_id*.

    Shape::

        {
          "project_id": str,
          "name": str,
          "status": str,
          "step_counts": {"total":N, "done":N, "blocked":N, "todo":N},
          "evidence_count": N,
          "recent_evidence": [
              {"step_id":..,"summary":..,"status":..,"created_at":..},
              ...
          ],
        }
    """
    if not project_id:
        return {"ok": False, "error": "project_id required"}

    proj = conn.execute(
        "SELECT project_id, name, status FROM projects WHERE project_id=?",
        (project_id,),
    ).fetchone()
    if not proj:
        return {"ok": False, "error": "not found", "project_id": project_id}

    step_rows = conn.execute(
        "SELECT status, COUNT(*) FROM project_steps WHERE project_id=? "
        "GROUP BY status",
        (project_id,),
    ).fetchall()
    counts = {"total": 0, "done": 0, "blocked": 0, "todo": 0, "skipped": 0}
    for status, n in step_rows:
        counts["total"] += int(n)
        key = (status or "todo").strip().lower()
        if key == "done":
            counts["done"] += int(n)
        elif key == "blocked":
            counts["blocked"] += int(n)
        elif key == "skipped":
            counts["skipped"] += int(n)
        else:
            counts["todo"] += int(n)

    try:
        ev_total = conn.execute(
            "SELECT COUNT(*) FROM project_step_evidence WHERE project_id=?",
            (project_id,),
        ).fetchone()[0]
        recent = [
            {
                "step_id": r[0],
                "summary": r[1] or "",
                "status": r[2] or "",
                "created_at": r[3] or "",
            }
            for r in conn.execute(
                "SELECT step_id, summary, status, created_at "
                "FROM project_step_evidence WHERE project_id=? "
                "ORDER BY id DESC LIMIT 5",
                (project_id,),
            ).fetchall()
        ]
    except Exception:
        ev_total = 0
        recent = []

    return {
        "ok": True,
        "project_id": proj[0],
        "name": proj[1],
        "status": proj[2],
        "step_counts": counts,
        "evidence_count": int(ev_total),
        "recent_evidence": recent,
    }


__all__ = ["dashboard_tile"]
