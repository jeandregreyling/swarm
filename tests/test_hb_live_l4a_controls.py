"""HB Live L4a: the Tasks window controls the clipboard through HB's routes; online models are doers."""
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
    fn = js[js.index('  function controlsFor'):js.index('  // Bound headers')]   # Practice 276: doer buttons, not a dropdown
    code = (f"const R=require({json.dumps(str(JS))}); const S={{snap:{{doers:[{{id:'apex',name:'APEX',ok:true}},{{id:'fred',name:'Fred',ok:true}}]}}}};" + fn +
            "; process.stdout.write(JSON.stringify([controlsFor({step_id:'S-1',task_id:'T-1',state:'waiting',parked:true,doer:'codex',importance:4}),"
            "controlsFor({step_id:'S-2',state:'needs_you'})]))")
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    parked, needs = json.loads(out.stdout)
    assert 'Try again' in parked and 'data-a="cancel"' in parked and 'imp 4</option>' in parked
    assert 'Codex' in parked and 'data-v="apex"' in parked and 'data-v="fred"' in parked and '<option value="codex"' not in parked
    assert 'data-a="accept"' in needs and 'data-a="cancel"' not in needs
