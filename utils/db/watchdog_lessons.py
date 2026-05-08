"""Persistent Watchdog repair lessons.

This is the small bridge between "we noticed a failure" and "local agents can
repair it through DEV/UAT".  Watchdog records a failure class plus the proof
needed before the lesson is promoted into behavior.
"""
from __future__ import annotations

import json
import uuid

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

