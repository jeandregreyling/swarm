"""Practice 279 (JD 22 Nov: "I see Apex and Fred, where's Claude, Codex, GIT?"): the task list offers Claude Code, Codex and Copilot (@git)
too, each with its real state; picking one sends it the task as JD's own @ request in main chat, the way typing @codex does."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_clipboard, hb_live, hb_tasks, peer_bridge

ROOT = Path(__file__).resolve().parents[1]


def _db():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    hb_tasks.ensure_schema(c)
    c.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY, title TEXT, description TEXT, status TEXT)')
    c.execute("INSERT INTO project_steps VALUES ('S-0123456789', 'Fix the board', 'Do: fix it. Done when: it works', 'todo')")
    c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT, tokens_used INT)')
    c.execute("INSERT INTO hb_tasks(task_id, conversation_id, root_message_id, title, objective, step_id) VALUES ('T-1', 2845, 1, 'Fix the board', 'Do: fix it', 'S-0123456789')")
    return c


@pytest.mark.parametrize('doer,recipient,mention', [('codex', 'codex-instructor', '@codex'), ('claude', 'claude-code', '@claude'),
                                                    ('copilot', 'copilot-instructor', '@git')])
def test_picking_an_online_agent_sends_it_the_task_as_jds_request(monkeypatch, doer, recipient, mention):
    sent = []
    monkeypatch.setattr(peer_bridge, 'enqueue', lambda conn, conv, mid, body, recipients, sender='user', **k: sent.append((conv, mid, body, recipients, sender)) or [77])
    c = _db()
    said = hb_clipboard.edit(c, ['doer', 'S-0123456789', doer], 'jd via the task board')
    assert 'sent to' in said and 'as your request' in said
    (conv, mid, body, recipients, sender), = sent
    assert conv == 2845 and recipients == [recipient] and sender == 'user'
    assert body.startswith(mention + ' ') and 'S-0123456789' in body and 'Fix the board' in body
    row = c.execute('SELECT from_agent, to_agent, content FROM messages WHERE id=?', (mid,)).fetchone()
    assert row[0] == 'user' and row[1] == recipient and row[2] == body and body.startswith(mention + ' JD picked you on the task list')


def test_the_list_offers_all_five_with_their_state(monkeypatch):
    from core import hb_online, hb_model_switches
    monkeypatch.setattr(hb_model_switches, 'modes', lambda conn: {})
    monkeypatch.setattr(hb_online, 'status', lambda conn, p: {'available': p != 'codex', 'reason': 'usage limit' if p == 'codex' else 'ok'})
    monkeypatch.setattr(hb_live, '_copilot_linked', lambda conn: False)
    doers = {d['id']: d for d in hb_live._doers(None)}
    assert list(doers) == ['apex', 'fred', 'claude', 'codex', 'copilot']
    assert doers['codex']['note'] == 'out of usage' and doers['copilot']['note'] == 'not connected' and not doers['claude'].get('note')
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    js = ROOT / 'frontend/static/js/hb-live.js'
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(js))}); process.stdout.write(R.renderDoers({{step_id:'S-1',doer:'apex'}}, {json.dumps(list(doers.values()))}))"],
                         capture_output=True, text=True, timeout=20).stdout
    for label in ('>Claude Code</button>', '>Codex (out of usage)</button>', '>Copilot (not connected)</button>', '>Fred</button>'):
        assert label in out, label
