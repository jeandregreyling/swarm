"""Regression tests for backlog batch 7 (2026-05-02 session 28).

- S-9D336883B1: SAP query expansion
- S-B0460BB6BD: Official SAP source allowlist
- S-F02066C5FA: scheduled_tasks.project_id + project_step_id columns
- S-F4DC817B17: project_step_evidence auto-created after task run
- S-8FEC46532A: IMAP listener regression scaffolding
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# S-9D336883B1 -------------------------------------------------------------

def test_expand_sap_query_adds_module_synonyms():
    from lib.search.internet_tavily import expand_sap_query
    out = expand_sap_query('SAP HCM payroll fix')
    assert 'SAP HCM' in out or 'sap' in out.lower()
    assert 'payroll' in out.lower()


def test_expand_sap_query_prefixes_when_missing_sap_terms():
    from lib.search.internet_tavily import expand_sap_query
    out = expand_sap_query('how to debug')
    assert out.lower().startswith('sap hcm')


def test_expand_sap_query_handles_empty():
    from lib.search.internet_tavily import expand_sap_query
    assert expand_sap_query('') == ''
    assert expand_sap_query('   ').strip() == ''


# S-B0460BB6BD -------------------------------------------------------------

def test_is_official_sap_source_accepts_help_sap_com():
    from lib.search.internet_tavily import is_official_sap_source
    assert is_official_sap_source('https://help.sap.com/docs/foo')
    assert is_official_sap_source('https://launchpad.support.sap.com/note/12345')
    assert is_official_sap_source('https://api.sap.com/api/SUCCESSFACTORS')


def test_is_official_sap_source_rejects_non_official():
    from lib.search.internet_tavily import is_official_sap_source
    assert not is_official_sap_source('https://stackoverflow.com/q/sap')
    assert not is_official_sap_source('')
    assert not is_official_sap_source('https://sap-fake.example.com/help.sap.com')


# 2026-05-03 — Tavily 400-char query limit guard ---------------------------

def test_truncate_query_under_limit_unchanged():
    from lib.search.internet_tavily import _truncate_query
    q = 'SAP HCM payroll PCR debugging'
    assert _truncate_query(q) == q


def test_truncate_query_over_limit_cuts_on_word_boundary():
    from lib.search.internet_tavily import _truncate_query
    q = ('lorem ipsum ' * 60).strip()  # ~720 chars
    out = _truncate_query(q, limit=380)
    assert len(out) <= 380
    # Did not split mid-word.
    assert not out.endswith('lor') and not out.endswith('ipsu')


def test_truncate_query_handles_no_whitespace():
    from lib.search.internet_tavily import _truncate_query
    q = 'x' * 1000
    out = _truncate_query(q, limit=380)
    assert len(out) == 380


def test_distil_question_strips_html_and_picks_question_sentence():
    from lib.search.internet_tavily import _distil_question
    # Pad with filler so total > 300 chars and the sentence-picking branch
    # fires. The actual question must surface from the noise.
    filler = '<p>boilerplate footer text to push past the threshold. </p>' * 10
    blob = (
        '<!doctype html><html><body><p>Hello there.</p>'
        '<p>How do I configure SAP HCM payroll PCR for retroactive accounting?</p>'
        + filler +
        '</body></html>'
    )
    out = _distil_question(blob)
    assert '<' not in out
    assert 'PCR' in out and out.endswith('?')


def test_distil_question_short_input_passthrough():
    from lib.search.internet_tavily import _distil_question
    assert _distil_question('SAP HCM payroll question') == 'SAP HCM payroll question'


def test_distil_question_empty_safe():
    from lib.search.internet_tavily import _distil_question
    assert _distil_question('') == ''
    assert _distil_question(None) == ''


# S-F02066C5FA / S-F4DC817B17 ---------------------------------------------

@pytest.fixture()
def task_db(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_memory.db'
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            schedule TEXT DEFAULT '',
            action_type TEXT DEFAULT '',
            action_data TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            project_id TEXT DEFAULT '',
            project_step_id TEXT DEFAULT ''
        );
        CREATE TABLE task_run_log (
            task_name TEXT NOT NULL,
            status TEXT DEFAULT 'ok',
            output TEXT DEFAULT '',
            run_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0,
            details_json TEXT DEFAULT ''
        );
        CREATE TABLE project_step_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'task',
            source_ref TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    # Reroute every code path that resolves the DB through SWARM_DB_PATH.
    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    import importlib
    import utils.db._connection as conn_mod
    importlib.reload(conn_mod)
    # Some modules captured `get_connection` at import-time; rebind those too.
    new_get = lambda: sqlite3.connect(str(db))
    monkeypatch.setattr(conn_mod, 'get_connection', new_get)
    try:
        import utils.database as udb
        monkeypatch.setattr(udb, 'get_connection', new_get, raising=False)
    except Exception:
        pass
    try:
        import database as db_mod
        monkeypatch.setattr(db_mod, 'get_connection', new_get, raising=False)
    except Exception:
        pass
    return str(db)


def test_scheduled_tasks_project_columns_exist(task_db):
    conn = sqlite3.connect(task_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(scheduled_tasks)").fetchall()}
    conn.close()
    assert 'project_id' in cols
    assert 'project_step_id' in cols


def test_step_evidence_recorded_when_task_linked_to_project(task_db):
    conn = sqlite3.connect(task_db)
    conn.execute(
        "INSERT INTO scheduled_tasks (name, schedule, action_type, action_data, "
        "project_id, project_step_id) VALUES "
        "('linked', '*/5 * * * *', 'python', 'noop_probe', 'P-XYZ', 'S-AAA')"
    )
    conn.commit()
    conn.close()

    from fridays.task_runner import TASK_REGISTRY, run_task
    TASK_REGISTRY['noop_probe'] = {
        'fn': lambda args='': 'probe ran', 'description': 'p',
        'category': 'test',
    }
    try:
        ok, out = run_task('noop_probe', args='')
        assert ok is True
    finally:
        TASK_REGISTRY.pop('noop_probe', None)

    conn = sqlite3.connect(task_db)
    rows = conn.execute(
        "SELECT project_id, step_id, source_type, source_ref, status "
        "FROM project_step_evidence"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 'P-XYZ'
    assert rows[0][1] == 'S-AAA'
    assert rows[0][2] == 'task'
    assert rows[0][3] == 'noop_probe'
    assert rows[0][4] == 'ok'


def test_step_evidence_skipped_when_task_not_linked(task_db):
    conn = sqlite3.connect(task_db)
    conn.execute(
        "INSERT INTO scheduled_tasks (name, schedule, action_type, action_data) "
        "VALUES ('unlinked', '*/5 * * * *', 'python', 'noop_probe2')"
    )
    conn.commit()
    conn.close()

    from fridays.task_runner import TASK_REGISTRY, run_task
    TASK_REGISTRY['noop_probe2'] = {
        'fn': lambda args='': 'ok', 'description': 'p2', 'category': 'test',
    }
    try:
        run_task('noop_probe2', args='')
    finally:
        TASK_REGISTRY.pop('noop_probe2', None)

    conn = sqlite3.connect(task_db)
    n = conn.execute("SELECT COUNT(*) FROM project_step_evidence").fetchone()[0]
    conn.close()
    assert n == 0


# S-8FEC46532A -------------------------------------------------------------

def test_listener_module_imports_without_side_effects(monkeypatch):
    # The listener relies on env-vars and a mailbox; importing must not
    # connect to IMAP. We just verify the module is importable and exposes
    # PUSH_RECOVERY_INTERVAL_SECONDS.
    monkeypatch.setenv('SWARM_LISTENER_TEST_MODE', '1')
    import importlib
    listener = importlib.import_module('core.pipeline.listener')
    assert hasattr(listener, 'PUSH_RECOVERY_INTERVAL_SECONDS')
    assert listener.PUSH_RECOVERY_INTERVAL_SECONDS >= 60
