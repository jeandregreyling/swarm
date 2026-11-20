"""Practice 194: the board inside main chat - groups, one primary action, Needs-you pop-up, clickable commands, /board."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_live

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'


def test_groups():
    g = hb_live._group
    assert g({'state': 'now'}, None) == 'now' and g({'state': 'waiting', 'parked': True}, None) == 'parked'
    assert g({'state': 'waiting', 'why': 'needs a spec: no done-when'}, None) == 'spec'
    assert g({'state': 'waiting', 'why': 'no HB task in main chat'}, 'Needs a spec: is Seven still used?') == 'spec'
    assert g({'state': 'waiting', 'why': 'no HB task in main chat', 'doer': 'claude'}, None) == 'claude'
    assert g({'state': 'waiting', 'why': 'held by you'}, None) == 'waiting'


def test_master_adds_other_owners_steps_as_roadmap(monkeypatch):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE project_steps(step_id TEXT, project_id TEXT, title TEXT, status TEXT, owner TEXT, residual_risk TEXT, order_idx REAL, created_at REAL)')
    c.executemany('INSERT INTO project_steps VALUES (?,?,?,?,?,?,?,?)', [('S-1', 'P', 'Bug A', 'todo', 'apex', None, 1, 0),
                  ('S-2', 'P', 'Roles not names', 'todo', 'claude-code', None, 2, 0), ('S-3', 'P', 'Done one', 'done', 'claude-code', None, 3, 0)])
    from core import hb_queue
    monkeypatch.setattr(hb_queue, 'PROJECT', 'P')
    monkeypatch.setattr(hb_queue, 'status', lambda conn: {'on': True, 'items': [{'step_id': 'S-1', 'task_id': 'T-1', 'title': 'Bug A', 'state': 'waiting', 'parked': True}]})
    m = hb_live._master(c, {})
    assert [(i['step_id'], i['group']) for i in m['items']] == [('S-1', 'parked'), ('S-2', 'roadmap')]


def test_board_text_has_the_commands_that_move_each_row():
    snap = {'master': {'on': True, 'items': [
        {'step_id': 'S-1', 'task_id': 'T-1', 'title': 'MCB research', 'group': 'now', 'live': {'last_step': 'reading KC document 7'}},
        {'step_id': 'S-2', 'task_id': 'T-2', 'title': 'Seven runtime', 'group': 'parked'},
        {'step_id': 'S-3', 'task_id': 'T-3', 'title': 'DAW review', 'group': 'spec'},
        {'step_id': 'S-4', 'title': 'Roles', 'group': 'roadmap'}]},
        'needs_you': [{'kind': 'accept', 'step_id': 'S-9', 'label': 'Approve S-9'}, {'kind': 'status', 'label': 'x'}]}
    text = hb_live.board_text(snap)
    for line in ('3 open, 1 need you', 'Approve S-9 → /accept S-9', 'MCB research (reading KC document 7) → /pause T-1',
                 'Seven runtime → /continue T-2', 'DAW review → /done T-3', 'Roadmap: 1 planned items', '/drive on'):
        assert line in text


def _node(code):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


SNAP = {'at': 1000, 'lanes': [{'id': 'gpu', 'state': 'busy', 'items': [{'actor': 'apex', 'model': 'swift-qwen3.8-27b', 'device': 'ROCm',
        'title': 'APEX: MCB', 'since': 900, 'last_step': 'reading KC', 'trail': [{'at': 950, 'kind': 'step', 'text': 'round 1'}]}]},
        {'id': 'fred', 'state': 'idle', 'items': []}],
        'needs_you': [{'key': 'accept:S-1', 'kind': 'accept', 'step_id': 'S-1', 'label': 'Approve S-1'}],
        'master': {'on': True, 'items': [{'step_id': 'S-1', 'task_id': 'T-1', 'title': 'MCB', 'state': 'now', 'group': 'now'},
                                         {'step_id': 'S-2', 'task_id': 'T-2', 'title': 'Old bug', 'group': 'parked', 'parked': True},
                                         {'step_id': 'S-4', 'title': 'Roles not names', 'group': 'roadmap'}]},
        'history': [], 'unexplained': [], 'telemetry': {'gpu': {'busy_pct': 61, 'vram_used_gb': 13.2, 'vram_total_gb': 16}}}


def test_board_shows_only_active_workers_and_the_grouped_list():
    out = _node(f"const R=require({json.dumps(str(JS))}); const s={json.dumps(SNAP)}; process.stdout.write(JSON.stringify("
                "[R.renderBoard(s,{now:1000,controls:()=>'<i>c</i>',needsControls:()=>'<i>n</i>'}), R.renderActive(Object.assign({},s,{lanes:[],needs_you:[]}))]))")
    board, idle = out
    assert 'APEX' in board and 'reading KC' in board and 'data-card' in board and 'Fred' not in board
    assert 'Try again' in board and '>Pause<' in board and 'Roadmap (1)' in board and 'Roles not names' not in board
    assert '2.8 GB free for you' in board and 'Everyone is idle' in idle


def test_commands_in_chat_become_buttons_and_page_keeps_one_fetch():
    js = JS.read_text()
    line = next(l for l in js.splitlines() if l.strip().startswith('const CMD = '))
    code = line.strip() + " const t='Reply: /continue T-ABCDEF123456 · /accept S-ABCDEF0123 and /workflow off; not /etc/passwd';" \
        " process.stdout.write(JSON.stringify(t.match(CMD).map(s => s.trim())));"
    found = _node(code)
    assert found == ['/continue T-ABCDEF123456', '/accept S-ABCDEF0123', '/workflow off']
    assert js.count("fetch('/api/peer/v1/hb/live'") == 1 and 'resize:vertical' in js and "id = 'hb-live-pop'" in js
    assert "text.startsWith('{\"task_type\"')" in js
