"""Practice 276 (JD 22 Nov: "in the task list, I can't reassign tasks to different actors, it shows a really ugly dropdown with some names in
it, not sure why it's showing actors that aren't even available, and also does nothing when I click on any of them"): the list offers one
button per doer HB can really run (APEX; Fred unless switched off), a click reassigns at once, and JD picking Fred is JD calling Fred."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_live, hb_model_switches, hb_task_manager as tm

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'
BOTH = [{'id': 'apex', 'name': 'APEX', 'ok': True}, {'id': 'fred', 'name': 'Fred', 'ok': True}]


def _render(item, doers):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(JS))}); process.stdout.write(R.renderDoers({json.dumps(item)}, {json.dumps(doers)}))"],
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-400:]
    return out.stdout


def test_one_button_per_runnable_doer_and_the_current_one_is_lit():
    html = _render({'step_id': 'S-1', 'doer': 'apex'}, BOTH)
    assert '<b class="hbl-doer hbl-doer-on"' in html and '>APEX</b>' in html
    assert 'data-q="clip" data-a="doer" data-id="S-1" data-v="fred"' in html and '<select' not in html


def test_unavailable_doers_are_not_offered():
    html = _render({'step_id': 'S-1', 'doer': 'apex'}, [BOTH[0], {'id': 'fred', 'name': 'Fred', 'ok': False, 'why': 'Fred is switched Off in Live status'}])
    assert 'data-v="fred"' not in html and '>Fred<' not in html
    assert '· Fred is switched Off in Live status' in html            # Practice 277: says why, no button
    for name in ('codex', 'gemini', 'small', 'Codex', 'Gemini'):
        assert name not in html


def test_a_doer_hb_cannot_run_shows_as_a_tag_with_the_real_choices():
    html = _render({'step_id': 'S-1', 'doer': 'claude'}, BOTH)
    assert 'hbl-tag' in html and 'Claude Code' in html and 'data-v="apex"' in html and 'data-v="fred"' in html


def test_the_snapshot_lists_who_can_take_a_step(monkeypatch):
    monkeypatch.setattr(hb_model_switches, 'modes', lambda conn: {hb_model_switches.FRED: 'off'})
    assert [(d['id'], d['ok'], d['off']) for d in hb_live._doers(None)] == [('apex', True, False), ('fred', True, True)]   # Practice 278
    monkeypatch.setattr(hb_model_switches, 'modes', lambda conn: {})
    assert [(d['id'], d['ok']) for d in hb_live._doers(None)] == [('apex', True), ('fred', True)]


def _fred_db(doer, editor):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(task_id TEXT, agent TEXT, kind TEXT, payload TEXT)')
    c.execute('CREATE TABLE hb_clipboard(step_id TEXT PRIMARY KEY, importance INTEGER, doer TEXT, pin REAL, edited_by TEXT, updated_at REAL)')
    c.execute('INSERT INTO hb_clipboard VALUES (?,?,?,?,?,?)', ('S-1', None, doer, None, editor, 0))
    return c


def test_jd_picking_fred_on_the_list_is_jd_calling_fred():
    t = {'task_id': 'T-1', 'step_id': 'S-1'}
    assert tm.jd_asked_for_fred(_fred_db('fred', 'jd via the task board'), t)
    assert tm.jd_asked_for_fred(_fred_db('fred', 'JD via Telegram'), t)
    assert not tm.jd_asked_for_fred(_fred_db('fred', 'Claude Code (plan 20 Nov)'), t)
    assert not tm.jd_asked_for_fred(_fred_db('fred', 'APEX'), t)
    assert not tm.jd_asked_for_fred(_fred_db('apex', 'jd via the task board'), t)


def test_the_click_sends_the_choice_and_an_open_dropdown_survives_the_redraw():
    js = JS.read_text()
    assert 'data-a="doer"' not in js.split('function renderDoers')[0] and '<select data-q="clip" data-a="doer"' not in js
    assert "q.dataset.v ? [q.dataset.a, q.dataset.id, q.dataset.v] : [q.dataset.a, q.dataset.id]" in js
    assert "if (focus && focus.tagName === 'SELECT' && el.contains(focus)) return;" in js
