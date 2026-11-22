"""Practice 290 (JD 22 Nov: "the new settings window is not resizable and I do want things like downloads and background activity to be shown in
there ... and the network settings should also be in there showing which wifi/LAN is in use"): the Status drawer shows downloads, background
jobs and the networks (which one is in use), and the drawer has a drag grip on its left edge."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import hb_live

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'
NET = [{'name': 'enp5s0', 'kind': 'wired', 'up': True, 'default': True, 'metric': 100, 'mobile': False, 'label': '', 'network': 'Wired connection 1'},
       {'name': 'usb0', 'kind': 'usb tether', 'up': True, 'default': True, 'metric': 101, 'mobile': True, 'label': '', 'network': 'Phone'},
       {'name': 'wlan0', 'kind': 'wifi', 'up': False, 'default': False, 'metric': None, 'mobile': False, 'label': '', 'network': ''}]
HF = {'full_public_hub': {'state': 'in_progress', 'downloads_paused': False, 'active_transfer': {'repo': 'org/model', 'path': 'model.gguf'}}}
JOBS = [{'role': 'BA', 'model': 'homework-cpu:7b', 'task': 'Phone flow 1', 'steps': [{'what': 'asking the model for the spec'}]}]


def test_status_extra_says_which_network_is_in_use_and_what_is_downloading():
    x = hb_live.status_extra(net=NET, hf=HF, jobs=JOBS)
    assert [(n['name'], n['in_use'], n['backup'], n['mobile']) for n in x['network']] == [('Wired connection 1', True, False, False), ('Phone', False, True, True)]
    assert x['downloads'] == [{'what': 'Hugging Face mirror', 'state': 'in_progress', 'now': 'org/model / model.gguf', 'error': ''}]
    assert x['background'][0]['who'] == 'BA' and x['background'][0]['now'] == 'asking the model for the spec'


def test_the_drawer_shows_them_and_can_be_resized():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    x = hb_live.status_extra(net=NET, hf=HF, jobs=JOBS)
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(JS))}); process.stdout.write(R.renderStatus({{status_extra: {json.dumps(x)}, telemetry: {{}}}}, ''))"],
                         capture_output=True, text=True, timeout=20).stdout
    for words in ('Downloads &amp; background', 'Hugging Face mirror', 'org/model / model.gguf', 'BA', 'Network', '● in use', 'Wired connection 1', '○ backup', 'mobile data'):
        assert words in out, words
    js = JS.read_text()
    assert 'hbl-drawer-grip' in js and "ls('hbLive.drawerW'" in js and 'ew-resize' in js
