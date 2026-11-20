"""Prepare HB Live L4a (Practice 189): controls in the Tasks window; Codex, Gemini and Claude are doers on the clipboard."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
CB = 'core/hb_clipboard.py'
JS = 'frontend/static/js/hb-live.js'

controls = r'''  // ── HB Live L4a: controls in the Tasks window, through HB's own routes (/hb/queue task, clip, switch) ──
  const DOER_CHOICES = ['apex', 'fred', 'small', 'hb', 'codex', 'gemini', 'claude'];
  function controlsFor(i) {
    const step = R.esc(i.step_id || ''), task = R.esc(i.task_id || '');
    let html = '<div class="hbl-ctl">';
    if (i.state === 'needs_you' && i.step_id) html += `<button type="button" data-q="task" data-a="accept" data-id="${step}">Approve</button>`;
    if (i.task_id) {
      if (i.parked) html += `<button type="button" data-q="task" data-a="continue" data-id="${task}" title="Give it a fresh try">Try again</button>`;
      else if (i.state === 'now') html += `<button type="button" data-q="task" data-a="pause" data-id="${task}">Pause</button>`;
      else html += `<button type="button" data-q="task" data-a="continue" data-id="${task}">Continue</button>`;
      html += `<button type="button" data-q="task" data-a="cancel" data-id="${task}" data-confirm="Cancel this task?">Cancel</button>`;
    }
    if (i.step_id) {
      html += `<button type="button" data-q="clip" data-a="top" data-id="${step}" title="Move to the top">⇈</button>` +
        `<button type="button" data-q="clip" data-a="up" data-id="${step}" title="Move up">↑</button>` +
        `<button type="button" data-q="clip" data-a="down" data-id="${step}" title="Move down">↓</button>` +
        `<select data-q="clip" data-a="importance" data-id="${step}" title="Importance (5 is highest)">` +
        [5, 4, 3, 2, 1].map((n) => `<option value="${n}"${Number(i.importance) === n ? ' selected' : ''}>imp ${n}</option>`).join('') + '</select>' +
        `<select data-q="clip" data-a="doer" data-id="${step}" title="Who does it - HB lines up this model">` +
        DOER_CHOICES.map((d) => `<option value="${d}"${(i.doer || 'apex') === d ? ' selected' : ''}>${d}</option>`).join('') + '</select>';
    }
    return html + '</div>';
  }
  function send(body, win) {
    const note = win && win.querySelector('.hbl-said');
    return fetch('/api/peer/v1/hb/queue', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) }).then((r) => r.json()).then((d) => {
      if (note) note.textContent = (d && (d.said || d.error || d.changed)) || '';
      refresh();
    }).catch(() => { if (note) note.textContent = 'HB did not answer - try again.'; });
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.hbl-win [data-q]');
    if (b && b.tagName === 'BUTTON') {
      if (b.dataset.confirm && !window.confirm(b.dataset.confirm)) return;
      send({ [b.dataset.q]: [b.dataset.a, b.dataset.id] }, b.closest('.hbl-win'));
    }
    const sw = e.target.closest('.hbl-win [data-switch]');
    if (sw) send({ switch: sw.dataset.switch, on: sw.dataset.on === '1' }, sw.closest('.hbl-win'));
  });
  document.addEventListener('change', (e) => {
    const s = e.target.closest('.hbl-win select[data-q]');
    if (s) send({ [s.dataset.q]: [s.dataset.a, s.dataset.id, s.value] }, s.closest('.hbl-win'));
  });
  S.controls = controlsFor;

  let pending = null;'''

edits = [
    {'path': CB, 'old': "DOERS = ('hb', 'small', 'apex', 'fred')\nDOER_WORDS = {'hb': 'HB itself (no model)', 'small': 'small CPU model', 'apex': 'APEX (14B on the GPU)', 'fred': 'Fred (24B on the CPU)'}",
     'new': "DOERS = ('hb', 'small', 'apex', 'fred', 'codex', 'gemini', 'claude')   # HB Live L4a (owner 20 Nov): online models are doers too\n"
            "DOER_WORDS = {'hb': 'HB itself (no model)', 'small': 'small CPU model', 'apex': 'APEX (on the GPU)', 'fred': 'Fred (24B on the CPU)',\n"
            "              'codex': 'Codex (online)', 'gemini': 'Gemini (online)', 'claude': 'Claude Code (online)'}"},
    {'path': CB, 'old': "  edit(...)       /clip up|down|top S-xxxx · /clip importance S-xxxx 1-5 · /clip doer S-xxxx hb|small|apex|fred · /clip clear S-xxxx",
     'new': "  edit(...)       /clip up|down|top S-xxxx · /clip importance S-xxxx 1-5 · /clip doer S-xxxx hb|small|apex|fred|codex|gemini|claude · /clip clear S-xxxx"},
    {'path': CB, 'old': '    """/clip up|down|top S-xxxx · /clip importance S-xxxx 1-5 · /clip doer S-xxxx hb|small|apex|fred · /clip clear S-xxxx"""',
     'new': '    """/clip up|down|top S-xxxx · /clip importance S-xxxx 1-5 · /clip doer S-xxxx <doer> · /clip clear S-xxxx (doers: DOERS)"""'},
    {'path': CB, 'old': "        return 'Use /clip up|down|top|clear S-xxxx, /clip importance S-xxxx 1-5, or /clip doer S-xxxx hb|small|apex|fred.'\n    action, step_id",
     'new': "        return 'Use /clip up|down|top|clear S-xxxx, /clip importance S-xxxx 1-5, or /clip doer S-xxxx ' + '|'.join(DOERS) + '.'\n    action, step_id"},
    {'path': CB, 'old': "    else:\n        return 'Use /clip up|down|top|clear S-xxxx, /clip importance S-xxxx 1-5, or /clip doer S-xxxx hb|small|apex|fred.'",
     'new': "    else:\n        return 'Use /clip up|down|top|clear S-xxxx, /clip importance S-xxxx 1-5, or /clip doer S-xxxx ' + '|'.join(DOERS) + '.'"},
    {'path': JS, 'old': "  let pending = null;", 'new': controls},
    {'path': JS, 'old': '''    let html = `<div class="hbl-note">HB is ${m.on === false ? '<b>paused</b> (Auto off)' : 'driving'}` +
      `${m.auto ? ' · auto-approve on' : ''} · ${items.length} open</div>`;''', 'new': '''    let html = `<div class="hbl-note">HB is ${m.on === false ? '<b>paused</b> (Auto off)' : 'driving'}` +
      `${m.auto ? ' · auto-approve on' : ''} · ${items.length} open` +
      (controls ? ` <span class="hbl-ctl"><button type="button" data-switch="auto" data-on="${m.on === false ? 1 : 0}">${m.on === false ? 'Start (Auto on)' : 'Stop (Auto off)'}</button></span>` : '') +
      '</div><div class="hbl-said hbl-dim"></div>';'''},
]

test = r'''"""HB Live L4a: the Tasks window controls the clipboard through HB's routes; online models are doers."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core import hb_clipboard

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'


