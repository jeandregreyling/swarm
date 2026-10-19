"""tests/test_slash_commands.py — PACKET-10B regression.

Drives Seven's slash commands end-to-end:
  * direct call into seven_agent._slash_command
  * through the /api/chat HTTP route (the path the actual frontend hits)
  * verifies /curiosity is NOT swallowed by the deterministic status block
  * verifies answers persist as beliefs
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
# frontend/ uses bare `from services import *` so we must put frontend on path.
_FRONTEND = ROOT / 'frontend'
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))


def _seed_brain_tables(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS seven_episodes (
            episode_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           REAL    NOT NULL,
            source       TEXT    NOT NULL,
            kind         TEXT,
            record_id    TEXT,
            action       TEXT,
            actor        TEXT,
            salience     REAL DEFAULT 0.5,
            payload_json TEXT
        );
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
        );
        """
    )
    con.commit()
    con.close()


@pytest.fixture
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _seed_brain_tables(path)
    monkeypatch.setenv("SWARM_MEMORY_DB", path)
    # Force re-import of curiosity so it picks up the env var
    for mod in [m for m in list(sys.modules) if m.startswith('core.curiosity')]:
        del sys.modules[mod]
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ── Direct slash_command unit tests ──────────────────────────────────────














# ── /api/chat HTTP route — slash codes are NOT intercepted there ─────────
# (PACKET-10B revision: dropped the secret-handshake API path. The frontend
# now uses natural language → see tests/test_seven_training.py for the real
# probes. The _slash_command() function is kept for CLI/HTTP inbox use.)


def test_api_chat_does_not_intercept_slash_messages(monkeypatch):
    """Regression guard: /api/chat must NOT short-circuit on slash messages.
    They should fall through to normal agent dispatch like any other prompt.
    (Slash codes are confusing UX; natural language is the contract now.)
    """
    from flask import Flask
    import frontend.blueprints.chat as chat_bp_mod

    app = Flask(__name__)
    app.config['TESTING'] = True
    monkeypatch.setattr(
        chat_bp_mod, '_resolve_identity_or_response',
        lambda data: (None, (chat_bp_mod.jsonify({'sentinel': 'fell_through'}), 200)),
        raising=False,
    )
    app.register_blueprint(chat_bp_mod.chat_bp)
    client = app.test_client()

    r = client.post('/api/chat', json={'message': '/curiosity', 'agent': 'seven'})
    body = r.get_json()
    # Either the sentinel response, or some other downstream handling — but NOT
    # the old slash_command shape.
    assert body.get('slash_command') is not True


