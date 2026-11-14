"""Practice 29 (owner 14 Nov; replaces practice 23's holder): "the auto approve and auto continue buttons aren't there ... the clipboard (which
is still not visible) needs to be updated by HB and the tasks updated in real time".

frontend/static/js/views/hb-queue.js puts HB's clipboard right above the chat messages (always visible): driving or paused, open and done,
now / next, the background work (homework, counsel), and on click every task with its doer, importance, Ready and check result. The Auto and
Approve switches sit under the chat box. The page loads the script once (and the brand icons once)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/views/hb-queue.js'
BASE = ROOT / 'frontend/templates/terminal_base.html'

HARNESS = r"""
const fs = require('fs');
function el(tag) { return { tag, id: '', className: '', innerHTML: '', dataset: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; },
  insertAdjacentElement(_, e) { this.after = e; byId[e.id] = e; }, appendChild(e) {} }; }
const byId = {};
const parent = { insertBefore(e, ref) { this.first = e; byId[e.id] = e; } };
byId['home-chat-messages'] = { parentNode: parent };
byId['home-chat-meta'] = el('div'); byId['home-chat-agent-count'] = el('span');
global.document = { hidden: false, head: el('head'), createElement: el, addEventListener() {}, getElementById: id => byId[id] || null };
global.window = {}; global.setInterval = () => 0; global.setTimeout = () => 0; global.AbortSignal = { timeout: () => undefined };
const states = JSON.parse(process.argv[3]); const posts = [];
global.fetch = async (url, opts) => { if (opts && opts.method === 'POST') { posts.push(JSON.parse(opts.body)); return { ok: true, json: async () => states[1] }; }
  return { ok: true, json: async () => states[0] }; };
eval(fs.readFileSync(process.argv[2], 'utf8'));
(async () => {
  await window.hbQueueRefresh();
  const clip = byId['hb-clipboard'], box = byId['hb-switches'];
  const closed = clip.innerHTML, offSwitches = box.innerHTML;
  clip.onclick({ target: { closest: s => s === '.hb-clip-head' ? {} : null } });
  await new Promise(r => setImmediate(r));
  const open = clip.innerHTML;
  box.onclick({ target: { closest: s => s === '[data-switch]' ? { dataset: { switch: 'auto' }, getAttribute: () => 'false' } : null } });
  await new Promise(r => setImmediate(r));
  console.log(JSON.stringify({ aboveMessages: parent.first === clip, switchesAfterCount: byId['home-chat-agent-count'].after === box,
    closed, open, offSwitches, onSwitches: box.innerHTML, posts }));
})();
"""
ITEMS = [{'step_id': 'S-0000000001', 'title': 'Practice 28', 'state': 'now', 'why': '', 'doer': 'apex', 'importance': 4, 'ready': True,
          'check_result': 'passing'},
         {'step_id': 'S-0000000002', 'title': 'Potato <Farm>', 'state': 'waiting', 'why': 'not scoped', 'doer': 'fred', 'importance': 2,
          'ready': False, 'check_result': 'not run yet'}]
OFF = {'ok': True, 'on': False, 'auto': True, 'open': 2, 'done_24h': 9, 'summary': 's', 'items': ITEMS,
       'background': [{'role': 'Homework', 'model': 'homework-cpu:7b', 'task': 'Potato Farm', 'now': 'writing the spec card'}]}
ON = {**OFF, 'on': True, 'auto': False}


def test_practice_29_file_parses_and_page_loads_scripts_once():
    assert JS.exists()
    if shutil.which('node'):
        subprocess.run(['node', '--check', str(JS)], check=True, capture_output=True)
    html = BASE.read_text()
    assert html.count('/static/js/views/hb-queue.js') == 1 and html.count('/static/js/views/hb-brand-icons.js') == 1
    assert 'home-chat-messages' in JS.read_text() and 'background' in JS.read_text()


def test_practice_29_clipboard_above_the_messages_with_tasks_background_and_switches(tmp_path):
    if not shutil.which('node'):
        pytest.skip('node is missing')
    h = tmp_path / 'h.js'
    h.write_text(HARNESS)
    v = json.loads(subprocess.run(['node', str(h), str(JS), json.dumps([OFF, ON])], check=True, capture_output=True, text=True).stdout)
    assert v['aboveMessages'] and v['switchesAfterCount']
    assert '<b>HB</b>' in v['closed'] and 'paused · 2 open · 9 done today' in v['closed'] and 'now: Practice 28' in v['closed']
    assert 'data-hb-icon="sprout"></span> Homework (homework-cpu:7b): writing the spec card' in v['closed'] and 'hb-clip-list' not in v['closed']
    assert 'hb-clip-list' in v['open'] and 'Potato &lt;Farm&gt;' in v['open'] and 'Fred · importance 2' in v['open'] and 'check passing' in v['open']
    assert 'class="hb-chip ready">ready' in v['open'] and '>no card<' in v['open']
    assert 'data-switch="auto" aria-pressed="false"' in v['offSwitches'] and 'data-switch="approve"' not in v['offSwitches']
    assert v['posts'] == [{'switch': 'auto', 'on': True}]
    assert 'class="hb-switch on" data-switch="auto"' in v['onSwitches'] and 'data-switch="approve" aria-pressed="false"' in v['onSwitches']
