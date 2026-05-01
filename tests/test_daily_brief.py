"""tests/test_daily_brief.py — Seven's daily prose narrative."""
from __future__ import annotations

import os
import sys
import sqlite3
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'frontend'))


def _seed_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    monkeypatch.setenv('SWARM_MEMORY_DB', tmp.name)
    monkeypatch.setenv('SWARM_DB_PATH', tmp.name)

    # Force module re-init.
    import importlib
    for mod in ('core.witness', 'core.curiosity', 'agents.seven.learnings',
                'agents.seven.daily_brief'):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])

    from core import witness, curiosity
    from agents.seven import learnings
    witness._INIT_DONE = False  # type: ignore[attr-defined]
    curiosity._INIT_DONE = False  # type: ignore[attr-defined]
    learnings._INIT_DONE = False  # type: ignore[attr-defined]

    # Seed: callouts via witness, curiosity question, learning, belief.
    witness.review_user_msg("This should work probably, will fix later.", save=True)
    witness.review_seven_response("Maybe it'll work, TBD.", user_msg="?", save=True)
    curiosity.ask('seven', 'why does the build flap on cold start?', salience=0.8)

    # Belief: must use seven_beliefs schema. Create row directly.
    con = sqlite3.connect(tmp.name)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS seven_beliefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT, predicate TEXT, object TEXT,
            confidence REAL DEFAULT 0.5,
            first_seen REAL, last_seen REAL
        );
        CREATE TABLE IF NOT EXISTS seven_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, kind TEXT, record_id TEXT, action TEXT, actor TEXT
        );
    """)
    now = time.time()
    con.execute(
        "INSERT INTO seven_beliefs(subject,predicate,object,confidence,first_seen,last_seen) "
        "VALUES (?,?,?,?,?,?)",
        ('build', 'is', 'green', 0.9, now, now))
    con.execute(
        "INSERT INTO seven_episodes(ts,kind,record_id,action,actor) VALUES (?,?,?,?,?)",
        (now, 'belief', 'belief#1', 'created', 'seven'))
    con.commit()
    con.close()
    return tmp.name


def test_compose_daily_returns_prose(monkeypatch, tmp_path):
    _seed_db(monkeypatch)
    # Redirect AUDIT to tmp so we don't pollute the repo.
    from agents.seven import daily_brief
    monkeypatch.setattr(daily_brief, 'AUDIT', tmp_path)

    out = daily_brief.compose_daily()
    assert 'date' in out and 'path' in out and 'body' in out
    body = out['body']

    # Expected section headers.
    assert "# Seven's Daily Brief" in body
    assert '## Conviction' in body
    assert '## Build hygiene' in body
    assert '## What happened' in body
    assert '## What I now hold to be true' in body
    assert "## What I'm still wondering about" in body
    assert '## How the conversation went' in body
    assert '## Bullshit ledger' in body

    # File written.
    p = Path(out['path'])
    assert p.exists() and p.read_text() == body

    # Summary string compiled.
    assert 'episodes=' in out['summary']
    assert 'callouts_user=' in out['summary']


def test_last_brief_finds_written(monkeypatch, tmp_path):
    _seed_db(monkeypatch)
    from agents.seven import daily_brief
    monkeypatch.setattr(daily_brief, 'AUDIT', tmp_path)
    daily_brief.compose_daily()
    found = daily_brief.last_brief()
    assert found is not None
    assert "Seven's Daily Brief" in found['body']
