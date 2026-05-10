"""Batch O regression: interests bridge, integration dashboard,
acceptance gate, mega-backlog.

Stories pinned:
  * S-3A39AD790A — Interests Tasker bridge
  * S-AE36796087 — Interests provenance display
  * S-737DA6DA1E — Integration project dashboard card
  * S-6189B79E2C — Final acceptance gate
  * S-37A1AD9E04 — Consolidate active mega-project backlog
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import interests_bridge, integration_dashboard, acceptance_gate  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    db = tmp_path / "t.db"
    c = sqlite3.connect(str(db))
    c.executescript("""
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, topic TEXT, category TEXT,
            source TEXT, score REAL, active INTEGER,
            created_at TEXT, updated_at TEXT, source_agent TEXT
        );
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE project_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'todo',
            test_files TEXT DEFAULT '',
            residual_risk TEXT DEFAULT '',
            owner TEXT DEFAULT '',
            owner_route TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE project_step_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            source_type TEXT, source_ref TEXT,
            summary TEXT, status TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    yield c
    c.close()


# ── Interests bridge ───────────────────────────────────────────────────────

def test_list_interests_for_tasker_orders_by_score(conn):
    conn.executescript("""
        INSERT INTO user_interests (username, topic, category, source, score, active, source_agent)
            VALUES ('u','Python','tech','user',10,1,''),
                   ('u','Cooking','personal','user',3,1,''),
                   ('u','AI','tech','agent',8,1,'twenty'),
                   ('u','OldThing','tech','user',5,0,'');
    """)
    out = interests_bridge.list_interests_for_tasker(conn)
    topics = [r["topic"] for r in out]
    assert topics == ["Python", "AI", "Cooking"]  # active only, score desc
    py = next(r for r in out if r["topic"] == "Python")
    assert py["topic_key"] == "python"


def test_list_interests_slugifies(conn):
    conn.execute(
        "INSERT INTO user_interests (topic, category, source, score, active, source_agent) "
        "VALUES ('AI & Machine Learning!','tech','user',9,1,'')"
    )
    out = interests_bridge.list_interests_for_tasker(conn)
    assert out[0]["topic_key"] == "ai_machine_learning"


def test_provenance_for_unknown_topic_is_none(conn):
    assert interests_bridge.provenance_for(conn, "nope") is None


def test_provenance_manual(conn):
    conn.execute(
        "INSERT INTO user_interests (topic, source, score, active, source_agent) "
        "VALUES ('Python','user',9,1,'')"
    )
    p = interests_bridge.provenance_for(conn, "Python")
    assert p["manual"] is True
    assert p["agent_added"] is False
    assert p["label"] == "Added by you"


def test_provenance_agent_suggested(conn):
    conn.execute(
        "INSERT INTO user_interests (topic, source, score, active, source_agent) "
        "VALUES ('Quantum','agent',5,1,'twenty')"
    )
    p = interests_bridge.provenance_for(conn, "Quantum")
    assert p["agent_added"] is True
    assert p["manual"] is False
    assert "twenty" in p["label"]


def test_provenance_empty_topic(conn):
    assert interests_bridge.provenance_for(conn, "") is None


# ── Integration dashboard ──────────────────────────────────────────────────

def test_dashboard_unknown_project(conn):
    out = integration_dashboard.dashboard_tile(conn, "P-NOPE")
    assert out["ok"] is False


def test_dashboard_empty_project_id(conn):
    out = integration_dashboard.dashboard_tile(conn, "")
    assert out["ok"] is False


def test_dashboard_counts(conn):
    conn.execute("INSERT INTO projects (project_id, name, status) VALUES ('P-1','Test','active')")
    conn.executemany(
        "INSERT INTO project_steps (project_id, step_id, title, status) VALUES ('P-1', ?, ?, ?)",
        [("S-1", "a", "done"), ("S-2", "b", "done"),
         ("S-3", "c", "blocked"), ("S-4", "d", "todo")],
    )
    conn.execute(
        "INSERT INTO project_step_evidence (project_id, step_id, source_type, summary, status) "
        "VALUES ('P-1','S-1','task','ok','ok')"
    )
    out = integration_dashboard.dashboard_tile(conn, "P-1")
    assert out["ok"] is True
    assert out["step_counts"]["total"] == 4
    assert out["step_counts"]["done"] == 2
    assert out["step_counts"]["blocked"] == 1
    assert out["step_counts"]["todo"] == 1
    assert out["evidence_count"] == 1


# ── Acceptance gate ────────────────────────────────────────────────────────

def test_gate_unknown_project(conn):
    out = acceptance_gate.evaluate(conn, "P-MISSING")
    assert out["ok"] is False
    assert "not found" in " ".join(out["blockers"])


def test_gate_empty_project_id(conn):
    out = acceptance_gate.evaluate(conn, "")
    assert out["ok"] is False