def test_online_models_are_doers_and_edits_are_recorded():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE project_steps(step_id TEXT PRIMARY KEY)')
    c.execute("INSERT INTO project_steps VALUES ('S-ABCDEF0123')")
    c.execute('CREATE TABLE hb_tasks(task_id TEXT, step_id TEXT, state TEXT, created_at REAL)')
    for doer in ('codex', 'gemini', 'claude', 'fred'):
        said = hb_clipboard.edit(c, ['doer', 'S-ABCDEF0123', doer], 'JD via HB Live')
        assert hb_clipboard.DOER_WORDS[doer] in said and '(JD via HB Live)' in said
    assert c.execute('SELECT doer, edited_by FROM hb_clipboard').fetchone() == ('fred', 'JD via HB Live')
    assert 'codex' in hb_clipboard.edit(c, ['doer', 'S-ABCDEF0123', 'nobody'], 'JD')


def test_tasks_window_has_controls_through_the_queue_route():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    js = JS.read_text()
    assert "fetch('/api/peer/v1/hb/queue'" in js and "data-confirm=\"Cancel this task?\"" in js
    fn = js[js.index('const DOER_CHOICES'):js.index('function send')]
    code = ("const R={esc:s=>String(s)};" + fn + "; process.stdout.write(JSON.stringify([controlsFor({step_id:'S-1',task_id:'T-1',state:'waiting',parked:true,doer:'codex',importance:4}),"
            "controlsFor({step_id:'S-2',state:'needs_you'})]))")
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    parked, needs = json.loads(out.stdout)
    assert 'Try again' in parked and 'data-a="cancel"' in parked and '<option value="codex" selected>' in parked and 'imp 4</option>' in parked
    assert 'data-a="accept"' in needs and 'data-a="cancel"' not in needs
'''


def run(cmd):
    o = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=1500)
    if o.returncode:
        print(o.stdout[-6000:])
    return o


out = cs.prepare(STEP, why=("HB Live L4a (owner 20 Nov: see and control what the system is doing from main chat; HB orchestrates through the "
                            "clipboard). The Tasks window gets controls through HB's existing /hb/queue route: Approve, Pause, Continue, "
                            "Try again (parked), Cancel (confirmed), top/up/down, importance and doer, plus Auto start/stop; HB's answer "
                            "shows in the window. core/hb_clipboard: codex, gemini and claude are doers (recorded with who set them). "
                            "Routing a step to its doer follows in L4b."),
                 edits=edits, new_files={'tests/test_hb_live_l4a_controls.py': test},
                 test={'tests': ['tests/test_hb_live_l4a_controls.py', 'tests/test_hb_live_l3_page.py', 'tests/test_practice_180_parked_tasks.py'],
                       'keyword': ''}, run=run)
print(out['verified'])
