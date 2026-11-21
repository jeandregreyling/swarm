"""Practice 275 (JD 22 Nov: "when I open the task list and click on cancel it pops up a really fucked up confirmation box, the cancel button
itself should turn into a confirm button so I basically just have to double click on cancel"): no browser dialog - the first click arms
Cancel (red, "Confirm cancel"), the second within 4 s cancels. Both task lists: HB Live's clipboard and the older board."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / 'frontend/static/js/hb-live.js'
QUEUE = ROOT / 'frontend/static/js/views/hb-queue.js'


def _node(code):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(LIVE))}); process.stdout.write(JSON.stringify({code}))"],
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-500:]
    return json.loads(out.stdout)


def test_first_click_arms_second_click_within_four_seconds_acts():
    first = _node("R.arm(null, 'task:cancel:T-1', 1000)")
    assert first == {'act': False, 'armed': {'key': 'task:cancel:T-1', 'until': 5000}}
    assert _node("R.arm({key: 'task:cancel:T-1', until: 5000}, 'task:cancel:T-1', 4999)") == {'act': True, 'armed': None}


def test_a_late_second_click_or_another_button_only_arms_again():
    assert _node("R.arm({key: 'task:cancel:T-1', until: 5000}, 'task:cancel:T-1', 5001)")['act'] is False
    other = _node("R.arm({key: 'task:cancel:T-1', until: 5000}, 'task:cancel:T-2', 2000)")
    assert other['act'] is False and other['armed']['key'] == 'task:cancel:T-2'


def test_no_browser_dialog_is_left_in_either_task_list():
    live, queue = LIVE.read_text(), QUEUE.read_text()
    assert 'window.confirm' not in live and 'window.confirm' not in queue
    assert live.count('if (!armedClick(') == 2 and 'showArmed();' in live and '.hbl-armed{' in live
    assert "'Confirm ' +" in live and 'S.armed' in live
    assert "b.textContent = on ? 'confirm cancel' : 'cancel';" in queue and "&& !armedClick(t)) return;" in queue and '.hb-armed{' in queue
    for js in (LIVE, QUEUE):
        assert subprocess.run(['node', '--check', str(js)], capture_output=True).returncode == 0
