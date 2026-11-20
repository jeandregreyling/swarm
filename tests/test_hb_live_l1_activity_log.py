"""HB Live L1: every model call and every APEX turn is recorded in hb_activity_log; Claude Code's work too."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import core.apex_tools as t
from core import hb_activity_log as live
from core import llm

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(monkeypatch, tmp_path):
    path = tmp_path / 'live.db'
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: sqlite3.connect(path))
    monkeypatch.setattr(live, 'who', lambda model: ('apex', 'gpu', 'ROCm', 'swift-qwen3.8-27b') if 'fred' not in str(model)
                        else ('fred', 'cpu', 'CPU', 'fred-cpu:24b'))
    return lambda: sqlite3.connect(path)


def test_gateway_call_is_logged_inside_the_turn(db, monkeypatch):
    monkeypatch.setattr(llm, '_chat_via_gateway_impl', lambda model, messages, **kw: ('hello', 7))
    with live.run('apex', 'gpu', 'APEX: MCB question', purpose='main-chat turn') as r:
        assert llm.chat_via_gateway('gpt-oss:20b', [{'role': 'user', 'content': 'hi'}]) == ('hello', 7)
        live.step('searching our notes: "MCB"')
    c = db()
    rows = c.execute('SELECT run_id, parent, actor, model, device, kind, text FROM hb_activity_log ORDER BY id').fetchall()
    kinds = [(r[0] == r_id, r[5]) for r_id in [r.run_id] for r in rows]
    assert [k for _, k in kinds] == ['start', 'start', 'finish', 'step', 'finish']
    call = [x for x in rows if x[0] != r.run_id]
    assert call[0][1] == r.run_id and call[0][3] == 'swift-qwen3.8-27b' and call[0][4] == 'ROCm' and '7 tokens' in call[-1][6]
    assert live.open_runs(c) == []
    done = live.finished(c)
    assert done[0]['run_id'] == r.run_id and done[0]['steps'] >= 1 and done[0]['outcome'] == 'ok'


def test_failed_call_is_an_error_entry(db, monkeypatch):
    monkeypatch.setattr(llm, '_chat_via_gateway_impl', lambda model, messages, **kw: ('[local runtime error: model busy]', 0))
    llm.chat_via_gateway('fred-cpu:24b', [])
    rows = db().execute("SELECT actor, lane, kind, text FROM hb_activity_log WHERE kind IN ('finish','error')").fetchall()
    assert rows == [('fred', 'cpu', 'error', rows[0][3])] and 'model busy' in rows[0][3]


def test_apex_turn_is_one_run_with_its_steps(db, monkeypatch, tmp_path):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    turns = [json.dumps({'tool_calls': [], 'answer': 'A list is mutable; a tuple is not.'})] * 3
    t.run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'list vs tuple?'}], lambda: True, lambda _r: None,
                     t.ReadOnlyRepository(tmp_path))
    c = db()
    start = c.execute("SELECT run_id, actor, lane, text, purpose FROM hb_activity_log WHERE kind='start'").fetchone()
    assert start[1:] == ('apex', 'gpu', 'APEX: list vs tuple?', 'main-chat turn')
    assert c.execute("SELECT COUNT(*) FROM hb_activity_log WHERE run_id=? AND kind='step'", (start[0],)).fetchone()[0] >= 1
    assert c.execute("SELECT kind FROM hb_activity_log WHERE run_id=? ORDER BY id DESC LIMIT 1", (start[0],)).fetchone()[0] == 'finish'


def test_logging_never_breaks_work(monkeypatch):
    monkeypatch.setattr(live, 'FORCE', True)
    monkeypatch.setattr(live, '_connect', lambda: (_ for _ in ()).throw(OSError('disk gone')))
    assert live.write({'kind': 'start'}) is False
    with live.run('hb', 'hb', 'x') as r:
        r.step('still fine')


def test_off_under_pytest_by_default():
    assert live.enabled() is False


def test_claude_code_runs(tmp_path):
    db_path = tmp_path / 'cc.db'
    env = {'SWARM_DB_PATH': str(db_path), 'PATH': '/usr/bin:/bin'}
    script = ROOT / 'runtime/claude_helpers/hbrun.py'
    if not script.exists():
        pytest.skip('hbrun.py lives in runtime/claude_helpers (not part of a fresh checkout)')
    rid = subprocess.run([sys.executable, str(script), 'start', 'Backlog sweep'], env=env, capture_output=True, text=True).stdout.strip()
    subprocess.run([sys.executable, str(script), 'step', rid, 'fixed 6 bugs'], env=env)
    subprocess.run([sys.executable, str(script), 'finish', rid, 'ok'], env=env)
    rows = sqlite3.connect(db_path).execute('SELECT lane, actor, kind FROM hb_activity_log WHERE run_id=? ORDER BY id', (rid,)).fetchall()
    assert rows == [('claude-code', 'claude', 'start'), ('claude-code', 'claude', 'step'), ('claude-code', 'claude', 'finish')]
