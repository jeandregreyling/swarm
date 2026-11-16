"""Practice 96 (owner 16 Nov 2026): "why can't I see the downloads progress in main chat?" HB's SAP notes progress lines were in chat
2845 but the open page never showed them: background lines are written straight to the database, and the page refreshed only on a
live event, a reload or a tab switch. The 30-second chat-list check now fetches the open chat when it has a newer message."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / 'frontend' / 'static' / 'js' / 'views' / 'home-chat.js'

HARNESS = r"""
const src = require('fs').readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('  let _hcLastSeenAt');
const end = src.indexOf('  setInterval(() => { if (!document.hidden) _hcElsewhere(); }');
let _hcConvId = 2845, _hcSending = false, refreshed = [], at = '2026-11-16 03:45:51';
const _hcSilentRefresh = id => refreshed.push(id);
const _hcEsc = s => s;
const document = { querySelector: () => ({ appendChild() {} }), getElementById: () => null };
const fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 2845, last_message_at: at }]) });
eval(src.slice(start, end) + '; globalThis.check = _hcElsewhere;');
const tick = () => { check(); return new Promise(r => setTimeout(r, 20)); };
(async () => {
  await tick();                                   // first look: remember, nothing to fetch
  await tick();                                   // nothing new
  at = '2026-11-16 04:00:51'; await tick();       // HB posted a progress line in the background
  _hcSending = true; at = '2026-11-16 04:01:00'; await tick();   // JD is sending: the send path refreshes itself
  console.log(JSON.stringify(refreshed));
})();
"""


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_practice_96_the_open_chat_fetches_a_background_line(tmp_path):
    h = tmp_path / 'h.js'
    h.write_text(HARNESS)
    out = subprocess.run(['node', str(h), str(JS)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [2845]


def test_practice_96_home_chat_still_parses():
    if shutil.which('node'):
        out = subprocess.run(['node', '--check', str(JS)], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
    assert '_hcLastSeenAt' in JS.read_text()
