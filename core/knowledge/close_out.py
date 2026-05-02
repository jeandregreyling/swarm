"""core.knowledge.close_out — ALM close-out report builder.

V7C-R17 / A16 refinement. For a given project, walk every step, find the
locked pytest file(s), find the most recent test-run per case, and return a
single auditable report. Used by:

    * ``/api/knowledge/projects/<pid>/close-out`` (R17)
    * ``/api/knowledge/steps/<sid>/probe``        (A16 — run one step's locked
      tests on demand and return structured verdicts).

Design rules:
    * File resolution is deterministic and declared: a step with
      ``step_id = 'S-XXXXXXXXXX'`` looks for any test file in ``tests/``
      whose source contains that exact id. This mirrors what we've been
      doing by hand all session and makes it self-checking.
    * The probe runs pytest as a subprocess with ``--tb=short`` and a
      timeout so a wedged test cannot hang the API.
    * Output is JSON-safe.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"

_STEP_ID_RE = re.compile(r"S-[0-9A-F]{10}")


def _index_tests_by_step_id() -> Dict[str, List[str]]:
    """Scan ``tests/`` once and return ``{step_id: [file, ...]}``."""
    idx: Dict[str, List[str]] = {}
    if not TESTS_DIR.exists():
        return idx
    for p in sorted(TESTS_DIR.glob("test_*.py")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for sid in set(_STEP_ID_RE.findall(text)):
            idx.setdefault(sid, []).append(str(p.relative_to(REPO_ROOT)))
    return idx


def _latest_run_for_case(case_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent test_runs row for a given case, or None."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
    except Exception:
        return None
    try:
        try:
            row = conn.execute(
                "SELECT run_id, status, stdout_tail, started_at "
                "FROM test_runs WHERE case_id=? "
                "ORDER BY started_at DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        if hasattr(row, "keys"):
            return {"run_id": row["run_id"], "status": row["status"],
                    "stdout_tail": row["stdout_tail"], "started_at": row["started_at"]}
        return {"run_id": row[0], "status": row[1],
                "stdout_tail": row[2], "started_at": row[3]}
    finally:
        conn.close()


def _latest_run_for_step(step_id: str) -> Optional[Dict[str, Any]]:
    """Return the most recent test_runs row keyed by step_id, or None."""
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
    except Exception:
        return None
    try:
        try:
            row = conn.execute(
                "SELECT run_id, status, stdout_tail, started_at "
                "FROM test_runs WHERE step_id=? "
                "ORDER BY started_at DESC LIMIT 1",
                (step_id,),
            ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        if hasattr(row, "keys"):
            return {"run_id": row["run_id"], "status": row["status"],
                    "stdout_tail": row["stdout_tail"], "started_at": row["started_at"]}
        return {"run_id": row[0], "status": row[1],
                "stdout_tail": row[2], "started_at": row[3]}
    finally:
        conn.close()


def _cases_for_step(step_id: str) -> List[Dict[str, Any]]:
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
    except Exception:
        return []
    try:
        try:
            rows = conn.execute(
                "SELECT case_id, title, status FROM project_test_cases WHERE step_id=?",
                (step_id,),
            ).fetchall()
        except Exception:
            return []
        return [dict(r) if hasattr(r, "keys") else
                {"case_id": r[0], "title": r[1], "status": r[2]}
                for r in rows]
    finally:
        conn.close()


def build_report(project_id: str) -> Dict[str, Any]:
    """Return the full close-out report for a project.

    Shape::

        {
          "ok": True,
          "project_id": "P-...",
          "totals": {"steps": N, "done": n, "partial": n, "open": n, ...},
          "steps": [
            {
              "step_id": "S-...",
              "title": "...",
              "status": "done" | "partial" | ...,
              "test_files": ["tests/test_v7c_r7_...", ...],
              "cases": [{"case_id": "C-...", "last_run": {...}}, ...],
              "verdict": "green" | "red" | "partial" | "unverified"
            },
            ...
          ]
        }
    """
    from core.knowledge import projects as _p
    proj = _p.get_project(project_id)
    if not proj:
        return {"ok": False, "error": "project not found"}
    # get_project() returns {'project': {...}, 'steps': [...], ...}; unwrap
    # the project header so downstream consumers (closeout markdown export,
    # cards, audit) can read project_name without re-fetching.
    proj_header = proj.get('project') if isinstance(proj.get('project'), dict) else proj
    steps = _p.list_steps(project_id)
    test_idx = _index_tests_by_step_id()

    totals: Dict[str, int] = {}
    out_steps: List[Dict[str, Any]] = []
    for s in steps:
        sid = s["step_id"]
        status = s.get("status") or "todo"
        totals[status] = totals.get(status, 0) + 1

        test_files = test_idx.get(sid, [])
        cases = _cases_for_step(sid)
        for c in cases:
            c["last_run"] = _latest_run_for_case(c["case_id"])
        step_last_run = _latest_run_for_step(sid)

        verdict = _verdict(status, test_files, cases, step_last_run)
        out_steps.append({
            "step_id": sid,
            "title": s.get("title"),
            "status": status,
            "owner": s.get("owner"),
            "test_files": test_files,
            "cases": cases,
            "last_run": step_last_run,
            "verdict": verdict,
        })

    return {
        "ok": True,
        "project_id": project_id,
        "project_name": proj_header.get("name"),
        "totals": {
            "steps": len(steps),
            **{k: totals.get(k, 0)
               for k in ("todo", "doing", "blocked", "partial", "done", "skipped")},
        },
        "steps": out_steps,
        "generated_at": time.time(),
    }


def _verdict(
    status: str,
    test_files: List[str],
    cases: List[Dict[str, Any]],
    step_last_run: Optional[Dict[str, Any]] = None,
) -> str:
    """Reduce (status, files, last runs) to a single verdict string."""
    if status == "done":
        if not test_files:
            return "unverified"
        # Collect latest statuses from per-case runs plus the step-level run.
        run_statuses = {
            (c.get("last_run") or {}).get("status") for c in cases
        }
        if step_last_run:
            run_statuses.add(step_last_run.get("status"))
        run_statuses.discard(None)
        if not run_statuses:
            return "unverified"
        if run_statuses <= {"pass", "passed"}:
            return "green"
        if {"fail", "failed", "error"} & run_statuses:
            return "red"
        return "partial"
    if status == "partial":
        return "partial"
    if status in ("todo", "doing"):
        return "open"
    if status == "blocked":
        return "blocked"
    if status == "skipped":
        return "skipped"
    return "unknown"


# ── Live probe: run the step's locked pytest file(s) on demand ─────────

def run_step_probe(step_id: str, *, timeout: float = 60.0) -> Dict[str, Any]:
    """Execute the step's locked pytest file(s) and return a parsed report.

    Mirrors A16 intent: the harness replays a step's regression evidence
    rather than trusting a stale DB row. Never raises — on timeout or
    pytest crash, returns ``ok=False`` with a ``reason``.
    """
    test_idx = _index_tests_by_step_id()
    files = test_idx.get(step_id, [])
    if not files:
        return {
            "ok": False,
            "step_id": step_id,
            "reason": "no test file carries this step_id",
            "files": [],
        }
    started = time.time()
    # Don't add -q here: pyproject already sets `-x -q --tb=short`, and
    # stacking another -q becomes -qq which suppresses the summary line
    # we need to parse ("N passed in ...").
    cmd = [sys.executable, "-m", "pytest", *files, "--tb=short",
           "-p", "no:cacheprovider"]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "step_id": step_id,
                "reason": f"timeout after {timeout}s", "files": files}
    except Exception as e:
        return {"ok": False, "step_id": step_id,
                "reason": f"pytest launch failed: {e}", "files": files}

    tail = "\n".join((r.stdout or "").splitlines()[-30:])
    passed = failed = errors = 0
    m = re.search(r"(\d+)\s+passed", r.stdout or "")
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", r.stdout or "")
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+)\s+error", r.stdout or "")
    if m:
        errors = int(m.group(1))

    verdict = "green" if (r.returncode == 0 and failed == 0 and errors == 0) else "red"
    rep = {
        "ok": True,
        "step_id": step_id,
        "files": files,
        "return_code": r.returncode,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "verdict": verdict,
        "duration_s": round(time.time() - started, 2),
        "tail": tail,
    }

    # Record an audit row in test_runs so the close-out report sees real
    # evidence instead of "unverified". Best-effort — never fail the probe.
    try:
        _record_probe_run(step_id, files, r.returncode, tail, passed, failed, errors,
                          started_at=started, ended_at=time.time())
    except Exception:
        pass

    return rep


def _record_probe_run(step_id: str, files: List[str], return_code: int,
                      tail: str, passed: int, failed: int, errors: int,
                      *, started_at: float, ended_at: float) -> None:
    """Write a minimal test_runs row tagged to this step."""
    from utils.db._connection import get_connection
    # Ensure schema exists (runs table + project columns).
    try:
        from core.knowledge import test_runs as _tr
        _tr._ensure_schema()
    except Exception:
        pass
    conn = get_connection()
    try:
        run_id = "R-" + uuid.uuid4().hex[:12].upper()
        status = "pass" if (return_code == 0 and failed == 0 and errors == 0) else "fail"
        duration_ms = int(max(0.0, ended_at - started_at) * 1000)
        conn.execute(
            "INSERT INTO test_runs (run_id, script_id, status, started_at, ended_at, "
            "duration_ms, exit_code, stdout_tail, command, triggered_by, step_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id,
             f"step-probe:{step_id}",
             status,
             started_at,
             ended_at,
             duration_ms,
             int(return_code),
             tail[:8 * 1024],
             f"pytest {' '.join(files)}",
             "step-probe",
             step_id),
        )
        conn.commit()
    finally:
        conn.close()


_VERDICT_BADGE = {
    "green": "✅",
    "red": "❌",
    "partial": "🟡",
    "unverified": "⚪",
}


def render_markdown(report: Dict[str, Any]) -> str:
    """Render a build_report() payload as a human-readable markdown document.

    S-4DB57C3A23 — closeout markdown export. Used by the API endpoint
    ``GET /api/knowledge/projects/<pid>/close-out?format=md`` and by
    ad-hoc CLI exporters.
    """
    if not report.get("ok"):
        return f"# Close-out export failed\n\nError: {report.get('error', 'unknown')}\n"

    lines: List[str] = []
    name = report.get("project_name") or report.get("project_id")
    lines.append(f"# Close-out — {name}")
    lines.append("")
    lines.append(f"**Project ID:** `{report.get('project_id')}`")
    gen = report.get("generated_at")
    if gen:
        try:
            from datetime import datetime, timezone
            stamp = datetime.fromtimestamp(float(gen), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            lines.append(f"**Generated:** {stamp}")
        except Exception:
            pass
    lines.append("")

    totals = report.get("totals") or {}
    if totals:
        lines.append("## Totals")
        lines.append("")
        lines.append("| Bucket | Count |")
        lines.append("|---|---:|")
        for key in ("steps", "done", "partial", "doing", "blocked", "todo", "skipped"):
            if key in totals:
                lines.append(f"| {key} | {totals[key]} |")
        lines.append("")

    steps = report.get("steps") or []
    lines.append(f"## Steps ({len(steps)})")
    lines.append("")
    for s in steps:
        verdict = s.get("verdict") or "unverified"
        badge = _VERDICT_BADGE.get(verdict, "⚪")
        title = s.get("title") or "(untitled)"
        lines.append(f"### {badge} {s.get('step_id')} — {title}")
        lines.append("")
        lines.append(f"- **Status:** `{s.get('status') or 'todo'}`")
        lines.append(f"- **Verdict:** `{verdict}`")
        owner = s.get("owner")
        if owner:
            lines.append(f"- **Owner:** {owner}")
        tfiles = s.get("test_files") or []
        if tfiles:
            lines.append(f"- **Test files ({len(tfiles)}):**")
            for tf in tfiles:
                lines.append(f"  - `{tf}`")
        cases = s.get("cases") or []
        if cases:
            lines.append(f"- **Cases ({len(cases)}):**")
            for c in cases:
                last = c.get("last_run") or {}
                last_status = last.get("status") or "—"
                lines.append(f"  - `{c.get('case_id')}` · {c.get('title') or ''} · last: {last_status}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["build_report", "run_step_probe", "render_markdown"]
