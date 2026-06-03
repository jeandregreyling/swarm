"""Read-only contracts for the Knowledge Center brain tables."""
from __future__ import annotations

import sqlite3
from typing import Any


BRAIN_TABLE_CONTRACTS: dict[str, dict[str, Any]] = {
    'project_docs': {
        'owner': 'knowledge_center',
        'layer': 'artifact',
        'purpose': 'Human-readable KC and Studio artifacts.',
        'required_columns': {'id', 'doc_name', 'content', 'updated_at', 'tags'},
    },
    'knowledge_sources': {
        'owner': 'knowledge_center',
        'layer': 'retrieval_source',
        'purpose': 'Canonical ingest source metadata before chunking.',
        'required_columns': {'source_id', 'title', 'source_type', 'status', 'chunk_count', 'updated_at'},
    },
    'knowledge_chunks': {
        'owner': 'knowledge_center',
        'layer': 'retrieval_index',
        'purpose': 'Searchable source chunks used by KC retrieval.',
        'required_columns': {'source_id', 'chunk_text', 'created_at'},
    },
    'swarm_knowledge': {
        'owner': 'swarm_brain',
        'layer': 'durable_fact',
        'purpose': 'Durable facts, lessons, warnings, decisions, and patterns.',
        'required_columns': {'id', 'key', 'content', 'source_agent', 'category', 'importance', 'updated_at'},
    },
    'memory': {
        'owner': 'memory',
        'layer': 'shared_memory',
        'purpose': 'Shared memories with provenance and archive state.',
        'required_columns': {'id', 'agent', 'subject', 'content', 'importance', 'created_at', 'archived'},
    },
    'user_interests': {
        'owner': 'interests',
        'layer': 'preference_signal',
        'purpose': 'User and agent-suggested interests with source provenance.',
        'required_columns': {'id', 'username', 'topic', 'category', 'source', 'score', 'active', 'updated_at', 'source_agent'},
    },
    'watched_topic_settings': {
        'owner': 'tasker',
        'layer': 'interest_schedule',
        'purpose': 'Durable watched-topic cadence and digest settings.',
        'required_columns': {'topic_key', 'updated_at'},
    },
    'watched_topic_evidence': {
        'owner': 'tasker',
        'layer': 'interest_evidence',
        'purpose': 'Scored evidence produced by watched-topic research.',
        'required_columns': {'id', 'topic_key', 'topic', 'evidence_fingerprint', 'qualified', 'updated_at'},
    },
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    try:
        return int(conn.execute(sql, args).fetchone()[0] or 0)
    except sqlite3.OperationalError:
        return 0


def inspect_table_contracts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return ownership and required-column coverage for brain tables."""
    tables = {}
    missing_tables = []
    missing_columns = {}
    for table, spec in BRAIN_TABLE_CONTRACTS.items():
        present = _table_exists(conn, table)
        cols = _columns(conn, table)
        required = set(spec['required_columns'])
        missing = sorted(required - cols)
        if not present:
            missing_tables.append(table)
        if missing:
            missing_columns[table] = missing
        tables[table] = {
            'present': present,
            'owner': spec['owner'],
            'layer': spec['layer'],
            'purpose': spec['purpose'],
            'required_columns': sorted(required),
            'missing_columns': missing,
        }
    return {
        'ok': not missing_tables and not missing_columns,
        'tables': tables,
        'missing_tables': missing_tables,
        'missing_columns': missing_columns,
    }


def inspect_retrieval_health(conn: sqlite3.Connection) -> dict[str, Any]:
    """Check source/chunk linkage without changing ingest state."""
    if not _table_exists(conn, 'knowledge_sources') or not _table_exists(conn, 'knowledge_chunks'):
        return {
            'ok': False,
            'source_count': _count(conn, 'SELECT COUNT(*) FROM knowledge_sources') if _table_exists(conn, 'knowledge_sources') else 0,
            'chunk_count': _count(conn, 'SELECT COUNT(*) FROM knowledge_chunks') if _table_exists(conn, 'knowledge_chunks') else 0,
            'missing_index_table': True,
        }
    source_cols = _columns(conn, 'knowledge_sources')
    source_id = 'source_id' if 'source_id' in source_cols else 'id'
    chunk_cols = _columns(conn, 'knowledge_chunks')
    chunk_id = 'chunk_id' if 'chunk_id' in chunk_cols else 'id'
    source_count = _count(conn, 'SELECT COUNT(*) FROM knowledge_sources')
    chunk_count = _count(conn, 'SELECT COUNT(*) FROM knowledge_chunks')
    orphan_chunks = _count(
        conn,
        f"""SELECT COUNT(*) FROM knowledge_chunks c
            LEFT JOIN knowledge_sources s ON s.{source_id}=c.source_id
            WHERE s.{source_id} IS NULL""",
    )
    unchunked_sources = _count(
        conn,
        f"""SELECT COUNT(*) FROM (
              SELECT s.{source_id}
              FROM knowledge_sources s
              LEFT JOIN knowledge_chunks c ON c.source_id=s.{source_id}
              WHERE COALESCE(s.status,'active')='active'
              GROUP BY s.{source_id}
              HAVING COUNT(c.{chunk_id})=0
            )""",
    )
    chunk_count_mismatch = 0
    if 'chunk_count' in source_cols:
        chunk_count_mismatch = _count(
            conn,
            f"""SELECT COUNT(*) FROM (
                  SELECT s.{source_id}, COALESCE(s.chunk_count,0) expected, COUNT(c.{chunk_id}) actual
                  FROM knowledge_sources s
                  LEFT JOIN knowledge_chunks c ON c.source_id=s.{source_id}
                  GROUP BY s.{source_id}
                ) WHERE expected != actual""",
        )
    return {
        'ok': orphan_chunks == 0 and unchunked_sources == 0 and chunk_count_mismatch == 0,
        'source_count': source_count,
        'chunk_count': chunk_count,
        'orphan_chunks': orphan_chunks,
        'unchunked_active_sources': unchunked_sources,
        'chunk_count_mismatch': chunk_count_mismatch,
    }


def inspect_memory_provenance(conn: sqlite3.Connection) -> dict[str, Any]:
    """Check memory table provenance columns and shared-memory provenance rows."""
    memory_tables = [
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'memory%' ORDER BY name"
        ).fetchall()
    ]
    missing_columns = {}
    for table in memory_tables:
        cols = _columns(conn, table)
        required = {'agent', 'content', 'importance', 'created_at', 'archived'}
        if table == 'memory' or 'subject' in cols:
            required.add('subject')
        missing = sorted(required - cols)
        if missing:
            missing_columns[table] = missing
    shared_unknown_source = 0
    shared_unverified = 0
    if _table_exists(conn, 'memory'):
        cols = _columns(conn, 'memory')
        if 'source' in cols:
            shared_unknown_source = _count(
                conn,
                "SELECT COUNT(*) FROM memory WHERE archived=0 AND COALESCE(source,'unknown') IN ('','unknown')",
            )
        if 'verified' in cols:
            shared_unverified = _count(
                conn,
                "SELECT COUNT(*) FROM memory WHERE archived=0 AND COALESCE(verified,'0') IN ('','0',0)",
            )
    return {
        'ok': not missing_columns,
        'table_count': len(memory_tables),
        'missing_columns': missing_columns,
        'shared_unknown_source': shared_unknown_source,
        'shared_unverified': shared_unverified,
    }


def inspect_interest_quality(conn: sqlite3.Connection) -> dict[str, Any]:
    """Summarize interest provenance quality and weak signal rows."""
    if not _table_exists(conn, 'user_interests'):
        return {'ok': False, 'active': 0, 'missing_table': True}
    by_source = {
        row[0] or '': int(row[1] or 0)
        for row in conn.execute(
            "SELECT COALESCE(source,''), COUNT(*) FROM user_interests WHERE active=1 GROUP BY COALESCE(source,'')"
        ).fetchall()
    }
    active = sum(by_source.values())
    durable = sum(by_source.get(src, 0) for src in ('user', 'manual', 'seed', 'newsletter_feedback'))
    weak_agent_rows = _count(
        conn,
        "SELECT COUNT(*) FROM user_interests "
        "WHERE active=1 AND source='agent' AND COALESCE(source_agent,'')=''",
    )
    unknown_source_rows = _count(
        conn,
        "SELECT COUNT(*) FROM user_interests "
        "WHERE active=1 AND COALESCE(source,'') NOT IN ('user','manual','seed','agent','media_center','newsletter_feedback')",
    )
    watched_without_interests = 0
    if _table_exists(conn, 'watched_topic_settings'):
        watched_without_interests = _count(
            conn,
            """SELECT COUNT(*) FROM watched_topic_settings s
               WHERE NOT EXISTS (
                 SELECT 1 FROM user_interests i
                 WHERE i.active=1
                   AND lower(replace(i.topic,' ','_')) = lower(s.topic_key)
               )""",
        )
    return {
        'ok': weak_agent_rows == 0 and unknown_source_rows == 0 and (active == 0 or durable > 0),
        'active': active,
        'durable_source_count': durable,
        'by_source': by_source,
        'weak_agent_rows': weak_agent_rows,
        'unknown_source_rows': unknown_source_rows,
        'watched_without_exact_interest': watched_without_interests,
    }
