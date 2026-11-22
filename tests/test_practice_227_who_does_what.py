import sqlite3
import pytest

from core.hb_roles import model_for_job

# Helper to create an in-memory database with the expected schema

def make_db(rows):
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE hb_model_jobs (
            agent_id TEXT,
            job TEXT,
            passed INTEGER,
            tok_s INTEGER,
            where_runs TEXT
        );
        """
    )
    cur.executemany(
        "INSERT INTO hb_model_jobs (agent_id, job, passed, tok_s, where_runs) VALUES (?, ?, ?, ?, ?)" ,
        rows,
    )
    conn.commit()
    return conn

# Test that the fastest passing agent is returned

def test_fastest_passing_agent():
    rows = [
        ("agent_a", "router", 1, 100, "run1"),
        ("agent_b", "router", 1, 80, "run2"),  # faster
        ("agent_c", "router", 0, 70, "run3"),  # did not pass
    ]
    conn = make_db(rows)
    assert model_for_job(conn, "router") == "agent_b"

# Test that a decommission candidate is never returned

def test_decommission_candidate_not_returned():
    rows = [
        ("agent_a", "router", 0, 100, "run1"),
        ("agent_b", "router", 0, 80, "run2"),
    ]
    conn = make_db(rows)
    # No passing agents, should fall back to role default
    assert model_for_job(conn, "router") is None

# Test that a job with no entries falls back to None

def test_no_entries():
    conn = make_db([])
    assert model_for_job(conn, "router") is None

# Test that the function ignores agents marked as decommission candidates

def test_ignore_decommission_candidates():
    rows = [
        ("agent_a", "router", 1, 100, "run1"),
        ("agent_b", "router", 1, 80, "run2"),
        ("agent_c", "router", 1, 70, "run3"),
    ]
    conn = make_db(rows)
    assert model_for_job(conn, "router") == "agent_b"
