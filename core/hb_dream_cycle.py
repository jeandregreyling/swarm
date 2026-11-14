"""DREAM cycle: Distinguish Repetition, Execution, Acceleration, Motivation.

Runs inside the existing HB coordinator tick (core/peer_coordination.py); no
new daemon. Off until the owner enables it (same rule as task continuation).

After `idle_after` seconds without a real owner chat message, HB writes ONE
measured-facts report per idle period: which tasks are spinning (and the exact
repeated error), which are held waiting for the owner, and what is queued.
No model call, no source writes, no online calls. When the owner returns, an
open cycle is closed as `owner_returned`.

CLI:  python -m core.hb_dream_cycle status|enable [seconds]|disable|report
"""
import json
import time

from core import hb_dream

DEFAULT_IDLE_AFTER = 3600


def ensure_schema(conn):
    hb_dream.ensure_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS hb_dream_settings(id INTEGER PRIMARY KEY CHECK(id=1),"
                 " enabled INTEGER NOT NULL DEFAULT 0, idle_after INTEGER NOT NULL DEFAULT 3600, updated_at REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS hb_dream_cycles(cycle_id INTEGER PRIMARY KEY, started_at REAL NOT NULL,"
                 " idle_since REAL NOT NULL, state TEXT NOT NULL, finished_at REAL, report TEXT)")


def settings(conn):
    ensure_schema(conn)
    row = conn.execute("SELECT enabled, idle_after FROM hb_dream_settings WHERE id=1").fetchone()
    return {"enabled": bool(row[0]), "idle_after": int(row[1])} if row else {"enabled": False, "idle_after": DEFAULT_IDLE_AFTER}


def configure(conn, enabled, idle_after=None):
    ensure_schema(conn)
    idle_after = int(idle_after or settings(conn)["idle_after"])
    if idle_after < 60:
        raise ValueError("idle_after must be at least 60 seconds")
    conn.execute("INSERT INTO hb_dream_settings(id,enabled,idle_after,updated_at) VALUES(1,?,?,?) "
                 "ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled, idle_after=excluded.idle_after, "
                 "updated_at=excluded.updated_at", (int(bool(enabled)), idle_after, time.time()))
    return settings(conn)


def observe_latest_owner_message(conn):
    """Feed the newest saved owner chat message into DREAM's activity clock."""
    row = conn.execute("SELECT MAX(id) FROM messages WHERE from_agent='user' AND message_type='chat'").fetchone()
    return bool(row and row[0]) and hb_dream.observe_owner_message(conn, row[0])


def build_report(conn):
    """Measured facts only. Every line comes from a database row, not a model."""
    from core.hb_task_manager import stuck_reason
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    facts = {"spinning": [], "held": [], "queued_requests": 0}
    if "hb_task_manager" in tables and "hb_tasks" in tables:
        for task_id, state, detail, title in conn.execute(
                "SELECT m.task_id, m.state, m.detail, t.title FROM hb_task_manager m JOIN hb_tasks t USING(task_id) "
                "WHERE m.enabled=1 AND t.state NOT IN ('completed','cancelled') ORDER BY m.updated_at DESC LIMIT 50"):
            reason = stuck_reason(conn, task_id)
            item = {"task_id": task_id, "title": str(title)[:120], "state": state}
            if reason:
                facts["spinning"].append(dict(item, reason=reason))
            elif state in ("held", "needs_owner", "waiting_dependencies", "waiting_resources"):
                facts["held"].append(dict(item, detail=str(detail)[:200]))
    if "hb_peer_work" in tables:
        facts["queued_requests"] = conn.execute("SELECT COUNT(*) FROM hb_peer_work WHERE state='queued'").fetchone()[0]
    lines = ["DREAM report (measured facts from HB records; no model output)."]
    for s in facts["spinning"]:
        lines.append(f"- SPINNING {s['task_id']} '{s['title']}': {s['reason']}. Fix: clarify the goal or add acceptance checks before Continue.")
    for h in facts["held"]:
        lines.append(f"- WAITING {h['task_id']} '{h['title']}': {h['state']} ({h['detail']}).")
    lines.append(f"- Queued peer requests: {facts['queued_requests']}.")
    if not facts["spinning"] and not facts["held"]:
        lines.append("- No managed task is spinning or waiting on the owner.")
    return {"facts": facts, "text": "\n".join(lines)}


def tick(conn, now=None):
    """One DREAM pass. Returns the new cycle id, or None."""
    ensure_schema(conn)
    now = time.time() if now is None else now
    observe_latest_owner_message(conn)
    row = conn.execute("SELECT timestamp FROM hb_dream_activity WHERE id=1").fetchone()
    last_owner = row[0] if row else None
    open_cycle = conn.execute("SELECT cycle_id, started_at FROM hb_dream_cycles WHERE state='running'").fetchone()
    if open_cycle and last_owner is not None and last_owner > open_cycle[1]:
        conn.execute("UPDATE hb_dream_cycles SET state='owner_returned', finished_at=? WHERE cycle_id=?", (now, open_cycle[0]))
        open_cycle = None
    cfg = settings(conn)
    if not cfg["enabled"] or last_owner is None or open_cycle:
        return None
    if now - last_owner < cfg["idle_after"]:
        return None
    if conn.execute("SELECT 1 FROM hb_dream_cycles WHERE idle_since=?", (last_owner,)).fetchone():
        return None                                    # one cycle per idle period
    cur = conn.execute("INSERT INTO hb_dream_cycles(started_at, idle_since, state) VALUES(?,?,'running')", (now, last_owner))
    report = build_report(conn)
    conn.execute("UPDATE hb_dream_cycles SET state='reported', finished_at=?, report=? WHERE cycle_id=?",
                 (time.time(), json.dumps(report), cur.lastrowid))
    return cur.lastrowid


def latest_report(conn):
    ensure_schema(conn)
    row = conn.execute("SELECT cycle_id, started_at, state, report FROM hb_dream_cycles ORDER BY cycle_id DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {"cycle_id": row[0], "started_at": row[1], "state": row[2], "report": json.loads(row[3]) if row[3] else None}


if __name__ == "__main__":
    import sys
    from contextlib import closing
    from utils.db._connection import get_connection
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    with closing(get_connection()) as conn, conn:
        if cmd == "enable":
            print(configure(conn, True, sys.argv[2] if len(sys.argv) > 2 else None))
        elif cmd == "disable":
            print(configure(conn, False))
        elif cmd == "report":
            print(build_report(conn)["text"])
        else:
            print(json.dumps({"settings": settings(conn), "latest": latest_report(conn)}, indent=2, default=str))
