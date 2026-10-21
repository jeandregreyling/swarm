"""core.seven.memory — Seven's three memory stores.

Memory model
============

Episodic memory (``seven_episodes``)
    Append-only stream of *events* Seven observed. One row per ledger
    entry, observation snapshot, or reasoning act. Always carries a
    timestamp, a source, and (when applicable) a (kind, record_id) pair
    plus a salience in 0..1 used by recall ordering.

Semantic memory (``seven_concepts``)
    Slow-changing knowledge about the *system itself*. Seeded from
    ``docs/seven/*.md`` so future agents (and humans) can teach Seven by
    editing markdown. Each concept has a slug, a title, a body, and tags.

Beliefs (``seven_beliefs``)
    Compact subject-predicate-object triples Seven derives from episodes.
    Examples::
        ("step:S-XYZ",        "is_stale",   "true")          conf 0.9
        ("kind:note:B-...",   "is_hub",     "true")          conf 0.6
        ("packet:PACKET-09",  "is_active",  "true")          conf 1.0
    Beliefs are evidence-counted; conflicting evidence reduces confidence
    rather than overwriting outright.

Attention (``seven_attention``)
    Working-memory rolling counter — what records Seven has touched
    recently. Drives "what's hot right now" without re-scanning the graph.

All four stores live in ``swarm_memory.db`` so they back-up alongside the
rest of the swarm. They are created lazily on first use; nothing else has
to be migrated for Seven's brain to come online.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

from utils.db._connection import get_connection


# ── lazy schema init ────────────────────────────────────────────────────────

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS seven_episodes (
        episode_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        ts            REAL    NOT NULL,
        source        TEXT    NOT NULL,
        kind          TEXT,
        record_id     TEXT,
        action        TEXT,
        actor         TEXT,
        salience      REAL    DEFAULT 0.5,
        payload_json  TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_seven_episodes_record ON seven_episodes(kind, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_seven_episodes_ts ON seven_episodes(ts DESC)",
    """
    CREATE TABLE IF NOT EXISTS seven_concepts (
        slug         TEXT PRIMARY KEY,
        title        TEXT NOT NULL,
        body_md      TEXT NOT NULL,
        tags         TEXT,
        source_path  TEXT,
        updated_at   REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS seven_beliefs (
        belief_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        subject        TEXT NOT NULL,
        predicate      TEXT NOT NULL,
        object         TEXT,
        confidence     REAL NOT NULL,
        evidence_count INTEGER DEFAULT 1,
        first_seen     REAL,
        last_seen      REAL,
        UNIQUE(subject, predicate, object)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_seven_beliefs_subj ON seven_beliefs(subject)",
    "CREATE INDEX IF NOT EXISTS idx_seven_beliefs_pred ON seven_beliefs(predicate)",
    """
    CREATE TABLE IF NOT EXISTS seven_attention (
        record_id   TEXT PRIMARY KEY,
        kind        TEXT,
        hits        INTEGER DEFAULT 1,
        last_seen   REAL
    )
    """,
]

_INIT_DONE = False


def ensure_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create Seven's memory tables if missing. Cheap on subsequent calls."""
    global _INIT_DONE
    if _INIT_DONE:
        return
    own = conn is None
    c = conn or get_connection()
    try:
        for stmt in _SCHEMA:
            c.execute(stmt)
        c.commit()
        _INIT_DONE = True
    finally:
        if own:
            try:
                c.close()
            except Exception:
                pass


@contextmanager
def _conn():
    ensure_schema()
    c = get_connection()
    try:
        yield c
    finally:
        try:
            c.close()
        except Exception:
            pass


# ── episodic ────────────────────────────────────────────────────────────────

def append_episode(
    *,
    source: str,
    kind: Optional[str] = None,
    record_id: Optional[str] = None,
    action: Optional[str] = None,
    actor: str = "system",
    salience: float = 0.5,
    payload: Optional[Dict[str, Any]] = None,
    ts: Optional[float] = None,
) -> int:
    """Insert one episode. Returns the new episode_id."""
    salience = max(0.0, min(1.0, float(salience)))
    payload_json = json.dumps(payload, default=str) if payload else None
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO seven_episodes
               (ts, source, kind, record_id, action, actor, salience, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                float(ts if ts is not None else time.time()),
                source, kind, record_id, action, actor, salience, payload_json,
            ),
        )
        c.commit()
        eid = cur.lastrowid
    if record_id:
        bump_attention(record_id, kind)
    return int(eid or 0)


