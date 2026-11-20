"""HB Live L3: the strip and windows render from one snapshot (renderers run in Node; the page loads the script)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'
SNAP = {'at': 1000, 'lanes': [
    {'id': 'gpu', 'label': 'GPU · APEX', 'state': 'busy', 'items': [{'actor': 'apex', 'model': 'swift-qwen3.8-27b', 'device': 'ROCm',
        'title': 'APEX: MCB <cap>', 'since': 900, 'purpose': 'main-chat turn', 'last_step': 'searching our notes: "MCB"',
        'trail': [{'at': 950, 'kind': 'step', 'text': 'APEX thinking - round 1'}, {'at': 960, 'kind': 'check', 'text': 'HB read check sent the answer back'}]}]},
    {'id': 'fred', 'label': 'CPU · Fred', 'state': 'idle', 'items': []},
    {'id': 'small', 'label': 'CPU · small', 'state': 'idle', 'items': [], 'note': 'translator on (manual)'},
    {'id': 'system', 'label': 'System', 'state': 'idle', 'items': []}],
    'needs_you': [{'kind': 'accept', 'label': 'Approve Studio S-1'}, {'kind': 'status', 'label': 'nothing ready'}],
    'master': {'on': True, 'auto': False, 'items': [{'step_id': 'S-1', 'task_id': 'T-1', 'title': 'MCB', 'state': 'now', 'doer': 'apex',
        'live': {'lane': 'gpu', 'last_step': 'reading'}}, {'step_id': 'S-2', 'title': 'Old bug', 'state': 'waiting', 'parked': True}]},
    'history': [{'lane': 'gpu', 'title': 'APEX: list vs tuple', 'at': 990, 'took_s': 17, 'outcome': 'ok', 'steps': 3, 'last': 'answered'}],
    'unexplained': [], 'telemetry': {'gpu': {'busy_pct': 61, 'temp_c': 55, 'vram_used_gb': 15.1, 'vram_total_gb': 16},
                                     'cpu': {'load1': 2.5, 'cores': 16}, 'ram': {'used_gb': 22, 'total_gb': 62.7}}}


def _node(expr):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    code = f"const R=require({json.dumps(str(JS))}); const snap={json.dumps(SNAP)}; process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, '-e', code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def test_strip_has_a_chip_per_lane_needs_tasks_and_system():
    html = _node('R.renderStrip(snap)')
    for word in ('data-win="gpu"', 'data-win="fred"', 'data-win="needs"', 'data-win="master"', 'data-win="system"', 'GPU 61%', 'now: MCB'):
        assert word in html
    assert 'hbl-busy' in html and '1 waiting' in html and 'data-win="system"' in html and html.count('data-win="system"') == 1


def test_lane_window_shows_live_trail_elapsed_and_finished_runs_escaped():
    html = _node('R.renderLane(snap, "gpu", 1000)')
    assert '1 min 40 s' in html and 'hbl-k-check' in html and 'APEX: MCB &lt;cap&gt;' in html and '<cap>' not in html
    assert 'list vs tuple' in html and '17 s' in html


def test_master_window_pins_needs_you_and_marks_parked_and_live():
    html = _node('R.renderMaster(snap)')
    assert html.index('Needs you') < html.index('>Now<') and 'parked by HB' in html and '● APEX: reading' in html
    assert 'nothing ready' not in html


def test_system_window_gauges():
    html = _node('R.renderSystem(snap)')
    assert 'VRAM' in html and 'CPU load' in html and 'translator on (manual)' in html


def test_page_loads_the_script_and_reads_one_snapshot():
    assert 'hb-live.js' in (ROOT / 'frontend/templates/terminal_base.html').read_text()
    js = JS.read_text()
    assert js.count("fetch('/api/peer/v1/hb/live'") == 1 and "addEventListener('sse:chat'" in js and 'localStorage' in js
