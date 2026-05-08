"""agents/seven/memory_backfill.py — thread continuity repair for Seven.

Problem: Seven's local memory index would occasionally lose continuity on a
specific thread (first reported on thread 2112) — the agent recalled messages
from turns N-2 and N but not N-1, producing "I already said that" style
non-sequiturs. Root cause was a race in the shared-thread writer where the
intermediate turn's memory insert happened after the next turn's read.

Repair strategy:
1. For each thread with gaps in ``agent_memory.created_at`` ordering vs the
   canonical ``queue`` ordering, re-scan the queue for that thread and rewrite
   the memory rows to match queue order.
2. Tag the rewritten rows with ``backfill,thread_repair`` so future reads can
   distinguish repaired turns from live ones.
3. Emit a summary row to ``audit/seven_memory_repair.log`` for observability.

This is a read-mostly, idempotent tool — running it twice does nothing the
second time.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import time
from typing import Iterable, Optional

logger = logging.getLogger("agents.seven.memory_backfill")

AUDIT_LOG = pathlib.Path(os.environ.get(
    "SEVEN_MEMORY_REPAIR_LOG",
    os.path.join(os.path.dirname(__file__), "..", "..", "audit", "seven_memory_repair.log"),
))
REPAIR_TAGS = "backfill,thread_repair"


def _iter_gap_threads(conn, agent: str = "seven") -> Iterable[tuple[int, int, int]]:
    """Yield (thread_id, queue_count, memory_count) for threads where counts disagree.

    Uses a correlated subquery for the per-thread memory count rather than a
    LEFT JOIN, because the LEFT JOIN produced a row-multiplication bug —
    each queue row matched the same memory row via ``LIKE``, so memory_count
    came out equal to queue_count and the gap was masked. (This is the bug
    that originally hid thread 2112 from the repair sweep.)
    """
    rows = conn.execute(
        """
        SELECT q.thread_id AS thread_id,
               COUNT(DISTINCT q.id) AS queue_count,
               (SELECT COUNT(*) FROM agent_memory m
                  WHERE m.agent = ?
                    AND m.context LIKE ('%thread_' || q.thread_id || '%')
               ) AS memory_count
        FROM queue q
        WHERE q.thread_id IS NOT NULL
        GROUP BY q.thread_id
        HAVING memory_count < queue_count
        """,
        (agent,),
    ).fetchall()
    for r in rows:
        yield int(r[0]), int(r[1] or 0), int(r[2] or 0)


def repair_thread(conn, thread_id: int, agent: str = "seven") -> int:
    """Rebuild memory rows for a single thread. Returns rows written."""
    queue_rows = conn.execute(
        """SELECT id, prompt, response, created_at FROM queue
           WHERE thread_id=? ORDER BY id ASC""",
        (thread_id,),
    ).fetchall()
    written = 0
    for row in queue_rows:
        qid, prompt, response, created = row[0], row[1], row[2], row[3]
        exists = conn.execute(
            "SELECT 1 FROM agent_memory WHERE agent=? AND context=? LIMIT 1",
            (agent, f"thread_{thread_id}:queue_{qid}"),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO agent_memory (agent, message, context, tags, importance, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent, (prompt or "") + "\n---\n" + (response or ""),
             f"thread_{thread_id}:queue_{qid}",
             REPAIR_TAGS, 6, created or time.time()),
        )
        written += 1
    conn.commit()
    return written


def run(agent: str = "seven", *, dry_run: bool = False) -> dict:
    """Scan + repair. Returns summary dict."""
    try:
        from database import get_connection  # type: ignore
    except Exception as exc:  # pragma: no cover — only fails outside the app
        return {"ok": False, "error": f"database module unavailable: {exc}"}

    conn = get_connection()
    summary: dict = {"checked": 0, "repaired_threads": [], "rows_written": 0}
    try:
        for thread_id, queue_count, memory_count in _iter_gap_threads(conn, agent):
            summary["checked"] += 1
            if dry_run:
                summary["repaired_threads"].append(
                    {"thread_id": thread_id, "queue_count": queue_count,
                     "memory_count": memory_count, "dry_run": True})
                continue
            written = repair_thread(conn, thread_id, agent)
            summary["rows_written"] += written
            summary["repaired_threads"].append(
                {"thread_id": thread_id, "queue_count": queue_count,
                 "memory_count": memory_count, "written": written})
    finally:
        conn.close()

    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a") as fh:
            fh.write(json.dumps({"ts": time.time(), **summary}) + "\n")
    except OSError:
        pass
    summary["ok"] = True
    return summary


if __name__ == "__main__":  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(run(dry_run=args.dry_run), indent=2))
