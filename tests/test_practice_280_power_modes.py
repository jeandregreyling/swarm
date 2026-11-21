"""Practice 280 (JD 22 Nov: the 'powersave' tag "doesn't tell me anything it does and doesn't allow me to select overclock or any other mode
like Auto"): HB Live names the CPU mode in words and has GPU buttons Auto (stock) and Overclock (JD's tested profile, double-click to confirm)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import hb_power

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'frontend/static/js/hb-live.js'


def test_switch_runs_jds_helper_in_the_background_and_says_so():
    ran, started = [], []
    said = hb_power.switch_gpu('jd_tested', start=lambda f: started.append(f), tool=lambda a: ran.append(a))
    assert said == 'GPU: switching to Overclock. HB posts the result in main chat.' and not ran
    started[0]()
    assert ran == [{'action': 'apply', 'profile': 'jd_tested'}]
    hb_power.switch_gpu('stock', start=lambda f: f(), tool=lambda a: ran.append(a))
    assert ran[-1] == {'action': 'reset'}
    with pytest.raises(ValueError):
        hb_power.switch_gpu('max')


def test_a_refusal_is_posted_in_main_chat():
    posted = []

    def refuse(args):
        raise PermissionError('hb-gpu-profile is not installed')
    hb_power.switch_gpu('jd_tested', start=lambda f: f(), tool=refuse, post=posted.append)
    assert posted == ['🖥 GPU Overclock: NOT applied - hb-gpu-profile is not installed']


def test_mode_is_read_from_the_cards_limits():
    assert hb_power.gpu_mode({'clock_limit_mhz': 2600, 'power_cap_w': 249.0}) == 'jd_tested'
    assert hb_power.gpu_mode({'clock_limit_mhz': 2159, 'power_cap_w': 227.0}) == 'stock'


def _node(expr, snap):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', f"const R=require({json.dumps(str(JS))}); const snap={json.dumps(snap)}; process.stdout.write(JSON.stringify({expr}))"],
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr[-400:]
    return json.loads(out.stdout)


def test_the_strip_names_the_cpu_mode_and_offers_the_gpu_modes():
    snap = {'telemetry': {'gpu': {'clock_limit_mhz': 2159, 'power_cap_w': 227, 'gpu_mode': 'stock'},
                          'cpu': {'governor': 'powersave', 'epp': 'balance_performance'}}}
    line = _node('R.systemLine(snap)', snap)
    assert 'CPU balanced' in line and 'powersave' not in line
    html = _node('R.renderPower(snap)', snap)
    assert '<b class="hbl-doer hbl-doer-on"' in html and 'Auto (stock)</b>' in html
    assert 'data-q="gpu" data-a="jd_tested"' in html and 'data-confirm="1"' in html and '>Overclock</button>' in html
    snap['telemetry']['gpu']['gpu_mode'] = 'jd_tested'
    html = _node('R.renderPower(snap)', snap)
    assert 'Overclock</b>' in html and 'data-a="stock"' in html


def test_the_route_switches_the_gpu_for_the_owner_only():
    src = (ROOT / 'frontend/blueprints/peer_bridge.py').read_text()
    i = src.index("isinstance(body.get('gpu'),list)")
    assert src.index('def hb_queue_status') < i and 'hb_power.switch_gpu' in src[i:i + 600]
