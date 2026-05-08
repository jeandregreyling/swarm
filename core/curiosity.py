"""
core/curiosity.py — PACKET-10B: Curiosity organ.

Seven (and any other agent) asks questions when stuck instead of failing
silently or hallucinating an answer. Questions land in `curiosity_questions`,
where the user (or another agent) can answer them. Answers are promoted into
`seven_beliefs` so the system *learns* from them — past curiosity becomes
permanent knowledge.

Motto: "Not a system that REPORTS. A system that DOES."
A system that doesn't know something must say so, then remember the answer.

Public API
----------
    ask(asked_by, question, *, context_kind=None, context_ref=None,
        options=None, salience=0.5, dedup_window_hours=24) -> int | None
    answer(question_id, answer_text, *, answered_by='user',
           promote_to_belief=True) -> bool
    list_open(*, limit=20, min_salience=0.0, asked_by=None) -> list[dict]
    list_recent(*, limit=20, status=None) -> list[dict]
    dismiss(question_id, *, reason=None) -> bool
    prune(*, max_age_days=30) -> int
    stats() -> dict

The schema is created on import so callers don't need bootstrap logic.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger("seven.curiosity")

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = str(ROOT / "swarm_memory.db")


def _db_path() -> str:
    """Return current DB path. Read dynamically so tests can swap it."""
    return os.environ.get("SWARM_MEMORY_DB", _DEFAULT_DB)


# Backwards-compat: some callers may inspect this. Updated lazily.
DB_PATH = Path(_db_path())

# Statuses
STATUS_OPEN = "open"
STATUS_ANSWERED = "answered"
STATUS_DISMISSED = "dismissed"
STATUS_EXPIRED = "expired"

_VALID_STATUSES = {STATUS_OPEN, STATUS_ANSWERED, STATUS_DISMISSED, STATUS_EXPIRED}


# ── connection / schema ──────────────────────────────────────────────────────


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS curiosity_questions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            asked_by          TEXT NOT NULL,
            context_kind      TEXT,
            context_ref       TEXT,
            question          TEXT NOT NULL,
            options_json      TEXT,
            salience          REAL DEFAULT 0.5,
            status            TEXT NOT NULL DEFAULT 'open',
            asked_at          REAL NOT NULL,
            answered_at       REAL,
            answer            TEXT,
            answered_by       TEXT,
            created_belief_id INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_curiosity_status
            ON curiosity_questions(status, salience DESC);
        CREATE INDEX IF NOT EXISTS idx_curiosity_asked
            ON curiosity_questions(asked_by, asked_at DESC);
        CREATE INDEX IF NOT EXISTS idx_curiosity_question
            ON curiosity_questions(question);
        """
    )
    con.commit()


# Initialise schema on first import (best-effort; never crash the importer).
try:
    _con0 = _connect()
    try:
        _ensure_schema(_con0)
    finally:
        _con0.close()
except Exception as exc:  # pragma: no cover - defensive
    logger.warning("[curiosity] schema bootstrap failed: %s", exc)


# ── helpers ──────────────────────────────────────────────────────────────────


def _normalise_question(q: str) -> str:
    """Loose dedup key — collapse whitespace + lowercase, keep punctuation."""
    return " ".join((q or "").lower().split())


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    raw = d.get("options_json")
    if raw:
        try:
            d["options"] = json.loads(raw)
        except Exception:
            d["options"] = None
    else:
        d["options"] = None
    return d


def _clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


# ── public API ───────────────────────────────────────────────────────────────


