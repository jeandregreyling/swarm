"""Practice 209: HB announces work in main chat; the ribbon sizes itself."""
import sqlite3
from pathlib import Path

from core import hb_announce as a

JS = (Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live.js').read_text()


def test_start_and_finish_are_posted_with_names():
    c = sqlite3.connect(':memory:')
    said = []
    post = lambda conn, text: said.append(text)
    job = {'run_id': 'R-1', 'actor': 'apex', 'lane': 'gpu', 'title': 'Repair 9: transport', 'purpose': 'workflow step', 'task_id': 'T-1'}
    assert a.tick(c, now=100, items=[job], post=post) == ['▶ APEX started: Repair 9: transport']
    assert a.tick(c, now=110, items=[job], post=post) == []                      # still running: nothing new
    assert a.tick(c, now=200, items=[], post=post) == []                         # missing once: not yet
    assert a.tick(c, now=400, items=[], post=post) == ['✓ APEX finished: Repair 9: transport (5 min)']


def test_failed_run_says_stopped():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_activity_log(id INTEGER PRIMARY KEY, run_id TEXT, kind TEXT, text TEXT)')
    c.execute("INSERT INTO hb_activity_log(run_id, kind, text) VALUES ('R-2','error','TimeoutError: slow (30 s)')")
    said = []
    job = {'run_id': 'R-2', 'actor': 'fred', 'lane': 'cpu', 'title': 'Repair 6', 'purpose': 'workflow step'}
    a.tick(c, now=0, items=[job], post=lambda conn, t: said.append(t))
    a.tick(c, now=10, items=[], post=lambda conn, t: said.append(t))
    a.tick(c, now=20, items=[], post=lambda conn, t: said.append(t))
    assert said[-1] == '✗ Fred stopped: Repair 6 (under a minute) - TimeoutError: slow (30 s)'


def test_names_not_roles():
    assert [a.name(x) for x in ('codex-instructor', 'claude-code', 'gemini-advisor', 'apex', 'fred', 'jd')] == \
        ['Codex', 'Claude Code', 'Gemini', 'APEX', 'Fred', 'JD']


def test_quiet_runs_are_not_announced():
    c = sqlite3.connect(':memory:')
    assert not a._worth(c, {'title': 'x', 'purpose': 'model call'})
    assert not a._worth(c, {'title': 'hello', 'purpose': 'main-chat turn', 'task_id': None})


def test_ribbon_has_no_grip_and_no_saved_height():
    assert 'resize:vertical' not in JS and "ls('hbLive.paneHeight', '')" in JS and 'ResizeObserver' not in JS
    assert "t.closest('[data-win=\"master\"]')" in JS
