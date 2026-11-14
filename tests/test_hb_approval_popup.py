"""Practice 24 (owner 14 Nov): "the approvals should be in the header banner as well as have a popup in the main chat linked to
it, otherwise I keep having to check 'is there something that needs checking'".

frontend/static/js/views/hb-approval-popup.js, loaded after hb-needs-you.js: the header's needs-you counter glows while something
waits; a popup in main chat names the newest item (Show jumps to it in the Needs-you bar; Later hides it until something new)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/views/hb-approval-popup.js'
BASE = ROOT / 'frontend/templates/terminal_base.html'

HARNESS = r"""
const fs = require('fs');
const body = { kids: [], appendChild(e) { this.kids.push(e); e.parent = this; } };
function el(tag) {
  return { tag, id: '', innerHTML: '', textContent: '', attrs: {}, setAttribute(k, v) { this.attrs[k] = v; },
    remove() { body.kids = body.kids.filter(k => k !== this); },
    querySelector(sel) { const self = this; self.btn = self.btn || {}; return (self.btn[sel] = self.btn[sel] || {}); } };
}
const head = { appendChild(e) { this.css = e; } };
global.document = { head, body, createElement: el, getElementById: id => body.kids.find(e => e.id === id) || (head.css && head.css.id === id ? head.css : null) };
let items = JSON.parse(process.argv[3]); let focused = 0;
global.window = { hbNeedsYouItems: () => items, hbNeedsFocusBar: () => { focused++; } };
global.setInterval = () => 0; global.setTimeout = () => 0;
eval(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
window.hbApprovalPopupCheck();
const pop = () => body.kids.find(e => e.id === 'hb-approval-popup');
out.first = pop() ? pop().innerHTML : null;
out.css = head.css ? head.css.textContent : '';
pop().querySelector('.hb-pop-show').onclick(); out.focused = focused;
pop().querySelector('.hb-pop-later').onclick(); out.afterLater = pop() ? pop().innerHTML : null;
items = items.concat([{ key: 'new', kind: 'accept', label: 'DOES rename 5' }]); window.hbApprovalPopupCheck();
out.afterNew = pop() ? pop().innerHTML : null;
items = []; window.hbApprovalPopupCheck(); out.afterHandled = pop() ? pop().innerHTML : null;
console.log(JSON.stringify(out));
"""
ITEMS = [{'key': 'info', 'kind': 'status', 'label': 'Plan workflow', 'info': True},
         {'key': 'a', 'kind': 'halted', 'label': 'DOES rename 4 <stuck>'},
         {'key': 'b', 'kind': 'accept', 'label': 'Practice 15'}]


def test_practice_24_popup_file_exists_and_parses():
    assert JS.exists(), 'create frontend/static/js/views/hb-approval-popup.js'
    node = shutil.which('node')
    if node:
        subprocess.run([node, '--check', str(JS)], check=True, capture_output=True)
    assert 'hbNeedsYouItems' in JS.read_text() and 'dial-needs-you' in JS.read_text()


def test_practice_24_page_loads_the_popup_after_the_needs_you_bar():
    html = BASE.read_text()
    assert html.index('<script src="/static/js/views/hb-approval-popup.js?v={{ ASSET_VERSION }}"></script>') > \
        html.index('/static/js/views/hb-needs-you.js')


def test_practice_24_popup_and_glowing_header(tmp_path):
    node = shutil.which('node')
    if not node or not JS.exists():
        pytest.skip('node or the popup file is missing')
    script = tmp_path / 'harness.js'
    script.write_text(HARNESS)
    out = json.loads(subprocess.run([node, str(script), str(JS), json.dumps(ITEMS)], check=True, capture_output=True, text=True).stdout)
    assert 'Needs you:</b> Approve - Practice 15' in out['first'] and 'and 1 more waiting' in out['first']   # newest first, info ignored
    assert '&lt;stuck&gt;' not in out['first'] and 'Plan workflow' not in out['first']
    assert '#dial-needs-you:not([data-count="0"])' in out['css']                                          # the header counter glows
    assert out['focused'] == 1                                                                             # Show -> the Needs-you bar
    assert out['afterLater'] is None                                                                       # Later hides it...
    assert 'DOES rename 5' in out['afterNew'] and 'more waiting' not in out['afterNew']                    # ...until something new
    assert out['afterHandled'] is None                                                                     # handled: gone
