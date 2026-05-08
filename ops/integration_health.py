"""ops/integration_health.py — Concise integration health report.

S-C67446BD44 (P-00221285D1 PACKET-05). One-shot CLI that prints a
single-screen status of swarm integrations. Designed to be safe to run
on a hot box: no writes, short timeouts, no exception leaks.

Sections:
  * DB hygiene       — duplicate scheduled_tasks, NULL next_run on
                       enabled rows, project step counts.
  * Scheduler        — due tasks (next_run <= now and enabled).
  * Services         — systemd is-active for swarm-*.
  * Routes           — Flask blueprint imports succeed.
  * Recent failures  — last 5 task_run_log rows with status='error'.

Usage:
    python -m ops.integration_health             # human-readable
    python -m ops.integration_health --json      # machine-readable JSON
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import closing
from typing import Any


SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("SWARM_DB", os.path.join(SWARM_ROOT, "swarm_memory.db"))
SERVICES = (
    "swarm-terminal",
    "swarm-listener",
    "swarm-fridays",
    "swarm-discord",
    "swarm-telegram",
    "swarm-prewarm",
)


def _safe_table_exists(conn, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def db_health() -> dict[str, Any]:
    import sqlite3
    out: dict[str, Any] = {"ok": True, "db_path": DB_PATH, "duplicates": [], "issues": []}
    if not os.path.exists(DB_PATH):
        out["ok"] = False
        out["issues"].append(f"db not found at {DB_PATH}")
        return out
    try:
        with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            if _safe_table_exists(conn, "scheduled_tasks"):
                rows = conn.execute(
                    "SELECT name, COUNT(*) AS n FROM scheduled_tasks "
                    "WHERE name IS NOT NULL AND name != '' "
                    "GROUP BY name HAVING n > 1"
                ).fetchall()
                out["duplicates"] = [{"name": r["name"], "n": r["n"]} for r in rows]
                out["scheduled_tasks_total"] = conn.execute(
                    "SELECT COUNT(*) FROM scheduled_tasks"
                ).fetchone()[0]
                out["scheduled_tasks_missing_next_run"] = conn.execute(
                    "SELECT COUNT(*) FROM scheduled_tasks "
                    "WHERE enabled = 1 AND (next_run IS NULL OR next_run = '')"
                ).fetchone()[0]
                if out["scheduled_tasks_missing_next_run"]:
                    out["issues"].append(
                        f"{out['scheduled_tasks_missing_next_run']} enabled task(s) missing next_run"
                    )
                if out["duplicates"]:
                    out["issues"].append(
                        f"{sum(d['n']-1 for d in out['duplicates'])} duplicate task row(s)"
                    )
            if _safe_table_exists(conn, "project_steps"):
                out["project_steps_open"] = conn.execute(
                    "SELECT COUNT(*) FROM project_steps WHERE status='todo'"
                ).fetchone()[0]
                out["project_steps_done"] = conn.execute(
                    "SELECT COUNT(*) FROM project_steps WHERE status='done'"
                ).fetchone()[0]
    except Exception as exc:
        out["ok"] = False
        out["issues"].append(f"db read failed: {exc}")
    return out


def due_tasks(limit: int = 10) -> list[dict[str, Any]]:
    import sqlite3
    if not os.path.exists(DB_PATH):
        return []
    try:
        with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as conn:
            if not _safe_table_exists(conn, "scheduled_tasks"):
                return []
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            rows = conn.execute(
                "SELECT name, schedule, next_run FROM scheduled_tasks "
                "WHERE enabled=1 AND next_run IS NOT NULL AND next_run != '' AND next_run <= ? "
                "ORDER BY next_run ASC LIMIT ?",
                (now, limit),
            ).fetchall()
            return [
                {"name": r[0], "schedule": r[1], "next_run": r[2]} for r in rows
            ]
    except Exception:
        return []


def service_status() -> list[dict[str, Any]]:
    results = []
    if not shutil.which("systemctl"):
        for s in SERVICES:
            results.append({"name": s, "active": "unknown", "enabled": "unknown"})
        return results
    for name in SERVICES:
        try:
            active = subprocess.run(
                ["systemctl", "is-active", name],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip() or "unknown"
        except Exception:
            active = "unknown"
        try:
            enabled = subprocess.run(
                ["systemctl", "is-enabled", name],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip() or "unknown"
        except Exception:
            enabled = "unknown"
        results.append({"name": name, "active": active, "enabled": enabled})
    return results


def route_imports() -> dict[str, Any]:
    """Confirm every Flask blueprint module imports without error."""
    import importlib
    import pkgutil
    sys.path.insert(0, SWARM_ROOT)
    # Blueprints use absolute imports like `from services import ...` which
    # resolve when frontend/ is on sys.path (terminal.py adds it). Mirror that
    # here so this check exercises the real import surface, not a stricter one.
    sys.path.insert(0, os.path.join(SWARM_ROOT, "frontend"))
    # Y.52: when this runs inside a long pytest session, earlier tests may have
    # cached partial / namespace-package versions of `services` or `database`
    # in sys.modules (e.g. an implicit namespace because frontend/ wasn't on
    # sys.path yet at the first import). Evict those so we re-resolve against
    # the path order we just established.
    for stale in (
        "services", "services.proposal_helpers", "services.identity",
        "services.chat_jobs", "services.chat_relay", "services.chat_history",
        "services.chat_agents", "services.duck_review", "services.alm",
        "services.auth", "services.queue_wrappers",
        "database",
    ):
        mod = sys.modules.get(stale)
        if mod is not None and getattr(mod, "__file__", None) is None:
            sys.modules.pop(stale, None)
    out = {"ok": True, "modules": 0, "failed": []}
    try:
        bp_pkg = importlib.import_module("frontend.blueprints")
    except Exception as exc:
        out["ok"] = False
        out["failed"].append({"module": "frontend.blueprints", "error": str(exc)})
        return out
    pkg_path = getattr(bp_pkg, "__path__", [])
    for info in pkgutil.iter_modules(pkg_path):
        name = f"frontend.blueprints.{info.name}"
        out["modules"] += 1
        try:
            importlib.import_module(name)
        except Exception as exc:
            out["failed"].append({"module": name, "error": str(exc)[:160]})
    out["ok"] = not out["failed"]
    return out


def recent_failures(limit: int = 5) -> list[dict[str, Any]]:
    import sqlite3
    if not os.path.exists(DB_PATH):
        return []
    try:
        with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as conn:
            if not _safe_table_exists(conn, "task_run_log"):
                return []
            rows = conn.execute(
                "SELECT task_name, status, started_at, "
                "       COALESCE(details_json, '') as details "
                "FROM task_run_log "
                "WHERE status='error' "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "task": r[0],
                    "status": r[1],
                    "started_at": r[2],
                    "details": (r[3] or "")[:160],
                }
                for r in rows
            ]
    except Exception:
        return []


def collect() -> dict[str, Any]:
    snap = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db": db_health(),
        "due_tasks": due_tasks(),
        "services": service_status(),
        "routes": route_imports(),
        "recent_failures": recent_failures(),
    }
    issues = list(snap["db"].get("issues") or [])
    issues += [f"{s['name']} {s['active']}" for s in snap["services"] if s["active"] in ("failed", "inactive")]
    if not snap["routes"]["ok"]:
        issues.append(f"{len(snap['routes']['failed'])} blueprint import(s) failed")
    if snap["recent_failures"]:
        issues.append(f"{len(snap['recent_failures'])} recent task error(s)")
    snap["overall_ok"] = not issues
    snap["issues"] = issues
    return snap


def render_text(snap: dict[str, Any]) -> str:
    lines = []
    status = "GREEN" if snap["overall_ok"] else "AMBER/RED"
    lines.append(f"=== Swarm integration health [{status}] {snap['generated_at']} ===")
    db = snap["db"]
    lines.append(f"DB: {db.get('db_path')}")
    lines.append(
        f"  scheduled_tasks: total={db.get('scheduled_tasks_total', '?')}  "
        f"missing_next_run={db.get('scheduled_tasks_missing_next_run', '?')}  "
        f"duplicates={len(db.get('duplicates') or [])}"
    )
    lines.append(
        f"  project_steps: open={db.get('project_steps_open', '?')}  "
        f"done={db.get('project_steps_done', '?')}"
    )
    if snap["due_tasks"]:
        lines.append(f"Due tasks ({len(snap['due_tasks'])}):")
        for t in snap["due_tasks"][:5]:
            lines.append(f"  - {t['name']:<30} next={t['next_run']}")
    else:
        lines.append("Due tasks: none")
    lines.append("Services:")
    for s in snap["services"]:
        lines.append(f"  {s['name']:<22} active={s['active']:<10} enabled={s['enabled']}")
    rt = snap["routes"]
    lines.append(f"Routes: {rt['modules']} modules, {len(rt['failed'])} failed")
    for f in rt["failed"][:5]:
        lines.append(f"  ! {f['module']}: {f['error']}")
    if snap["recent_failures"]:
        lines.append("Recent task errors:")
        for r in snap["recent_failures"]:
            lines.append(f"  - {r['started_at']}  {r['task']}  {r['details']}")
    if snap["issues"]:
        lines.append("Issues:")
        for i in snap["issues"]:
            lines.append(f"  ! {i}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Swarm integration health report")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)
    snap = collect()
    if args.json:
        print(json.dumps(snap, indent=2, default=str))
    else:
        print(render_text(snap))
    return 0 if snap["overall_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