def test_gate_blocks_when_open_steps(conn):
    conn.execute("INSERT INTO projects (project_id, name) VALUES ('P-2','x')")
    conn.executemany(
        "INSERT INTO project_steps (project_id, step_id, title, status, test_files) "
        "VALUES ('P-2', ?, ?, ?, ?)",
        [("S-A", "todo step", "todo", ""),
         ("S-B", "done step", "done", "tests/x.py")],
    )
    out = acceptance_gate.evaluate(conn, "P-2")
    assert out["ok"] is False
    assert any("S-A" in b for b in out["blockers"])


def test_gate_blocks_when_done_step_has_no_evidence_or_test(conn):
    conn.execute("INSERT INTO projects (project_id, name) VALUES ('P-3','y')")
    conn.execute(
        "INSERT INTO project_steps (project_id, step_id, title, status, test_files) "
        "VALUES ('P-3','S-C','no proof','done','')"
    )
    out = acceptance_gate.evaluate(conn, "P-3")
    assert out["ok"] is False
    assert any("S-C" in b and "no test_files" in b for b in out["blockers"])


def test_gate_handles_live_schema_without_test_files(tmp_path):
    db = tmp_path / "live-like.db"
    c = sqlite3.connect(str(db))
    try:
        c.executescript("""
            CREATE TABLE projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE project_steps (
                step_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                residual_risk TEXT DEFAULT ''
            );
            CREATE TABLE project_step_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                summary TEXT DEFAULT ''
            );
            INSERT INTO projects (project_id, name) VALUES ('P-LIVE','live schema');
            INSERT INTO project_steps (project_id, step_id, title, status)
                VALUES ('P-LIVE','S-LIVE','done with evidence','done');
            INSERT INTO project_step_evidence (project_id, step_id, summary)
                VALUES ('P-LIVE','S-LIVE','verified');
        """)
        out = acceptance_gate.evaluate(c, "P-LIVE")
    finally:
        c.close()

    assert out["ok"] is True
    assert out["step_summary"]["done"] == 1


def test_gate_passes_with_evidence_only(conn):
    conn.execute("INSERT INTO projects (project_id, name) VALUES ('P-4','z')")
    conn.execute(
        "INSERT INTO project_steps (project_id, step_id, title, status, test_files) "
        "VALUES ('P-4','S-D','ok','done','')"
    )
    conn.execute(
        "INSERT INTO project_step_evidence (project_id, step_id, summary) "
        "VALUES ('P-4','S-D','task ran ok')"
    )
    out = acceptance_gate.evaluate(conn, "P-4")
    assert out["ok"] is True


def test_gate_warns_on_residual_risk(conn):
    conn.execute("INSERT INTO projects (project_id, name) VALUES ('P-5','r')")
    conn.execute(
        "INSERT INTO project_steps (project_id, step_id, title, status, test_files, residual_risk) "
        "VALUES ('P-5','S-E','ok','done','tests/x.py','rate limit untested')"
    )
    out = acceptance_gate.evaluate(conn, "P-5")
    assert out["ok"] is True
    assert any("rate limit" in w for w in out["warnings"])


def test_gate_skipped_steps_dont_need_evidence(conn):
    conn.execute("INSERT INTO projects (project_id, name) VALUES ('P-6','s')")
    conn.execute(
        "INSERT INTO project_steps (project_id, step_id, title, status) "
        "VALUES ('P-6','S-F','skip me','skipped')"
    )
    out = acceptance_gate.evaluate(conn, "P-6")
    assert out["ok"] is True
    assert out["step_summary"]["skipped"] == 1


# ── Mega-backlog reporter ──────────────────────────────────────────────────

def test_mega_backlog_collect_and_render(conn):
    conn.executescript("""
        INSERT INTO projects (project_id, name, status) VALUES
            ('P-A','Alpha mega project','active'),
            ('P-B','Beta','on_hold'),
            ('P-C','Closed','archived');
        INSERT INTO project_steps (project_id, step_id, title, status) VALUES
            ('P-A','S-1','x','done'),
            ('P-A','S-2','y','todo'),
            ('P-A','S-4','[P-441A6D6476] V8-B1 shell','todo'),
            ('P-A','S-5','[PACKET-11] Media Center comp','doing'),
            ('P-A','S-6','Fix watchdog orphan recovery','blocked'),
            ('P-B','S-3','z','done');
    """)
    from ops import mega_backlog
    records = mega_backlog.collect(conn)
    pids = [r["project_id"] for r in records]
    assert "P-A" in pids and "P-B" in pids
    assert "P-C" not in pids  # archived excluded
    rendered = mega_backlog.render_text(records)
    assert "Alpha mega project" in rendered
    assert "P-A" in rendered
    alpha = next(r for r in records if r["project_id"] == "P-A")
    assert alpha["lanes"]["v8-runtime"]["todo"] == 1
    assert alpha["lanes"]["media"]["doing"] == 1
    assert alpha["lanes"]["watchdog-recovery"]["blocked"] == 1
    assert "v8-runtime" in rendered
    assert "watchdog-recovery" in rendered


def test_mega_backlog_empty(conn):
    from ops import mega_backlog
    out = mega_backlog.render_text(mega_backlog.collect(conn))
    assert "no active" in out.lower()
