"""DREAM as the way every task runs: the clipboard card and the "Distinguish" gate."""
import json
import sqlite3

import pytest

from core import hb_tasks, hb_dream_method as dream, hb_kc_records as kc
from core import hb_task_manager as manager


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE conversations(id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT,
                              message_type TEXT, tokens_used INT, created_at TEXT DEFAULT '2026-11-12 08:00:00');
        CREATE TABLE knowledge_sources(source_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'text',
            source_ref TEXT, raw_text TEXT, domain_tags TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'active',
            added_by TEXT NOT NULL DEFAULT 'ghost', chunk_count INTEGER NOT NULL DEFAULT 0, created_at DATETIME, updated_at DATETIME,
            category TEXT NOT NULL DEFAULT 'general', subcategory TEXT, content_hash TEXT);
        CREATE TABLE knowledge_chunks(chunk_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INT, chunk_index INT, chunk_text TEXT,
            embedding TEXT, created_at DATETIME);
        CREATE TABLE project_test_cases(case_id TEXT, project_id TEXT, step_id TEXT, title TEXT, script_id TEXT, status TEXT,
            owner TEXT, created_at REAL, updated_at REAL);
    """)
    from core import peer_bridge, peer_turns
    peer_bridge.ensure_schema(c)
    peer_turns.ensure_schema(c)
    hb_tasks.ensure_schema(c)
    manager.ensure_schema(c)
    import importlib
    for name in ('core.hb_executions', 'core.hb_owner_sessions', 'core.hb_provider_conditions'):
        module = importlib.import_module(name)
        if hasattr(module, 'ensure_schema'):
            module.ensure_schema(c)
    yield c
    c.close()


def task_from(c, text):
    mid = c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type) VALUES(2834,'user','apex',?,'chat')",
                    (text,)).lastrowid
    return hb_tasks.bind(c, 2834, mid)


def test_done_criteria_come_from_owner_studio_or_the_task_text(conn):
    t = task_from(conn, 'Show real VRAM on the sundial')
    assert dream.done_when(conn, t) == (None, [])
    t2 = task_from(conn, 'Fix the sundial\nDone when: VRAM matches /sys/class/drm readings')
    assert dream.done_when(conn, t2) == ('task', ['VRAM matches /sys/class/drm readings'])
    conn.execute("UPDATE hb_tasks SET step_id='S-ABCDEF0123' WHERE task_id=?", (t['task_id'],))
    conn.execute("INSERT INTO project_test_cases VALUES('C-1','P-1','S-ABCDEF0123','sundial shows GPU busy %','s','todo','apex',0,0)")
    assert dream.done_when(conn, hb_tasks.get(conn, t['task_id'])) == ('studio', ['sundial shows GPU busy %'])
    dream.set_done(conn, hb_tasks.get(conn, t['task_id']), ['VRAM and GPU % match sysfs', 'switches unload a model'], 'jd')
    assert dream.done_when(conn, hb_tasks.get(conn, t['task_id']))[0] == 'owner'      # owner's words win
    with pytest.raises(ValueError):
        dream.set_done(conn, t, ['tiny'], 'jd')


def test_card_holds_goal_done_step_failure_related_work_and_method(conn):
    old = task_from(conn, 'Repair sundial vram gauge readings from sysfs amdgpu counters')
    hb_tasks.event(conn, old, 'apex', 'tool_failure', {'tool': 'read_file', 'error': 'old failure'})
    kc.tick(conn)
    t = task_from(conn, 'Sundial vram gauge shows wrong amdgpu counters')
    hb_tasks.event(conn, t, 'apex', 'task_plan', {'next_action': 'Read the sysfs counters and compare with the sundial API output'})
    hb_tasks.event(conn, t, 'apex', 'tool_failure', {'tool': 'grep_repo', 'error': 'pattern too short'})
    kc.tick(conn)
    text = dream.card(conn, hb_tasks.get(conn, t['task_id']))
    assert text.startswith(dream.CARD_HEADER + t['task_id'])
    assert 'Done when: what JD asked is done' in text and 'do NOT ask JD to define' in text
    assert 'Current step: Read the sysfs counters' in text
    assert 'grep_repo: pattern too short' in text
    assert old['task_id'] in text and 'KC document' in text                        # related past work found in the KC
    assert 'look in the KC and memory first' in text


def test_gate_holds_automatic_continuation_until_done_is_defined_then_releases(conn, monkeypatch):
    from core.hb_chat_controls import continuation
    t = task_from(conn, 'Continue the DREAM build')
    manager.register(conn, t)
    # Owner has turned Continue on; nothing else is in the way.
    monkeypatch.setattr('core.hb_chat_controls.continuation',
                        lambda c, task: {**continuation(c, task), 'mode': 'on', 'effective': 'on'})
    monkeypatch.setattr(manager, '_queue', lambda *a, **k: 4242)
    monkeypatch.setattr('core.hb_executions.reconcile', lambda c: None)
    monkeypatch.setattr('core.hb_executions.active', lambda c, tid: False)
    assert manager.tick(conn) == []
    state, detail = conn.execute('SELECT state, detail FROM hb_task_manager WHERE task_id=?', (t['task_id'],)).fetchone()
    assert state == 'needs_owner' and 'definition of done' in detail
    asks = conn.execute("SELECT content FROM messages WHERE from_agent='hummingbird'").fetchall()
    assert len(asks) == 1 and f"/done {t['task_id']}" in asks[0][0]
    manager.tick(conn)
    assert len(conn.execute("SELECT 1 FROM messages WHERE from_agent='hummingbird'").fetchall()) == 1   # asked once
    dream.set_done(conn, hb_tasks.get(conn, t['task_id']), ['the DREAM idle report runs after one idle hour'], 'jd')
    conn.execute('UPDATE hb_task_manager SET next_due=0')
    assert manager.tick(conn) == [4242]                                                    # released by /done
