"""
lib/knowledge/store.py — SQLite persistence for the Knowledge Library.

Two tables:
  knowledge_sources — one row per ingested document (email, PDF, text, URL)
  knowledge_chunks  — overlapping text windows + float embeddings per source

The SQLite connection reuses the swarm's existing db module so all operations
land in the same database file and benefit from the same connection pool.
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'utils'))

logger = logging.getLogger('seven.knowledge.store')

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS knowledge_sources (
        source_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT    NOT NULL,
        source_type TEXT    NOT NULL DEFAULT 'text',
        source_ref  TEXT,
        raw_text    TEXT,
        domain_tags TEXT    NOT NULL DEFAULT '[]',
        status      TEXT    NOT NULL DEFAULT 'active',
        added_by    TEXT    NOT NULL DEFAULT 'ghost',
        chunk_count INTEGER NOT NULL DEFAULT 0,
        created_at  DATETIME DEFAULT (datetime('now')),
        updated_at  DATETIME DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        chunk_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        chunk_text  TEXT    NOT NULL,
        embedding   TEXT,
        created_at  DATETIME DEFAULT (datetime('now')),
        FOREIGN KEY (source_id) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_kchunks_source ON knowledge_chunks(source_id)",
]


def _conn():
    from db import get_connection
    return get_connection()


def ensure_schema():
    conn = _conn()
    try:
        for stmt in _SCHEMA:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def add_source(title, source_type, raw_text, source_ref=None,
               domain_tags=None, added_by='ghost'):
    ensure_schema()
    conn = _conn()
    try:
        tags_json = json.dumps(domain_tags or [])
        cur = conn.execute(
            """INSERT INTO knowledge_sources
               (title, source_type, source_ref, raw_text, domain_tags, added_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, source_type, source_ref, raw_text, tags_json, added_by),
        )
        source_id = cur.lastrowid
        conn.commit()
        return source_id
    finally:
        conn.close()


def save_chunks(source_id, chunks_with_embeddings):
    """
    Persist (chunk_text, embedding_list_or_None) pairs for a source.
    Replaces any previously stored chunks for that source.
    """
    conn = _conn()
    try:
        conn.execute('DELETE FROM knowledge_chunks WHERE source_id=?', (source_id,))
        for i, (text, embedding) in enumerate(chunks_with_embeddings):
            emb_json = json.dumps(embedding) if embedding is not None else None
            conn.execute(
                """INSERT INTO knowledge_chunks
                   (source_id, chunk_index, chunk_text, embedding)
                   VALUES (?, ?, ?, ?)""",
                (source_id, i, text, emb_json),
            )
        conn.execute(
            """UPDATE knowledge_sources
               SET chunk_count=?, updated_at=datetime('now')
               WHERE source_id=?""",
            (len(chunks_with_embeddings), source_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_sources(status='active'):
    ensure_schema()
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT source_id, title, source_type, source_ref, domain_tags,
                      status, added_by, chunk_count, created_at
               FROM knowledge_sources
               WHERE status=? ORDER BY created_at DESC""",
            (status,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_source(source_id):
    conn = _conn()
    try:
        row = conn.execute(
            'SELECT * FROM knowledge_sources WHERE source_id=?', (source_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_source(source_id):
    conn = _conn()
    try:
        conn.execute('DELETE FROM knowledge_sources WHERE source_id=?', (source_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_chunks():
    """Return all chunks (with embeddings) from active sources for search."""
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT kc.chunk_id, kc.source_id, kc.chunk_index,
                      kc.chunk_text, kc.embedding,
                      ks.title, ks.source_type, ks.domain_tags
               FROM knowledge_chunks kc
               JOIN knowledge_sources ks ON ks.source_id = kc.source_id
               WHERE ks.status = 'active' AND kc.embedding IS NOT NULL"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def source_stats():
    """Return {total_sources, total_chunks, sources_by_type} for UI."""
    ensure_schema()
    conn = _conn()
    try:
        total_s = conn.execute(
            "SELECT COUNT(*) FROM knowledge_sources WHERE status='active'"
        ).fetchone()[0]
        total_c = conn.execute(
            """SELECT SUM(kc.chunk_id) FROM knowledge_chunks kc
               JOIN knowledge_sources ks ON ks.source_id=kc.source_id
               WHERE ks.status='active'"""
        ).fetchone()[0] or 0
        by_type = {}
        for row in conn.execute(
            """SELECT source_type, COUNT(*) as n FROM knowledge_sources
               WHERE status='active' GROUP BY source_type"""
        ).fetchall():
            by_type[row['source_type']] = row['n']
        return {'total_sources': total_s, 'total_chunks': total_c, 'by_type': by_type}
    finally:
        conn.close()