def recall_episodes(
    *,
    kind: Optional[str] = None,
    record_id: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    sql = "SELECT episode_id, ts, source, kind, record_id, action, actor, salience, payload_json FROM seven_episodes"
    where: List[str] = []
    args: List[Any] = []
    if kind is not None:
        where.append("kind = ?"); args.append(kind)
    if record_id is not None:
        where.append("record_id = ?"); args.append(record_id)
    if source is not None:
        where.append("source = ?"); args.append(source)
    if since is not None:
        where.append("ts >= ?"); args.append(float(since))
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(int(limit))
    out: List[Dict[str, Any]] = []
    with _conn() as c:
        for row in c.execute(sql, args).fetchall():
            payload = None
            if row[8]:
                try:
                    payload = json.loads(row[8])
                except Exception:
                    payload = None
            out.append({
                "episode_id": row[0], "ts": row[1], "source": row[2],
                "kind": row[3], "record_id": row[4], "action": row[5],
                "actor": row[6], "salience": row[7], "payload": payload,
            })
    return out


# ── attention (working memory) ──────────────────────────────────────────────

def bump_attention(record_id: str, kind: Optional[str] = None, *, by: int = 1) -> None:
    if not record_id:
        return
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO seven_attention(record_id, kind, hits, last_seen)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(record_id) DO UPDATE SET
                   hits = hits + excluded.hits,
                   last_seen = excluded.last_seen,
                   kind = COALESCE(excluded.kind, kind)""",
            (record_id, kind, int(by), now),
        )
        c.commit()


def hot_records(limit: int = 10) -> List[Dict[str, Any]]:
    """Records Seven has touched most-and-most-recently. Cheap working set."""
    sql = """SELECT record_id, kind, hits, last_seen FROM seven_attention
             ORDER BY (hits * 1.0 / (1 + (? - last_seen)/86400.0)) DESC
             LIMIT ?"""
    with _conn() as c:
        rows = c.execute(sql, (time.time(), int(limit))).fetchall()
    return [
        {"record_id": r[0], "kind": r[1], "hits": int(r[2]), "last_seen": r[3]}
        for r in rows
    ]


# ── beliefs ─────────────────────────────────────────────────────────────────

def assert_belief(
    subject: str,
    predicate: str,
    obj: Optional[str] = None,
    *,
    confidence: float = 0.7,
    evidence_delta: int = 1,
) -> None:
    """Upsert a belief. Repeated assertions raise evidence_count and pull
    confidence toward the asserted value (Bayesian-ish, not actual Bayes)."""
    confidence = max(0.0, min(1.0, float(confidence)))
    now = time.time()
    with _conn() as c:
        row = c.execute(
            "SELECT belief_id, confidence, evidence_count FROM seven_beliefs WHERE subject=? AND predicate=? AND IFNULL(object,'')=IFNULL(?,'')",
            (subject, predicate, obj),
        ).fetchone()
        if row is None:
            c.execute(
                """INSERT INTO seven_beliefs
                   (subject, predicate, object, confidence, evidence_count, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (subject, predicate, obj, confidence, evidence_delta, now, now),
            )
        else:
            old_id, old_conf, old_n = row
            new_n = max(1, int(old_n) + int(evidence_delta))
            # weighted average toward asserted value
            new_conf = ((float(old_conf) * old_n) + (confidence * abs(evidence_delta))) / (old_n + abs(evidence_delta))
            c.execute(
                "UPDATE seven_beliefs SET confidence=?, evidence_count=?, last_seen=? WHERE belief_id=?",
                (max(0.0, min(1.0, new_conf)), new_n, now, old_id),
            )
        c.commit()


def retract_belief(subject: str, predicate: str, obj: Optional[str] = None) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM seven_beliefs WHERE subject=? AND predicate=? AND IFNULL(object,'')=IFNULL(?,'')",
            (subject, predicate, obj),
        )
        c.commit()


