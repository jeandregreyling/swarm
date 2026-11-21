"""Practice 285 (JD 22 Nov: "why is the clipboard just sort of dangling below HB live ... a waste of space making the top banner larger ...
modernise it, and 'Apex your assistant with show team & tasks' also seems a bit out of place below it ... make it more functional"): the
banner keeps only who is working; the task list is a drawer on the right opened by a Tasks chip; the old team bar becomes one row of
talk-to buttons (@apex, @fred, @claude, @codex, @git, @gemini) in the banner."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'
SNAP = {'at': 1000, 'apex_live': {'up': True, 'busy': False, 'prompt_tokens': 1},
        'lanes': [{'id': 'gpu', 'state': 'busy', 'items': [{'actor': 'apex', 'title': 'APEX: x', 'trail': []}]}],
        'needs_you': [{'kind': 'accept', 'label': 'Approve S-1'}],
        'master': {'on': True, 'items': [{'step_id': 'S-1', 'task_id': 'T-1', 'title': 'Task one', 'state': 'waiting', 'group': 'waiting'},
                                         {'step_id': 'S-2', 'task_id': 'T-2', 'title': 'Task two', 'state': 'waiting', 'group': 'waiting'}]},
        'history': [], 'telemetry': {}}


def _node(expr):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(JS))}); const snap={json.dumps(SNAP)}; process.stdout.write(JSON.stringify({expr}))"],
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-400:]
    return json.loads(out.stdout)


def test_the_banner_keeps_only_who_is_working_and_a_tasks_chip():
    html = _node('R.renderBoard(snap, {drawer: true})')
    assert 'hbl-board' not in html and 'Task one' not in html
    assert 'data-drawer="1"' in html and '📋 Tasks · 2 open · 1 needs you' in html and 'hbl-active' in html


def test_the_drawer_holds_the_task_list():
    html = _node('R.renderDrawer(snap, {})')
    assert 'Task one' in html and 'Task two' in html and 'data-drawer="1"' in html and 'hbl-drawer-head' in html


def test_talk_to_buttons_replace_the_team_bar():
    html = _node('R.renderTalk()')
    for at in ('apex', 'fred', 'claude', 'codex', 'git', 'gemini'):
        assert f'data-at="{at}"' in html, at
    assert 'Talk to' in _node('R.renderBoard(snap, {drawer: true})')


def test_the_page_wires_the_drawer_and_hides_the_old_team_bar():
    js = JS.read_text()
    assert "const SCOPE = '#hb-live-pane, #hb-live-pop, #hb-live-drawer, #home-chat-messages';" in js
    assert "body.hb-live-on .chat-team>.chat-team-people" in js and '#hb-live-drawer{' in js
    assert "ls('hbLive.drawer')" in js and 'insertAt(' in js
    assert subprocess.run(['node', '--check', str(JS)], capture_output=True).returncode == 0