def ask(
    asked_by: str,
    question: str,
    *,
    context_kind: Optional[str] = None,
    context_ref: Optional[str] = None,
    options: Optional[Iterable[str]] = None,
    salience: float = 0.5,
    dedup_window_hours: float = 24.0,
) -> Optional[int]:
    """Record a curiosity question.

    Returns the question id (new or existing dedup hit), or None if the
    inputs were unusable. Dedup: if the same agent asked the same
    normalised question within the last ``dedup_window_hours`` and it is
    still open, that row is bumped (salience taken as max) and its id
    returned instead of inserting a new row.
    """
    if not asked_by or not question:
        logger.debug("[curiosity] ask() ignored: missing asked_by/question")
        return None

    asked_by = str(asked_by).strip().lower()[:64]
    question = str(question).strip()
    if not question:
        return None
    if len(question) > 2000:
        question = question[:2000]

    salience = _clamp(float(salience or 0.5), 0.0, 1.0)
    options_json = json.dumps(list(options)) if options else None
    norm = _normalise_question(question)

    con = _connect()
    try:
        _ensure_schema(con)
        now = time.time()

        # Dedup: open question, same agent, same normalised text, within window.
        if dedup_window_hours and dedup_window_hours > 0:
            cutoff = now - dedup_window_hours * 3600.0
            existing = con.execute(
                """
                SELECT id, salience FROM curiosity_questions
                WHERE asked_by = ?
                  AND status = 'open'
                  AND asked_at >= ?
                  AND LOWER(TRIM(question)) = ?
                ORDER BY asked_at DESC LIMIT 1
                """,
                (asked_by, cutoff, norm),
            ).fetchone()
            if existing:
                new_sal = max(float(existing["salience"] or 0.0), salience)
                con.execute(
                    "UPDATE curiosity_questions SET salience = ? WHERE id = ?",
                    (new_sal, existing["id"]),
                )
                con.commit()
                logger.info(
                    "[curiosity] dedup hit id=%s asked_by=%s sal=%.2f",
                    existing["id"], asked_by, new_sal,
                )
                return int(existing["id"])

        cur = con.execute(
            """
            INSERT INTO curiosity_questions (
                asked_by, context_kind, context_ref, question,
                options_json, salience, status, asked_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                asked_by,
                context_kind,
                context_ref,
                question,
                options_json,
                salience,
                now,
            ),
        )
        con.commit()
        qid = int(cur.lastrowid)
        logger.info(
            "[curiosity] q#%d asked by %s sal=%.2f kind=%s",
            qid, asked_by, salience, context_kind,
        )

        # Best-effort episode write so Seven's brain notices it.
        try:
            con.execute(
                """
                INSERT INTO seven_episodes (ts, source, kind, record_id, action, actor, salience, payload_json)
                VALUES (?, 'curiosity', 'curiosity_question', ?, 'asked', ?, ?, ?)
                """,
                (
                    now,
                    f"Q-{qid}",
                    asked_by,
                    salience,
                    json.dumps({
                        "question": question[:500],
                        "context_kind": context_kind,
                        "context_ref": context_ref,
                    }),
                ),
            )
            con.commit()
        except Exception:
            pass

        return qid
    finally:
        con.close()


def answer(
    question_id: int,
    answer_text: str,
    *,
    answered_by: str = "user",
    promote_to_belief: bool = True,
) -> bool:
    """Answer a question. Optionally promote the answer to a seven_belief.

    Returns True on success, False if the question is missing or already
    closed.
    """
    if not question_id or not (answer_text or "").strip():
        return False

    answer_text = str(answer_text).strip()[:4000]
    answered_by = (answered_by or "user").strip().lower()[:64]

    con = _connect()
    try:
        _ensure_schema(con)
        row = con.execute(
            "SELECT * FROM curiosity_questions WHERE id = ?", (int(question_id),)
        ).fetchone()
        if not row:
            return False
        if row["status"] != STATUS_OPEN:
            logger.info(
                "[curiosity] q#%d already %s — refusing re-answer",
                question_id, row["status"],
            )
            return False

        now = time.time()
        belief_id: Optional[int] = None

        if promote_to_belief:
            try:
                # Promote: subject=context_ref or 'curiosity', predicate='answer:<question>',
                # object=answer_text, confidence=high if user, lower otherwise.
                subj = row["context_ref"] or f"curiosity::{row['asked_by']}"
                pred = "answer"
                obj = answer_text[:1000]
                conf = 0.9 if answered_by == "user" else 0.6
                # Best-effort upsert (table from PACKET-10 brain).
                cur = con.execute(
                    """
                    INSERT INTO seven_beliefs (
                        subject, predicate, object, confidence,
                        evidence_count, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(subject, predicate, object) DO UPDATE SET
                        confidence = MAX(confidence, excluded.confidence),
                        evidence_count = evidence_count + 1,
                        last_seen = excluded.last_seen
                    """,
                    (subj, pred, obj, conf, now, now),
                )
                belief_id = int(cur.lastrowid) if cur.lastrowid else None
            except Exception as exc:
                logger.debug("[curiosity] belief promotion skipped: %s", exc)

        con.execute(
            """
            UPDATE curiosity_questions
               SET status = 'answered',
                   answer = ?,
                   answered_at = ?,
                   answered_by = ?,
                   created_belief_id = COALESCE(?, created_belief_id)
             WHERE id = ?
            """,
            (answer_text, now, answered_by, belief_id, int(question_id)),
        )

        # Record episode.
        try:
            con.execute(
                """
                INSERT INTO seven_episodes (ts, source, kind, record_id, action, actor, salience, payload_json)
                VALUES (?, 'curiosity', 'curiosity_question', ?, 'answered', ?, ?, ?)
                """,
                (
                    now,
                    f"Q-{int(question_id)}",
                    answered_by,
                    float(row["salience"] or 0.5),
                    json.dumps({"answer": answer_text[:500], "belief_id": belief_id}),
                ),
            )
        except Exception:
            pass

        con.commit()
        logger.info(
            "[curiosity] q#%d answered by %s (belief=%s)",
            question_id, answered_by, belief_id,
        )
        return True
    finally:
        con.close()


def list_open(
    *,
    limit: int = 20,
    min_salience: float = 0.0,
    asked_by: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return open questions, highest salience + most recent first."""
    limit = max(1, min(int(limit or 20), 500))
    min_salience = _clamp(float(min_salience or 0.0), 0.0, 1.0)
    con = _connect()
    try:
        _ensure_schema(con)
        sql = (
            "SELECT * FROM curiosity_questions "
            "WHERE status='open' AND salience >= ?"
        )
        params: list[Any] = [min_salience]
        if asked_by:
            sql += " AND asked_by = ?"
            params.append(asked_by.strip().lower())
        sql += " ORDER BY salience DESC, asked_at DESC LIMIT ?"
        params.append(limit)
        rows = con.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        con.close()


def list_recent(
    *, limit: int = 20, status: Optional[str] = None
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 500))
    con = _connect()
    try:
        _ensure_schema(con)
        if status and status in _VALID_STATUSES:
            rows = con.execute(
                "SELECT * FROM curiosity_questions WHERE status = ? "
                "ORDER BY asked_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM curiosity_questions "
                "ORDER BY asked_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        con.close()


def dismiss(question_id: int, *, reason: Optional[str] = None) -> bool:
    """Mark a question as dismissed (no answer needed). Idempotent."""
    if not question_id:
        return False
    con = _connect()
    try:
        _ensure_schema(con)
        row = con.execute(
            "SELECT id, status FROM curiosity_questions WHERE id = ?",
            (int(question_id),),
        ).fetchone()
        if not row:
            return False
        if row["status"] != STATUS_OPEN:
            return False
        now = time.time()
        con.execute(
            """
            UPDATE curiosity_questions
               SET status='dismissed',
                   answered_at = ?,
                   answer = COALESCE(?, answer),
                   answered_by = 'system'
             WHERE id = ?
            """,
            (now, reason, int(question_id)),
        )
        con.commit()
        logger.info("[curiosity] q#%d dismissed (%s)", question_id, reason or "")
        return True
    finally:
        con.close()


def prune(*, max_age_days: int = 30) -> int:
    """Mark old open questions as expired. Returns count."""
    if max_age_days <= 0:
        return 0
    cutoff = time.time() - max_age_days * 86400.0
    con = _connect()
    try:
        _ensure_schema(con)
        cur = con.execute(
            "UPDATE curiosity_questions "
            "SET status='expired', answered_at = ? "
            "WHERE status='open' AND asked_at < ?",
            (time.time(), cutoff),
        )
        con.commit()
        n = int(cur.rowcount or 0)
        if n:
            logger.info("[curiosity] pruned %d expired questions", n)
        return n
    finally:
        con.close()


def stats() -> dict[str, Any]:
    """Snapshot for the digest / self-test."""
    con = _connect()
    try:
        _ensure_schema(con)
        out: dict[str, Any] = {}
        for status in _VALID_STATUSES:
            n = con.execute(
                "SELECT COUNT(*) FROM curiosity_questions WHERE status = ?",
                (status,),
            ).fetchone()[0]
            out[status] = int(n)
        latest = con.execute(
            "SELECT asked_at FROM curiosity_questions "
            "WHERE status='open' ORDER BY asked_at DESC LIMIT 1"
        ).fetchone()
        out["latest_open_age_h"] = (
            (time.time() - float(latest[0])) / 3600.0 if latest else None
        )
        top = con.execute(
            "SELECT id, asked_by, question, salience FROM curiosity_questions "
            "WHERE status='open' ORDER BY salience DESC, asked_at DESC LIMIT 3"
        ).fetchall()
        out["top_open"] = [dict(r) for r in top]
        return out
    finally:
        con.close()


# ── convenience: structured wrapper for common stuck contexts ─────────────────


def from_llm_failure(
    asked_by: str, prompt: str, error: BaseException, *, salience: float = 0.4
) -> Optional[int]:
    """Helper: an agent's LLM call died. Ask the user for guidance."""
    snippet = (prompt or "")[:200]
    return ask(
        asked_by=asked_by,
        question=(
            f"My language model is unavailable right now. "
            f"How should I handle this kind of request next time?\n\n"
            f"User asked: {snippet!r}\n"
            f"Error: {type(error).__name__}: {str(error)[:200]}"
        ),
        context_kind="llm_failure",
        context_ref=type(error).__name__,
        salience=salience,
    )


def from_ambiguous_route(
    asked_by: str, message: str, candidates: Iterable[str], *, salience: float = 0.5
) -> Optional[int]:
    """Helper: routing has multiple equally-good targets."""
    cands = list(candidates)[:8]
    return ask(
        asked_by=asked_by,
        question=(
            f"I wasn't sure who should handle this:\n  '{(message or '')[:200]}'\n"
            f"Candidates: {', '.join(cands) or '(none)'}\n"
            f"Which agent fits best by default?"
        ),
        context_kind="ambiguous_route",
        options=cands or None,
        salience=salience,
    )


def from_unknown_term(asked_by: str, term: str, *, salience: float = 0.3) -> Optional[int]:
    """Helper: encountered a term/concept the system doesn't know."""
    if not term:
        return None
    return ask(
        asked_by=asked_by,
        question=f"I don't recognise the term '{term}'. What does it mean in this system?",
        context_kind="unknown_term",
        context_ref=term[:200],
        salience=salience,
    )
