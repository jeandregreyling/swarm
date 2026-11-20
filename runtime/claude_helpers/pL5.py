"""Prepare HB Live L5 (Practice 190): the strip takes over main chat's HB widgets; Needs-you actions live in the Tasks window."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
JS = 'frontend/static/js/hb-live.js'
OLD = 'frontend/static/js/hb-live-activity.js'

edits = [
    {'path': JS, 'old': '  function renderMaster(snap, controls) {', 'new': '  function renderMaster(snap, controls, needsControls) {'},
    {'path': JS, 'old': """        `<li class="hbl-needs"><span class="hbl-tag">${esc(n.kind || 'review')}</span> ${esc(n.label || n.text || '')}</li>`).join('') + '</ul>';""",
     'new': """        `<li class="hbl-needs" title="${esc(n.why || n.title || '')}"><span class="hbl-tag">${esc(n.kind || 'review')}</span> ${esc(n.label || n.text || '')}` +
        (n.title && n.title !== n.label ? `<div class="hbl-dim">${esc(n.title)}</div>` : '') + (needsControls ? needsControls(n) : '') + '</li>').join('') + '</ul>';"""},
    {'path': JS, 'old': "    if (id === 'master' || id === 'needs') return R.renderMaster(s, S.controls);",
     'new': "    if (id === 'master' || id === 'needs') return R.renderMaster(s, S.controls, S.needsControls);"},
    # Needs-you actions: show the message, run HB's suggested command, continue / cancel the task
    {'path': JS, 'old': "  S.controls = controlsFor;", 'new': r"""  S.controls = controlsFor;

  // HB Live L5: everything the old Needs-you bar could do, in the Tasks window
  function needsControlsFor(n) {
    let html = '<div class="hbl-ctl">';
    if (n.kind === 'accept' && n.step_id) html += `<button type="button" data-q="task" data-a="accept" data-id="${R.esc(n.step_id)}">Approve</button>`;
    if (n.open && n.open.type === 'message' && n.open.id) html += `<button type="button" data-show="${Number(n.open.id)}">Show in chat</button>`;
    (n.actions || []).forEach((a) => { if (a && a.command) html += `<button type="button" data-cmd="${R.esc(a.command)}">${R.esc(a.label || a.command)}</button>`; });
    if (n.task_id && n.kind !== 'accept') {
      html += `<button type="button" data-q="task" data-a="continue" data-id="${R.esc(n.task_id)}">Continue</button>` +
        `<button type="button" data-q="task" data-a="cancel" data-id="${R.esc(n.task_id)}" data-confirm="Cancel this task?">Cancel</button>`;
    }
    return html + '</div>';
  }
  S.needsControls = needsControlsFor;
  document.addEventListener('click', (e) => {
    const show = e.target.closest('.hbl-win [data-show]');
    if (show) {
      const m = document.querySelector(`#home-chat-messages [data-message-id="${Number(show.dataset.show)}"]`);
      if (m) { m.scrollIntoView({ behavior: 'smooth', block: 'center' }); m.style.outline = '2px solid #ffb300'; setTimeout(() => { m.style.outline = ''; }, 2500); }
    }
    const cmd = e.target.closest('.hbl-win [data-cmd]');
    if (cmd) {
      const input = document.getElementById('home-chat-input');
      if (input) { input.value = cmd.dataset.cmd; input.dispatchEvent(new Event('input', { bubbles: true })); document.getElementById('home-chat-send-btn')?.click(); }
    }
  });"""},
    # The strip takes over: hide main chat's older HB widgets (the Chat window keeps its own board); one escape hatch back
    {'path': JS, 'old': '  function strip() {\n', 'new': """  function classic() { try { return localStorage.getItem('hbLive.classic') === '1'; } catch (e) { return false; } }
  function strip() {
    if (classic()) { document.body.classList.remove('hb-live-on'); return null; }
    document.body.classList.add('hb-live-on');   // HB Live L5: hides the HB-now pill, live box, HB Driving board and Needs-you bar in main chat
"""},
    {'path': JS, 'old': "@media (max-width:640px){", 'new': """body.hb-live-on #hb-now,body.hb-live-on #hb-live-activity,body.hb-live-on #hb-clipboard,body.hb-live-on #home-chat-main .hb-needs-you{display:none!important}
@media (max-width:640px){"""},
    {'path': JS, 'old': "    if (document.hidden || S.busy) return;", 'new': "    if (document.hidden || S.busy || classic()) return;"},
    {'path': JS, 'old': "  root.hbLive = { open, close, toggle, refresh, state: S,",
     'new': "  root.hbLive = { classic: (on) => { try { localStorage.setItem('hbLive.classic', on ? '1' : '0'); } catch (e) {} location.reload(); }, open, close, toggle, refresh, state: S,"},
    # the old live-activity poller stops when the strip is on (its two outputs are hidden)
    {'path': OLD, 'old': "  function tick() {\n    if (document.hidden) return;",
     'new': "  function tick() {\n    if (document.hidden || (document.body && document.body.classList && document.body.classList.contains('hb-live-on'))) return;   // HB Live L5: the strip took over"},
]

test = r'''"""HB Live L5: the strip takes over main chat's HB widgets; Needs-you actions work from the Tasks window."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'frontend/static/js/hb-live.js').read_text()


def test_older_widgets_are_hidden_in_main_chat_with_an_escape_hatch():
    rule = 'body.hb-live-on #hb-now,body.hb-live-on #hb-live-activity,body.hb-live-on #hb-clipboard,body.hb-live-on #home-chat-main .hb-needs-you{display:none!important}'
    assert rule in JS and "document.body.classList.add('hb-live-on')" in JS and "localStorage.getItem('hbLive.classic') === '1'" in JS
    old = (ROOT / 'frontend/static/js/hb-live-activity.js').read_text()
    assert "document.body.classList.contains('hb-live-on'))) return;" in old


def test_needs_you_actions_render():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    fn = JS[JS.index('function needsControlsFor'):JS.index('S.needsControls = needsControlsFor;')]
    items = [{'kind': 'accept', 'step_id': 'S-1', 'label': 'Approve S-1'},
             {'kind': 'review', 'task_id': 'T-1', 'open': {'type': 'message', 'id': 18323}, 'actions': [{'label': 'Stop the workflow', 'command': '/workflow off'}]}]
    code = "const R={esc:s=>String(s)};" + fn + f"; process.stdout.write(JSON.stringify({json.dumps(items)}.map(needsControlsFor)))"
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    accept, review = json.loads(out.stdout)
    assert 'data-a="accept" data-id="S-1"' in accept and 'Show in chat' not in accept
    assert 'data-show="18323"' in review and 'data-cmd="/workflow off"' in review and 'data-a="continue" data-id="T-1"' in review
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("HB Live L5 (owner 20 Nov: \"Needs you and HB Driving still seem disconnected\"; docs/spec-hb-live-dashboard.md). "
                            "With the live strip mounted (body.hb-live-on), main chat's older HB widgets are hidden - the HB-now pill, the "
                            "live box under the bubble, the HB Driving board and the Needs-you bar - and the old live-activity poller stops. "
                            "The Tasks window carries the Needs-you actions: Approve, Show in chat, HB's suggested commands (/workflow off ...), "
                            "Continue, Cancel. The Chat window keeps its own board. Escape hatch: hbLive.classic(true) brings the old view back."),
                 edits=edits, new_files={'tests/test_hb_live_l5_takeover.py': test},
                 test={'tests': ['tests/test_hb_live_l5_takeover.py', 'tests/test_hb_live_l4a_controls.py', 'tests/test_hb_live_l3_page.py',
                                 'tests/test_hb_live_activity.py', 'tests/test_practice_126_hb_now.py', 'tests/test_practice_177_activity_box.py',
                                 'tests/test_practice_179_arrow_and_idle.py', 'tests/test_practice_164_activity_route.py'], 'keyword': ''}, run=run)
print(out['verified'])
