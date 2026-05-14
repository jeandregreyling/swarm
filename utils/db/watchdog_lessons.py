"""Persistent Watchdog repair lessons.

Enhanced: Stall detection now attempts basic recovery (pause) where safe
and creates stronger repair lessons with recovery suggestions.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from ._connection import get_connection


_OPEN_STATUSES = {'open', 'assigned', 'dev', 'uat'}


def _ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchdog_repair_lessons (
            lesson_id TEXT PRIMARY KEY,
            failure_class TEXT NOT NULL,
            symptom TEXT NOT NULL,
            evidence_json TEXT DEFAULT '{}',
            lesson TEXT NOT NULL,
            proof_required TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            owner TEXT DEFAULT 'watchdog',
            source_thread_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_watchdog_repair_lessons_status
        ON watchdog_repair_lessons(status, updated_at)
        """
    )


def _row_to_dict(row):
    if row is None:
        return None
    data = dict(row)
    try:
        data['evidence'] = json.loads(data.pop('evidence_json') or '{}')
    except Exception:
        data['evidence'] = {}
    return data


def record_repair_lesson(
    failure_class,
    symptom,
    lesson,
    *,
    proof_required='',
    evidence=None,
    owner='watchdog',
    source_thread_id='',
    lesson_id=None,
):
    """Create or update a Watchdog repair lesson and return it as a dict."""
    failure_class = str(failure_class or '').strip()
    symptom = str(symptom or '').strip()
    lesson = str(lesson or '').strip()
    if not failure_class or not symptom or not lesson:
        raise ValueError('failure_class, symptom, and lesson are required')

    evidence_json = json.dumps(evidence or {}, sort_keys=True)
    lesson_id = str(lesson_id or f'WDL-{uuid.uuid4().hex[:10].upper()}')
    conn = get_connection()
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO watchdog_repair_lessons
                (lesson_id, failure_class, symptom, evidence_json, lesson,
                 proof_required, status, owner, source_thread_id)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
            ON CONFLICT(lesson_id) DO UPDATE SET
                failure_class=excluded.failure_class,
                symptom=excluded.symptom,
                evidence_json=excluded.evidence_json,
                lesson=excluded.lesson,
                proof_required=excluded.proof_required,
                owner=excluded.owner,
                source_thread_id=excluded.source_thread_id,
                updated_at=datetime('now')
            """,
            (
                lesson_id,
                failure_class,
                symptom,
                evidence_json,
                lesson,
                str(proof_required or '').strip(),
                str(owner or 'watchdog').strip() or 'watchdog',
                str(source_thread_id or '').strip(),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM watchdog_repair_lessons WHERE lesson_id=?",
            (lesson_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_open_repair_lessons(limit=20):
    conn = get_connection()
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT * FROM watchdog_repair_lessons
            WHERE status IN ({})
            ORDER BY updated_at DESC
            LIMIT ?
            """.format(','.join('?' for _ in _OPEN_STATUSES)),
            (*sorted(_OPEN_STATUSES), int(limit or 20)),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def detect_and_record_stalls(max_age_minutes: int = 15, limit: int = 20, auto_recover: bool = True) -> list:
    """
    Automatic stall detector with optional recovery.
    Finds stuck processing tasks and creates repair lessons.
    If auto_recover=True, attempts to pause stuck tasks as first response.
    """
    conn = get_connection()
    created_lessons = []
    try:
        _ensure_schema(conn)

        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()

        # Try queue first, fallback to chat_jobs
        try:
            rows = conn.execute(
                """
                SELECT id, agent, thread_id, status, updated_at
                FROM queue
                WHERE status = 'processing' AND updated_at < ?
                ORDER BY updated_at ASC LIMIT ?
                """,
                (cutoff, limit)
            ).fetchall()
        except Exception:
            rows = conn.execute(
                """
                SELECT id, agent, conversation_id as thread_id, status, updated_at
                FROM chat_jobs
                WHERE status = 'processing' AND updated_at < ?
                ORDER BY updated_at ASC LIMIT ?
                """,
                (cutoff, limit)
            ).fetchall()

        for row in rows:
            row_dict = dict(row)
            agent = row_dict.get('agent') or 'unknown'
            thread_id = str(row_dict.get('thread_id') or row_dict.get('id') or '')

            # Attempt auto-recovery: pause the stuck task
            recovered = False
            if auto_recover:
                try:
                    conn.execute(
                        "UPDATE queue SET status = 'paused' WHERE id = ? AND status = 'processing'",
                        (row_dict.get('id'),)
                    )
                    conn.commit()
                    recovered = True
                except Exception:
                    pass  # table might differ, ignore

            symptom = f"Stuck in processing > {max_age_minutes} min (agent={agent}, thread={thread_id})"
            lesson_text = (
                f"Task for agent {agent} (thread {thread_id}) stuck in processing. "
                f"Auto-paused: {recovered}. "
                "Next: investigate logs, add heartbeat/timeout, or trigger full recovery sweep."
            )
            evidence = {
                'agent': agent,
                'thread_id': thread_id,
                'auto_paused': recovered,
                'detected_at': datetime.now().isoformat(),
            }

            lesson = record_repair_lesson(
                failure_class='stalled_task',
                symptom=symptom,
                lesson=lesson_text,
                evidence=evidence,
                owner='watchdog_auto',
                source_thread_id=thread_id,
            )
            if lesson:
                created_lessons.append(lesson)

        return created_lessons
    finally:
        conn.close()
