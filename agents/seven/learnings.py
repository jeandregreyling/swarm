"""Seven's self-learning loop.

Captures lessons from real conversational signal:

- Negative reactions ("no", "wrong", "fuck", "again", "stop guessing") on the
  user turn following a Seven turn → stored as a NEGATIVE lesson tied to that
  prior reply.
- Positive reactions ("good", "yes", "perfect", "ship it", "exactly") →
  POSITIVE lesson reinforcing the prior reply pattern.

Lessons are surfaced back to Seven via `recent_lessons_block(limit)` and are
injected into the LLM system prompt every turn.

Storage: SQLite table `seven_learnings` in the same DB as the rest of Seven's
state (`SWARM_MEMORY_DB`). Schema is forward-compatible via `ensure_columns`
on init, mirroring the wishlist pillar pattern.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

NEG_PATTERNS = re.compile(
    r'\b(no(?:pe)?|wrong|stop|again|bullshit|slop|mediocre|lazy|guessing|hallucinat\w+|'
    r"that's not|that is not|don'?t|incorrect|fail(?:ed|ing)?|broke|broken)\b",
    re.IGNORECASE,
)
POS_PATTERNS = re.compile(
    r'\b(good|great|perfect|exactly|nice|clean|ship\s*it|love it|yes please|'
    r'thank you|legendary|amazing|excellent|on point)\b',
    re.IGNORECASE,
)
PROFANE_NEG = re.compile(r'\b(fuck|shit|crap)\b', re.IGNORECASE)


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


def _ensure_columns(conn, table, cols):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    have = {r['name'] for r in rows}
    for name, sqltype in cols.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}")


def _init():
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seven_learnings (
                lesson_id   TEXT PRIMARY KEY,
                ts          INTEGER NOT NULL,
                kind        TEXT NOT NULL,            -- 'positive' | 'negative'
                trigger     TEXT,                     -- the user words that triggered capture
                user_msg    TEXT,                     -- full user turn text (truncated)
                seven_msg   TEXT,                     -- the prior Seven reply being judged
                weight      REAL DEFAULT 1.0,
                tags        TEXT DEFAULT '',
                created_at  INTEGER NOT NULL
            )
        """)
        _ensure_columns(conn, 'seven_learnings', {
            'context_hint': 'TEXT',  # short distillation Seven can quote in future
        })
        conn.commit()
    finally:
        conn.close()


def _gen_id() -> str:
    return f"LRN-{uuid.uuid4().hex[:8].upper()}"


def classify(user_msg: str) -> tuple[str | None, str | None]:
    """Return (kind, trigger) or (None, None) if no clear signal."""
    if not user_msg:
        return None, None
    txt = user_msg.strip()
    # Negative signals dominate when both present (the user is correcting).
    m_neg = NEG_PATTERNS.search(txt) or PROFANE_NEG.search(txt)
    if m_neg:
        return 'negative', m_neg.group(0)
    m_pos = POS_PATTERNS.search(txt)
    if m_pos:
        return 'positive', m_pos.group(0)
    return None, None


def observe(user_msg: str, prior_seven_msg: str | None) -> dict | None:
    """Inspect a user turn (with the immediately preceding Seven reply) and
    record a lesson if there is a clear positive/negative signal.

    Returns the inserted lesson row dict, or None.
    """
    if not user_msg or not prior_seven_msg:
        return None
    kind, trigger = classify(user_msg)
    if not kind:
        return None
    _init()
    lid = _gen_id()
    now = int(time.time())
    user_clip = (user_msg or '')[:600]
    seven_clip = (prior_seven_msg or '')[:600]
    weight = 1.5 if PROFANE_NEG.search(user_msg or '') else 1.0
    # cheap context distillation: first sentence of Seven's reply
    hint = (prior_seven_msg or '').strip().split('.', 1)[0][:240]
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO seven_learnings "
            "(lesson_id, ts, kind, trigger, user_msg, seven_msg, weight, tags, created_at, context_hint) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (lid, now, kind, trigger, user_clip, seven_clip, weight, '', now, hint),
        )
        conn.commit()
        return {
            'lesson_id': lid, 'ts': now, 'kind': kind, 'trigger': trigger,
            'user_msg': user_clip, 'seven_msg': seven_clip, 'weight': weight,
            'context_hint': hint,
        }
    finally:
        conn.close()


def recent(limit: int = 5, kind: str | None = None) -> list[dict]:
    _init()
    conn = _connect()
    try:
        if kind:
            rows = conn.execute(
                "SELECT * FROM seven_learnings WHERE kind=? ORDER BY ts DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM seven_learnings ORDER BY ts DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def stats() -> dict:
    _init()
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM seven_learnings").fetchone()['c']
        pos = conn.execute("SELECT COUNT(*) AS c FROM seven_learnings WHERE kind='positive'").fetchone()['c']
        neg = conn.execute("SELECT COUNT(*) AS c FROM seven_learnings WHERE kind='negative'").fetchone()['c']
        return {'total': total, 'positive': pos, 'negative': neg}
    finally:
        conn.close()


def recent_lessons_block(limit: int = 4) -> str:
    """Compact LLM-friendly block. Negatives first (they bind harder)."""
    neg = recent(limit=limit, kind='negative')
    pos = recent(limit=max(1, limit // 2), kind='positive')
    if not neg and not pos:
        return "(no learned lessons yet — Seven is fresh)"
    lines = []
    if neg:
        lines.append("Recent corrections (do NOT repeat):")
        for l in neg:
            lines.append(f"  ✗ '{l['trigger']}' on: {l.get('context_hint') or l['seven_msg'][:160]}")
    if pos:
        lines.append("Recent wins (keep doing this):")
        for l in pos:
            lines.append(f"  ✓ '{l['trigger']}' on: {l.get('context_hint') or l['seven_msg'][:160]}")
    return '\n'.join(lines)


def summary_for_seven() -> dict:
    s = stats()
    last = recent(limit=1)
    return {
        'pillar': 'self-learning',
        'ok': True,
        'total': s['total'],
        'positive': s['positive'],
        'negative': s['negative'],
        'last_ts': last[0]['ts'] if last else 0,
    }
