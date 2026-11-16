"""Practice 126 (owner 17 Nov 2026): "I can't really see what HB is busy with at the moment, I just hear the fans". HB's live activity only
appeared at the end of the message list and showed nothing when idle. The chat bar now always says "HB now: <what runs>" or "HB now: idle"."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / 'frontend/static/js/hb-live-activity.js'

HARNESS = r"""
const src = require('fs').readFileSync(process.argv[2], 'utf8');
const els = {};
const mk = () => ({style: {}, textContent: '', title: '', appendChild(n) { this.child = n; }});
const bar = mk();
global.document = {hidden: false, body: {contains: () => true},
  querySelector: s => s === '#home-chat-bar .home-chat-bar-left' ? bar : null,
  querySelectorAll: () => [], getElementById: id => els[id] || null,
  createElement: () => { const n = mk(); return new Proxy(n, {set(t, k, v) { t[k] = v; if (k === 'id') els[v] = t; return true; }}); }};
let reply = JSON.parse(process.argv[3]);
global.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve(reply)});
global.setInterval = () => 0;
eval(src);
setTimeout(() => {
  const first = els['hb-now'] && els['hb-now'].textContent;
  reply = {running: false, lines: []};
  fetch().then(r => r.json()).then(() => {});
  console.log(JSON.stringify({first}));
}, 50);
"""


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_practice_126_the_bar_says_what_runs(tmp_path):
    h = tmp_path / 'h.js'
    h.write_text(HARNESS)
    busy = {'running': True, 'lines': ['HOMEWORK (homework-cpu:7b, CPU / RAM) - S-3AE9 Audit fix', '  stage: writing the spec card']}
    out = subprocess.run(['node', str(h), str(JS), json.dumps(busy)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1])['first'] == 'HB now: HOMEWORK (homework-cpu:7b, CPU / RAM) - S-3AE9 Audit fix'


def test_practice_126_idle_is_said_too():
    src = JS.read_text()
    assert "'idle'" in src and 'now(data);' in src and "getElementById('hb-now')" in src
    if shutil.which('node'):
        assert subprocess.run(['node', '--check', str(JS)], capture_output=True).returncode == 0
