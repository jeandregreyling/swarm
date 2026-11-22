"""Practice 287 (JD 22 Nov): "the live status dropdown is hideously designed and completely unusable ... the context of that section is also
quite fucked"; "it's not posting its own token usage in main chat next to its name anymore (as should all actors)"; "the round button that
hovers in the main chat window at the bottom right corner when I scroll up ... and if I double click it, it ... stays tracking the bottom".
Live status becomes a clean Status drawer in HB Live (APEX, its window, GPU/CPU mode, the model switches; no archive/bridge noise), the token
count sits next to the sender's name, and main chat has the round jump-to-latest button with double-click follow mode."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'
CHAT = ROOT / 'frontend/static/js/views/chat.js'
SNAP = {'apex_live': {'up': True, 'busy': False, 'model': 'mistral-nemo-12b-abliterated', 'device': 'ROCm', 'ctx': 49664},
        'telemetry': {'gpu': {'clock_limit_mhz': 2159, 'power_cap_w': 227, 'gpu_mode': 'stock'}, 'cpu': {'governor': 'powersave', 'epp': 'balance_performance'}},
        'lanes': [], 'needs_you': [], 'master': {'items': []}, 'history': []}


def _node(expr):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(JS))}); const snap={json.dumps(SNAP)}; process.stdout.write(JSON.stringify({expr}))"],
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-400:]
    return json.loads(out.stdout)


def test_the_status_drawer_shows_what_matters_and_the_switches():
    html = _node("R.renderStatus(snap, '<b>models</b>')")
    assert 'mistral-nemo-12b-abliterated' in html and '49,664 tokens' in html and 'ROCm' in html
    assert 'data-hb-models' in html and '<b>models</b>' in html and 'Auto (stock)' in html and 'CPU balanced' in html
    assert 'archive' not in html.lower() and 'bridge' not in html.lower()


def test_the_banner_has_a_status_chip_next_to_tasks():
    html = _node('R.renderBoard(snap, {drawer: true})')
    assert 'data-drawer="status"' in html and 'data-drawer="tasks"' in html


def test_main_chat_has_the_round_jump_button_with_follow_mode():
    js = JS.read_text()
    assert "b.id = 'hb-scroll-bottom'" in js and "addEventListener('dblclick'" in js and 'hbLive.follow' in js and 'MutationObserver' in js
    assert '#hb-scroll-bottom{' in js and 'border-radius:50%' in js


def test_the_token_count_sits_next_to_the_senders_name():
    chat = CHAT.read_text()
    assert '<span class="chat-tok-chip"' in chat
    assert 'margin-left:auto;white-space:nowrap;">${_tokCount ?' not in chat
    assert subprocess.run(['node', '--check', str(JS)], capture_output=True).returncode == 0
