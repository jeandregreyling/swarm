"""Practice 278 (JD 22 Nov: "yeah maybe if i could actually click on anything I would" / "I'm trying to click on the agent selection of a task"):
with Fred switched off, Practice 276/277 left only APEX on the list - nothing to click. Fred stays pickable ("Fred (off)"); picking him
switches him on and hands him the step's open task at once; the list says what happened."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_clipboard, hb_model_switches, hb_task_manager as tm, hb_tasks

ROOT = Path(__file__).resolve().parents[1]


def _db(task=True):
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    hb_tasks.ensure_schema(c)
    c.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, title TEXT, description TEXT, status TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-0123456789', 'x', 'Done when: x', 'todo')")
    c.execute('CREATE TABLE hb_task_manager(task_id TEXT PRIMARY KEY)')
    if task:
        c.execute("INSERT INTO hb_tasks(task_id, conversation_id, root_message_id, title, objective, step_id) VALUES ('T-1', 2845, 1, 'x', 'x', 'S-0123456789')")
        c.execute("INSERT INTO hb_task_manager VALUES ('T-1')")
    return c


@pytest.fixture
def fred_off(monkeypatch):
    calls = {'set': [], 'help': []}
    state = {'mode': 'off'}
    monkeypatch.setattr(hb_model_switches, 'modes', lambda conn: {hb_model_switches.FRED: state['mode']})

    def set_mode(conn, model, mode, actor):
        calls['set'].append((model, mode, actor))
        state['mode'] = mode
    monkeypatch.setattr(hb_model_switches, 'set_mode', set_mode)
    return calls


def test_picking_fred_switches_him_on_and_hands_him_the_task_now(fred_off, monkeypatch):
    monkeypatch.setattr(tm, 'local_help', lambda conn, task, selected=False: fred_off['help'].append((task['task_id'], selected)) or 'submitted')
    said = hb_clipboard.edit(_db(), ['doer', 'S-0123456789', 'fred'], 'jd via the task board')
    assert 'Fred switched on. Fred has it now.' in said
    assert fred_off['set'] == [(hb_model_switches.FRED, 'on', 'jd via the task board')] and fred_off['help'] == [('T-1', True)]


def test_the_list_says_why_when_fred_cannot_take_it(fred_off, monkeypatch):
    monkeypatch.setattr(tm, 'local_help', lambda conn, task, selected=False: 'unavailable: the step is too vague to build - it needs a spec, not Fred')
    assert 'Fred could not take it: the step is too vague to build' in hb_clipboard.edit(_db(), ['doer', 'S-0123456789', 'fred'], 'jd')


def test_a_step_with_no_task_yet_waits_for_fred_and_apex_needs_no_handover(fred_off, monkeypatch):
    monkeypatch.setattr(tm, 'local_help', lambda *a, **k: pytest.fail('no task to hand over'))
    assert 'Fred takes it when the step starts.' in hb_clipboard.edit(_db(task=False), ['doer', 'S-0123456789', 'fred'], 'jd')
    said = hb_clipboard.edit(_db(), ['doer', 'S-0123456789', 'apex'], 'jd')
    assert 'Fred' not in said and 'doer: APEX' in said


def test_fred_off_is_still_a_button_on_the_list():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    doers = [{'id': 'apex', 'name': 'APEX', 'ok': True, 'off': False, 'why': 'a'}, {'id': 'fred', 'name': 'Fred', 'ok': True, 'off': True, 'why': 'b'}]
    js = ROOT / 'frontend/static/js/hb-live.js'
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(js))}); process.stdout.write(R.renderDoers({{step_id:'S-1',doer:'apex'}}, {json.dumps(doers)}))"],
                         capture_output=True, text=True, timeout=20).stdout
    assert 'data-v="fred"' in out and '>Fred (off)</button>' in out and '>APEX</b>' in out