def beliefs_about(
    subject: Optional[str] = None,
    *,
    predicate: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    sql = "SELECT subject, predicate, object, confidence, evidence_count, first_seen, last_seen FROM seven_beliefs"
    where: List[str] = []
    args: List[Any] = []
    if subject is not None:
        where.append("subject = ?"); args.append(subject)
    if predicate is not None:
        where.append("predicate = ?"); args.append(predicate)
    if min_confidence > 0:
        where.append("confidence >= ?"); args.append(float(min_confidence))
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY confidence DESC, last_seen DESC LIMIT ?"
    args.append(int(limit))
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [
        {
            "subject": r[0], "predicate": r[1], "object": r[2],
            "confidence": r[3], "evidence_count": int(r[4]),
            "first_seen": r[5], "last_seen": r[6],
        }
        for r in rows
    ]


# ── semantic / concepts ─────────────────────────────────────────────────────

def upsert_concept(
    slug: str, title: str, body_md: str,
    *, tags: Optional[Iterable[str]] = None, source_path: Optional[str] = None,
) -> None:
    tag_str = ",".join(sorted({t.strip() for t in (tags or []) if t.strip()})) or None
    now = time.time()
    with _conn() as c:
        c.execute(
            """INSERT INTO seven_concepts(slug, title, body_md, tags, source_path, updated_at)
               VALUES(?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                   title=excluded.title,
                   body_md=excluded.body_md,
                   tags=excluded.tags,
                   source_path=excluded.source_path,
                   updated_at=excluded.updated_at""",
            (slug, title, body_md, tag_str, source_path, now),
        )
        c.commit()


def get_concept(slug: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute(
            "SELECT slug, title, body_md, tags, source_path, updated_at FROM seven_concepts WHERE slug=?",
            (slug,),
        ).fetchone()
    if not row:
        return None
    return {
        "slug": row[0], "title": row[1], "body_md": row[2],
        "tags": (row[3] or "").split(",") if row[3] else [],
        "source_path": row[4], "updated_at": row[5],
    }


def list_concepts(tag: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    sql = "SELECT slug, title, tags, source_path, updated_at FROM seven_concepts"
    args: List[Any] = []
    if tag:
        sql += " WHERE tags LIKE ?"; args.append(f"%{tag}%")
    sql += " ORDER BY slug LIMIT ?"; args.append(int(limit))
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [
        {
            "slug": r[0], "title": r[1],
            "tags": (r[2] or "").split(",") if r[2] else [],
            "source_path": r[3], "updated_at": r[4],
        }
        for r in rows
    ]


def search_concepts(query: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Cheap LIKE search across slug/title/body. Good enough for KC lookup."""
    if not query:
        return list_concepts(limit=limit)
    q = f"%{query.strip()}%"
    sql = """SELECT slug, title, tags, source_path, updated_at FROM seven_concepts
             WHERE slug LIKE ? OR title LIKE ? OR body_md LIKE ? OR IFNULL(tags,'') LIKE ?
             ORDER BY (CASE WHEN title LIKE ? THEN 0 ELSE 1 END), slug
             LIMIT ?"""
    with _conn() as c:
        rows = c.execute(sql, (q, q, q, q, q, int(limit))).fetchall()
    return [
        {
            "slug": r[0], "title": r[1],
            "tags": (r[2] or "").split(",") if r[2] else [],
            "source_path": r[3], "updated_at": r[4],
        }
        for r in rows
    ]


# ── summary helpers (used by reasoning + API) ───────────────────────────────

def memory_stats() -> Dict[str, Any]:
    with _conn() as c:
        ep = c.execute("SELECT COUNT(*), MAX(ts) FROM seven_episodes").fetchone()
        co = c.execute("SELECT COUNT(*) FROM seven_concepts").fetchone()
        be = c.execute("SELECT COUNT(*) FROM seven_beliefs").fetchone()
        at = c.execute("SELECT COUNT(*) FROM seven_attention").fetchone()
    return {
        "episodes": int(ep[0] or 0),
        "last_episode_ts": ep[1],
        "concepts": int(co[0] or 0),
        "beliefs": int(be[0] or 0),
        "attention_records": int(at[0] or 0),
    }
