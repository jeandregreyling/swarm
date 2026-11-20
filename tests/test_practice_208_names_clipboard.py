"""Practice 208: real model names, readable card titles, chat is not a task, and the clipboard comes first."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_live, hb_tasks

JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live.js'


def test_stand_in_names_show_the_real_model(monkeypatch):
    monkeypatch.setattr('core.hb_apex_swap.playing', lambda: 'swift-qwen3.8-27b')
    monkeypatch.setattr('core.hb_apex_swap.backend', lambda: 'rocm')
    assert hb_live._real_model('apex-direct:20b') == 'swift-qwen3.8-27b'
    assert hb_live._real_model('gpt-oss:20b') == 'swift-qwen3.8-27b'
    assert hb_live._real_model('fred-cpu:24b') == 'fred-cpu:24b'


def test_json_titles_become_words():
    t = hb_live._title('APEX: {"task_type": "hb_managed_continuation", "task_id": "T-8E322F28857A", "sequence": 1, "reason": "Previous model turn ended"}')
    assert t == 'APEX: managed continuation T-8E322F28857A - Previous model turn ended'
    assert hb_live._title('APEX: {"task_type": "hb_x", "task_id": "T-1", "cut') == 'APEX: continuing T-1'
    assert hb_live._title('Repair 8') == 'Repair 8'


def test_chat_task_carries_only_the_last_three_lines():
    from core.hb_owner_intent import CHAT_MARK, CHAT_TITLE
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    hb_tasks.ensure_schema(c)
    say = lambda t: c.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content) VALUES (7,'user','apex',?)", (t,)).lastrowid
    task = hb_tasks.bind(c, 7, say('hi'), objective=CHAT_MARK, title=CHAT_TITLE, studio=False)
    for n in range(8):
        hb_tasks.bind(c, 7, say(f'line {n}'), task_id=task['task_id'])
    p = hb_tasks.packet(c, hb_tasks.get(c, task['task_id']))
    assert [i['content'] for i in p['instructions']] == ['line 5', 'line 6', 'line 7'] and p['older_instructions']['count'] == 5


def test_clipboard_comes_before_the_cards_and_survives_folding():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    snap = {'lanes': [{'id': 'gpu', 'items': [{'actor': 'APEX', 'title': 'turn', 'trail': [], 'last_step': 'x'}]}], 'needs_you': [],
            'master': {'on': True, 'items': [{'step_id': 'S-1', 'task_id': None, 'title': 'Plan step', 'state': 'waiting', 'group': 'waiting', 'doer': 'apex'}]}}
    code = (f"const R=require({json.dumps(str(JS))}); const s={json.dumps(snap)};"
            "process.stdout.write(JSON.stringify([R.renderBoard(s,{now:1}), R.renderBoard(s,{now:1,collapsed:true})]))")
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    full, folded = json.loads(out.stdout)
    assert full.index('Clipboard') < full.index('hbl-cards')
    assert 'data-cmd="/workflow next S-1">Start now' in full
    assert '📋 Clipboard · 1 open - show' in folded and 'hbl-cards' not in folded
