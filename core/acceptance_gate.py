"""core.acceptance_gate — final acceptance check for a project.

S-6189B79E2C — closing a project should require:
  1. All steps are done or skipped
  2. At least one evidence row OR a non-empty test_files entry per
     done step (skipped steps exempt)
  3. Project's residual risk fields surfaced for any step that left
     residual_risk

Returns a structured report so the Studio "Close project" button can
display blockers before the user clicks confirm.
"""
from __future__ import annotations

from typing import Any, Dict, List


def evaluate(conn, project_id: str) -> Dict[str, Any]:
    """Run the gate. Returns:

        {
          "ok": bool,                # True when project can close
          "project_id": str,
          "blockers": [str, ...],    # human-readable
          "warnings": [str, ...],    # non-blocking residual risks
          "step_summary": {"total":N,"done":N,"skipped":N,"open":N},
        }
    """
    if not project_id:
        return {"ok": False, "blockers": ["project_id required"],
                "warnings": [], "step_summary": {}}

    proj = conn.execute(
        "SELECT project_id, name, status FROM projects WHERE project_id=?",
        (project_id,),
    ).fetchone()
    if not proj:
        return {"ok": False, "project_id": project_id,
                "blockers": ["project not found"], "warnings": [],
                "step_summary": {}}

    rows = conn.execute(
        "SELECT step_id, title, status, "
        "       COALESCE(test_files,''), COALESCE(residual_risk,'') "
        "FROM project_steps WHERE project_id=?",
        (project_id,),
    ).fetchall()

    summary = {"total": len(rows), "done": 0, "skipped": 0, "open": 0}
    blockers: List[str] = []
    warnings: List[str] = []

    # Pre-load evidence presence in one query (best-effort).
    evidence_steps = set()
    try:
        for (sid,) in conn.execute(
            "SELECT DISTINCT step_id FROM project_step_evidence WHERE project_id=?",
            (project_id,),
        ).fetchall():
            evidence_steps.add(sid)
    except Exception:
        pass

    for sid, title, status, test_files, residual in rows:
        s = (status or "").strip().lower()
        if s == "done":
            summary["done"] += 1
            has_test = bool((test_files or "").strip())
            has_evidence = sid in evidence_steps
            if not (has_test or has_evidence):
                blockers.append(
                    f"{sid} '{title}' is done but has no test_files "
                    "and no evidence row"
                )
            if (residual or "").strip():
                warnings.append(
                    f"{sid} residual risk: {residual.strip()[:120]}"
                )
        elif s == "skipped":
            summary["skipped"] += 1
        else:
            summary["open"] += 1
            blockers.append(f"{sid} '{title}' is still {s or 'todo'}")

    return {
        "ok": not blockers,
        "project_id": project_id,
        "name": proj[1],
        "current_status": proj[2],
        "blockers": blockers,
        "warnings": warnings,
        "step_summary": summary,
    }


__all__ = ["evaluate"]
