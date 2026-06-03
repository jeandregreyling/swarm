from __future__ import annotations

import sqlite3


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_table_contracts_report_missing_columns():
    from utils.db.brain_contracts import inspect_table_contracts

    conn = _conn()
    conn.execute("CREATE TABLE project_docs (id INTEGER PRIMARY KEY, doc_name TEXT, content TEXT)")
    try:
        out = inspect_table_contracts(conn)
    finally:
        conn.close()

    assert out["ok"] is False
    assert "project_docs" in out["missing_columns"]
    assert "updated_at" in out["missing_columns"]["project_docs"]
    assert "knowledge_sources" in out["missing_tables"]


def test_retrieval_health_catches_orphans_and_unchunked_sources():
    from utils.db.brain_contracts import inspect_retrieval_health

    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE knowledge_sources (
            source_id INTEGER PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'active',
            chunk_count INTEGER DEFAULT 0
        );
        CREATE TABLE knowledge_chunks (
            chunk_id INTEGER PRIMARY KEY,
            source_id INTEGER,
            chunk_text TEXT,
            created_at TEXT
        );
        INSERT INTO knowledge_sources (source_id, title, chunk_count) VALUES (1, 'one', 1);
        INSERT INTO knowledge_sources (source_id, title, chunk_count) VALUES (2, 'two', 0);
        INSERT INTO knowledge_chunks (source_id, chunk_text) VALUES (99, 'orphan');
        """
    )
    try:
        out = inspect_retrieval_health(conn)
    finally:
        conn.close()

    assert out["ok"] is False
    assert out["orphan_chunks"] == 1
    assert out["unchunked_active_sources"] == 2
    assert out["chunk_count_mismatch"] == 1


def test_memory_provenance_reports_missing_archive_columns():
    from utils.db.brain_contracts import inspect_memory_provenance

    conn = _conn()
    conn.execute("CREATE TABLE memory_qwen (id INTEGER PRIMARY KEY, agent TEXT, content TEXT, importance INTEGER, created_at TEXT)")
    try:
        out = inspect_memory_provenance(conn)
    finally:
        conn.close()

    assert out["ok"] is False
    assert out["missing_columns"]["memory_qwen"] == ["archived"]


def test_interest_quality_distinguishes_durable_and_weak_rows():
    from utils.db.brain_contracts import inspect_interest_quality

    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY,
            username TEXT,
            topic TEXT,
            category TEXT,
            source TEXT,
            source_agent TEXT,
            score REAL,
            active INTEGER
        );
        INSERT INTO user_interests VALUES (1, 'ghost', 'SAP', 'work', 'user', '', 10, 1);
        INSERT INTO user_interests VALUES (2, 'ghost', 'Rust', 'tech', 'agent', '', 5, 1);
        INSERT INTO user_interests VALUES (3, 'ghost', 'Mystery', 'general', 'strange', '', 1, 1);
        """
    )
    try:
        out = inspect_interest_quality(conn)
    finally:
        conn.close()

    assert out["ok"] is False
    assert out["durable_source_count"] == 1
    assert out["weak_agent_rows"] == 1
    assert out["unknown_source_rows"] == 1
