"""Seven-owned DEOS operating contract.

DEOS = Decides, Executes, Operates, Sustains.

This module is intentionally small and deterministic. It gives Seven a native
way to describe the proof standard he should hold the system to, and to read the
latest DEOS/browser evidence from Studio rather than relying on chat memory.
"""
from __future__ import annotations

from pathlib import Path
import os
import sqlite3


PROJECT_ID = 'P-SEVEN-DIRECT-GGUF'
STEP_ID = 'S-DGGUF-14'


def _db_path() -> Path:
    env = os.environ.get('SWARM_MEMORY_DB') or os.environ.get('SWARM_DB_PATH')
    if env:
        return Path(env)
    root = os.environ.get('SWARM_ROOT') or str(Path(__file__).resolve().parent.parent.parent)
    return Path(root) / 'swarm_memory.db'


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def latest_evidence(limit: int = 5) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, project_id, step_id, source_type, source_ref, status, summary, created_at
            FROM project_step_evidence
            WHERE project_id = ? AND step_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (PROJECT_ID, STEP_ID, max(1, int(limit or 5))),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def contract() -> str:
    return (
        "DEOS = Decides, Executes, Operates, Sustains.\n\n"
        "Seven's rule for Fridays fixes:\n"
        "  0. CHM maps the handoff: preserve source, target, whole latest turn, obligations, evidence, unresolved items, and return path.\n"
        "  1. Decides: bind every obligation to a real user path test, action, or explicit blocker.\n"
        "  2. Executes: click or invoke the same surface the user uses.\n"
        "  3. Operates: inspect rendered UI, API, DB rows, jobs, recoveries, and service state.\n"
        "  4. Sustains: leave a regression guard, cache/service refresh, Studio/KC evidence, and the next teaching obligation.\n\n"
        "Specific learned constraint: if home chat says 'Ask Seven', fresh home chat must route to Seven. "
        "A probe that manually selects Seven is not enough."
    )


def status(limit: int = 5) -> str:
    rows = latest_evidence(limit=limit)
    lines = [contract()]
    if not rows:
        lines.append("\nLatest evidence: none recorded for the Seven direct/chat path.")
        return '\n'.join(lines)
    lines.append("\nLatest Seven/DEOS evidence:")
    for r in rows:
        summary = str(r.get('summary') or '').strip().replace('\n', ' ')
        if len(summary) > 240:
            summary = summary[:240] + '...'
        lines.append(
            f"  · #{r.get('id')} {r.get('status')} {r.get('source_type')} "
            f"{r.get('source_ref')} — {summary}"
        )
    return '\n'.join(lines)


__all__ = ['PROJECT_ID', 'STEP_ID', 'contract', 'latest_evidence', 'status']
