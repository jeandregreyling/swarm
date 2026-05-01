"""tests/test_seven_training.py — PACKET-10B real training (no slash codes).

Seven must understand natural language about himself and his curiosity inbox,
without secret-handshake commands. These tests drive the actual chat() entry
point that the frontend reaches via /api/chat.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_UTILS = ROOT / 'utils'
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))


def _seed_brain(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS seven_episodes (
            episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL, source TEXT NOT NULL, kind TEXT,
            record_id TEXT, action TEXT, actor TEXT,
            salience REAL DEFAULT 0.5, payload_json TEXT
        );
        CREATE TABLE IF NOT EXISTS seven_beliefs (
            belief_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT,
            confidence REAL NOT NULL, evidence_count INTEGER DEFAULT 1,
            first_seen REAL, last_seen REAL,
            UNIQUE(subject, predicate, object)
        );
        """
    )
    # Seed bedrock identity
    seeds = [
        ("seven", "is_a", "personal_swarm_companion", 1.0),
        ("seven", "motto", "Not a system that REPORTS. A system that DOES.", 1.0),
        ("seven", "principal_user", "jean-andre", 1.0),
        ("seven", "prime_directive", "serve motion not memory", 0.95),
    ]
    for s, p, o, c in seeds:
        con.execute(
            "INSERT INTO seven_beliefs (subject,predicate,object,confidence,evidence_count,first_seen,last_seen) "
            "VALUES (?,?,?,?,1,0,0)",
            (s, p, o, c),
        )
    con.commit()
    con.close()


@pytest.fixture
def fresh_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _seed_brain(path)
    monkeypatch.setenv("SWARM_MEMORY_DB", path)
    # Force re-import of curiosity so it picks up the env
    for m in list(sys.modules):
        if m.startswith('core.curiosity'):
            del sys.modules[m]
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ── _compose deterministic-path tests (these are what /api/chat triggers) ────


def test_natural_language_who_are_you_returns_identity_from_beliefs(monkeypatch, fresh_db):
    """'who are you' must pull from seven_beliefs, not a hardcoded string."""
    # Patch database.get_connection to point at our temp DB
    import database
    orig = database.get_connection
    monkeypatch.setattr(database, 'get_connection',
                        lambda: sqlite3.connect(os.environ['SWARM_MEMORY_DB']))
    # Make sqlite return rows with .keys()
    def conn_factory():
        c = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(database, 'get_connection', conn_factory)

    from agents.seven import seven_agent
    # Reload so it picks up patched get_connection if it's imported lazily
    state = seven_agent._read_state()
    out, _ = seven_agent._compose("who are you?", state, [])
    assert out is not None
    assert 'Seven' in out
    # Pulled from belief store, not hard-coded answer
    assert 'jean-andre' in out
    assert 'personal_swarm_companion' in out or 'is_a' in out


def test_natural_language_what_are_you_asking_shows_inbox(monkeypatch, fresh_db):
    """'what are you asking' must show the curiosity inbox."""
    def conn_factory():
        c = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
        c.row_factory = sqlite3.Row
        return c
    import database
    monkeypatch.setattr(database, 'get_connection', conn_factory)

    from core import curiosity
    qid = curiosity.ask('seven', 'is the natural language path working?', salience=0.95)

    from agents.seven import seven_agent
    out, _ = seven_agent._compose("what are you wondering about?", seven_agent._read_state(), [])
    assert out is not None
    assert f'#{qid}' in out
    assert 'natural language path' in out


def test_inline_answer_promotes_to_belief(monkeypatch, fresh_db):
    """Replying '#3 my answer' should answer the question and promote a belief."""
    def conn_factory():
        c = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
        c.row_factory = sqlite3.Row
        return c
    import database
    monkeypatch.setattr(database, 'get_connection', conn_factory)

    from core import curiosity
    qid = curiosity.ask('seven', 'what is the test answer?', salience=0.9)

    from agents.seven import seven_agent
    out, _ = seven_agent._compose(f"#{qid} the test answer is forty two",
                                   seven_agent._read_state(), [])
    assert out is not None
    assert 'Answered' in out or 'answered' in out
    assert 'forty two' in out
    assert 'belief' in out.lower()

    # Verify in DB
    con = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
    rows = con.execute(
        "SELECT object, confidence FROM seven_beliefs WHERE object LIKE '%forty two%'"
    ).fetchall()
    con.close()
    assert rows, f"belief was not created · all beliefs: {rows}"
    assert rows[0][1] >= 0.9


def test_inline_answer_handles_unknown_id_gracefully(monkeypatch, fresh_db):
    def conn_factory():
        c = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
        c.row_factory = sqlite3.Row
        return c
    import database
    monkeypatch.setattr(database, 'get_connection', conn_factory)

    from agents.seven import seven_agent
    out, _ = seven_agent._compose("#99999 nonsense answer",
                                   seven_agent._read_state(), [])
    assert out is not None
    assert 'couldn' in out.lower() or 'never existed' in out.lower() or 'already' in out.lower()


def test_normal_message_falls_through_to_llm(monkeypatch, fresh_db):
    """An ordinary message should NOT match identity or curiosity probes."""
    def conn_factory():
        c = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
        c.row_factory = sqlite3.Row
        return c
    import database
    monkeypatch.setattr(database, 'get_connection', conn_factory)

    from agents.seven import seven_agent
    # Returns (None, 0) when no template matches → caller routes to LLM
    out, _ = seven_agent._compose("hey can you help me write a python function",
                                   seven_agent._read_state(), [])
    assert out is None


def test_status_block_still_works_for_status_words(monkeypatch, fresh_db):
    """Old 'status'/'queue' deterministic path must still work."""
    def conn_factory():
        c = sqlite3.connect(os.environ['SWARM_MEMORY_DB'])
        c.row_factory = sqlite3.Row
        return c
    import database
    monkeypatch.setattr(database, 'get_connection', conn_factory)

    from agents.seven import seven_agent
    out, _ = seven_agent._compose("what's the queue status?",
                                   seven_agent._read_state(), [])
    assert out is not None
    # Should produce a state read; key thing is it didn't return None
    assert isinstance(out, str) and len(out) > 10
