"""
lib/knowledge/store.py — SQLite persistence for the Knowledge Library.

Two tables:
  knowledge_sources — one row per ingested document (email, PDF, text, URL)
  knowledge_chunks  — overlapping text windows + float embeddings per source

The SQLite connection reuses the swarm's existing db module so all operations
land in the same database file and benefit from the same connection pool.
"""

import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'utils'))

logger = logging.getLogger('seven.knowledge.store')

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS knowledge_sources (
        source_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        title        TEXT    NOT NULL,
        source_type  TEXT    NOT NULL DEFAULT 'text',
        source_ref   TEXT,
        raw_text     TEXT,
        domain_tags  TEXT    NOT NULL DEFAULT '[]',
        category     TEXT    NOT NULL DEFAULT 'general',
        subcategory  TEXT,
        content_hash TEXT,
        status       TEXT    NOT NULL DEFAULT 'active',
        added_by     TEXT    NOT NULL DEFAULT 'ghost',
        chunk_count  INTEGER NOT NULL DEFAULT 0,
        created_at   DATETIME DEFAULT (datetime('now')),
        updated_at   DATETIME DEFAULT (datetime('now'))
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
    "CREATE INDEX IF NOT EXISTS idx_ksources_category ON knowledge_sources(category)",
    "CREATE INDEX IF NOT EXISTS idx_ksources_hash ON knowledge_sources(content_hash)",
]

# Columns added after initial release — ALTER TABLE is idempotent (errors ignored)
_MIGRATIONS = [
    "ALTER TABLE knowledge_sources ADD COLUMN category TEXT NOT NULL DEFAULT 'general'",
    "ALTER TABLE knowledge_sources ADD COLUMN subcategory TEXT",
    "ALTER TABLE knowledge_sources ADD COLUMN content_hash TEXT",
]


def _conn():
    from db import get_connection
    return get_connection()


def _hash_content(text):
    """SHA-256 of normalised text for dedup."""
    normalised = ' '.join((text or '').split()).strip().lower()
    return hashlib.sha256(normalised.encode('utf-8')).hexdigest()


def ensure_schema():
    conn = _conn()
    try:
        # 1. Create tables (skip indexes — columns may not exist yet on old DBs)
        for stmt in _SCHEMA:
            if 'CREATE INDEX' in stmt:
                continue
            conn.execute(stmt)
        # 2. Migrations: add columns that may be missing from pre-overhaul DBs
        for mig in _MIGRATIONS:
            try:
                conn.execute(mig)
            except Exception:
                pass  # column already exists
        # 3. Now create indexes (columns guaranteed present)
        for stmt in _SCHEMA:
            if 'CREATE INDEX' in stmt:
                conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def check_duplicate(raw_text):
    """Return existing source_id if content already exists, else None."""
    h = _hash_content(raw_text)
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT source_id FROM knowledge_sources WHERE content_hash=? AND status='active'",
            (h,),
        ).fetchone()
        return row['source_id'] if row else None
    finally:
        conn.close()


