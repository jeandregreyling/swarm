"""Phase 5 tests: agent-facing interests CRUD with provenance (utils/db/interests.py)."""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _fresh_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            source_agent TEXT DEFAULT '',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        );
    ''')
    return conn


from utils.db import interests as M  # noqa: E402


def test_whitelist_rejects_unknown_agent():
    conn = _fresh_conn()
    assert M.record_agent_interest('ghost', 'rust', source_agent='random', conn=conn) is False
    rows = conn.execute('SELECT COUNT(*) FROM user_interests').fetchone()
    assert rows[0] == 0


def test_whitelist_accepts_librarian_scholar_seeker():
    conn = _fresh_conn()
    for agent in ('librarian', 'scholar', 'seeker'):
        assert M.record_agent_interest('ghost', f'topic-{agent}', source_agent=agent, conn=conn)
    rows = conn.execute(
        "SELECT source, source_agent FROM user_interests ORDER BY topic"
    ).fetchall()
    assert len(rows) == 3
    for r in rows:
        assert r['source'] == 'agent'
        assert r['source_agent'] in {'librarian', 'scholar', 'seeker'}


def test_user_rows_never_relabelled_by_agent():
    conn = _fresh_conn()
    conn.execute(
        "INSERT INTO user_interests (username, topic, source, source_agent, score) "
        "VALUES ('ghost', 'python', 'user', '', 10.0)"
    )
    conn.commit()
    assert M.record_agent_interest('ghost', 'python', source_agent='scholar', conn=conn)
    row = conn.execute(
        "SELECT source, source_agent, score FROM user_interests WHERE topic='python'"
    ).fetchone()
    assert row['source'] == 'user'
    assert row['source_agent'] == ''
    assert row['score'] == 10.0


def test_agent_score_nudge_capped_at_9():
    conn = _fresh_conn()
    for _ in range(20):
        M.record_agent_interest('ghost', 'rust', source_agent='librarian', conn=conn)
    row = conn.execute("SELECT score FROM user_interests WHERE topic='rust'").fetchone()
    assert row['score'] <= 9.0
    assert row['score'] >= 5.5  # initial 5.0 + at least one 0.5 nudge


def test_decay_and_deactivate():
    conn = _fresh_conn()
    # Two agent rows: one that will survive, one that will be deactivated.
    conn.execute(
        "INSERT INTO user_interests (username, topic, source, source_agent, score, active) "
        "VALUES ('ghost', 'high', 'agent', 'scholar', 8.0, 1), "
        "       ('ghost', 'low',  'agent', 'seeker',  1.05, 1), "
        "       ('ghost', 'userrow', 'user', '', 0.5, 1)"  # user row below threshold
    )
    conn.commit()
    decayed, deactivated = M.decay_agent_interests(factor=0.9, deactivate_below=1.0, conn=conn)
    assert decayed == 2
    assert deactivated == 1
    # User row untouched
    row = conn.execute("SELECT active, score FROM user_interests WHERE topic='userrow'").fetchone()
    assert row['active'] == 1
    assert row['score'] == 0.5
    # High agent row decayed but still active
    row = conn.execute("SELECT active, score FROM user_interests WHERE topic='high'").fetchone()
    assert row['active'] == 1
    assert abs(row['score'] - 7.2) < 0.001
    # Low agent row deactivated
    row = conn.execute("SELECT active FROM user_interests WHERE topic='low'").fetchone()
    assert row['active'] == 0


def test_list_agent_interests_filters():
    conn = _fresh_conn()
    M.record_agent_interest('ghost', 'rust', source_agent='librarian', conn=conn)
    M.record_agent_interest('ghost', 'go', source_agent='scholar', conn=conn)
    M.record_agent_interest('ghost', 'zig', source_agent='seeker', conn=conn)
    conn.execute(
        "INSERT INTO user_interests (username, topic, source, source_agent, score) "
        "VALUES ('ghost', 'python', 'user', '', 10.0)"
    )
    conn.commit()

    all_agent = M.list_agent_interests('ghost', conn=conn)
    assert len(all_agent) == 3
    topics = {r['topic'] for r in all_agent}
    assert topics == {'rust', 'go', 'zig'}

    only_scholar = M.list_agent_interests('ghost', agent='scholar', conn=conn)
    assert len(only_scholar) == 1
    assert only_scholar[0]['topic'] == 'go'


def test_schema_migration_adds_source_agent_column():
    """Migration path on an existing DB that predates the source_agent column."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    # Simulate the OLD schema (no source_agent column)
    conn.executescript('''
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        );
    ''')
    conn.commit()
    cols_before = {r[1] for r in conn.execute('PRAGMA table_info(user_interests)').fetchall()}
    assert 'source_agent' not in cols_before

    # Run the exact migration snippet from _schema.py
    tables = {'user_interests'}
    if 'user_interests' in tables:
        ui_cols = {row[1] for row in conn.execute('PRAGMA table_info(user_interests)').fetchall()}
        if 'source_agent' not in ui_cols:
            conn.execute("ALTER TABLE user_interests ADD COLUMN source_agent TEXT DEFAULT ''")

    cols_after = {r[1] for r in conn.execute('PRAGMA table_info(user_interests)').fetchall()}
    assert 'source_agent' in cols_after
