"""HB Live L5: the strip takes over main chat's HB widgets; Needs-you actions work from the Tasks window."""
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