def add_source(title, source_type, raw_text, source_ref=None,
               domain_tags=None, added_by='ghost',
               category='general', subcategory=None):
    ensure_schema()
    content_hash = _hash_content(raw_text)
    conn = _conn()
    try:
        tags_json = json.dumps(domain_tags or [])
        cur = conn.execute(
            """INSERT INTO knowledge_sources
               (title, source_type, source_ref, raw_text, domain_tags,
                added_by, category, subcategory, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, source_type, source_ref, raw_text, tags_json,
             added_by, category or 'general', subcategory, content_hash),
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


def list_sources(status='active', category=None, subcategory=None,
                 order='created', limit=None):
    """List knowledge sources.

    order: 'created' (default — newest first by created_at) or
           'updated' (most recently touched first by updated_at).
    limit: optional integer cap on the number of rows returned.
    """
    ensure_schema()
    conn = _conn()
    try:
        sql = """SELECT source_id, title, source_type, source_ref, domain_tags,
                        status, added_by, chunk_count, created_at, updated_at,
                        category, subcategory
                 FROM knowledge_sources
                 WHERE status=?"""
        params = [status]
        if category:
            sql += " AND category=?"
            params.append(category)
        if subcategory:
            sql += " AND subcategory=?"
            params.append(subcategory)
        if order == 'updated':
            sql += " ORDER BY updated_at DESC"
        else:
            sql += " ORDER BY created_at DESC"
        if isinstance(limit, int) and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql, params).fetchall()
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


def update_source(source_id, *, title=None, category=None, subcategory=None, domain_tags=None):
    """Reclassify / rename a source. Only non-None fields are written.
    `domain_tags` may be a list (stored as JSON) or a string. `subcategory`
    may be '' to clear. Returns True if a row was touched, False if not found."""
    import json as _json
    fields = []
    params = []
    if title is not None:
        fields.append('title=?')
        params.append(str(title).strip() or 'Untitled')
    if category is not None:
        fields.append('category=?')
        params.append(str(category).strip() or 'general')
    if subcategory is not None:
        fields.append('subcategory=?')
        params.append(str(subcategory).strip() or None)
    if domain_tags is not None:
        if isinstance(domain_tags, (list, tuple, set)):
            tags_val = _json.dumps(list(domain_tags))
        else:
            tags_val = str(domain_tags or '[]')
        fields.append('domain_tags=?')
        params.append(tags_val)
    if not fields:
        return False
    fields.append("updated_at=datetime('now')")
    params.append(source_id)
    conn = _conn()
    try:
        cur = conn.execute(
            f"UPDATE knowledge_sources SET {', '.join(fields)} WHERE source_id=?",
            params,
        )
        conn.commit()
        return (cur.rowcount or 0) > 0
    finally:
        conn.close()


def get_all_chunks(category=None):
    """Return all chunks (with embeddings) from active sources for search."""
    conn = _conn()
    try:
        sql = """SELECT kc.chunk_id, kc.source_id, kc.chunk_index,
                        kc.chunk_text, kc.embedding,
                        ks.title, ks.source_type, ks.domain_tags,
                        ks.category, ks.subcategory
                 FROM knowledge_chunks kc
                 JOIN knowledge_sources ks ON ks.source_id = kc.source_id
                 WHERE ks.status = 'active' AND kc.embedding IS NOT NULL"""
        params = []
        if category:
            from lib.knowledge.categories import all_ids_for
            ids = all_ids_for(category)
            if ids:
                placeholders = ','.join('?' for _ in ids)
                sql += f" AND (ks.category IN ({placeholders}) OR ks.subcategory IN ({placeholders}))"
                params.extend(list(ids) * 2)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def source_stats():
    """Return {total_sources, total_chunks, sources_by_type, by_category} for UI."""
    ensure_schema()
    conn = _conn()
    try:
        total_s = conn.execute(
            "SELECT COUNT(*) FROM knowledge_sources WHERE status='active'"
        ).fetchone()[0]
        total_c = conn.execute(
            """SELECT COUNT(*) FROM knowledge_chunks kc
               JOIN knowledge_sources ks ON ks.source_id=kc.source_id
               WHERE ks.status='active'"""
        ).fetchone()[0] or 0
        by_type = {}
        for row in conn.execute(
            """SELECT source_type, COUNT(*) as n FROM knowledge_sources
               WHERE status='active' GROUP BY source_type"""
        ).fetchall():
            by_type[row['source_type']] = row['n']
        by_category = {}
        for row in conn.execute(
            """SELECT category, COUNT(*) as n FROM knowledge_sources
               WHERE status='active' GROUP BY category"""
        ).fetchall():
            by_category[row['category']] = row['n']
        return {
            'total_sources': total_s,
            'total_chunks': total_c,
            'by_type': by_type,
            'by_category': by_category,
        }
    finally:
        conn.close()
