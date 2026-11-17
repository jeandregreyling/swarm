"""Practice 132 (owner 17 Nov 2026): "the network status call and select and control". Status names the network each connection is on,
JD picks the connection for downloads, connects a saved Wi-Fi in range or disconnects a side connection - never the main route or VPN."""
import shutil
import sqlite3
import subprocess
from pathlib import Path

import core.hb_network as n
from test_hb_network import ADDR

ROUTE = '[{"dst": "default", "dev": "enp5s0", "metric": 100}, {"dst": "default", "dev": "wlo1", "metric": 600}]'
ACTIVE = 'Wired connection 1:enp5s0\nAuto ORBI16:wlo1\ntailscale0:tailscale0\nlo:lo'
SAVED = 'Wired connection 1:802-3-ethernet\nAuto ORBI16:802-11-wireless\nAuto S9FE:802-11-wireless\nHotspot:802-11-wireless\nAuto Far:802-11-wireless'
SEEN = 'yes:ORBI16:100\nno:ORBI16:90\nno:S9FE:71\nno:Neighbour:60'


def run(cmd, timeout=20):
    if cmd[:3] == ['ip', '-j', 'addr']:
        return ADDR
    if cmd[:3] == ['ip', '-j', 'route']:
        return ROUTE
    if cmd[:2] == ['nmcli', '-t']:
        return {'--active': ACTIVE, 'show': SAVED, 'list': SEEN}.get(cmd[-1] if cmd[-1] != 'no' else 'list', '')
    return ''


def test_practice_132_status_names_the_network():
    inv = {c['name']: c for c in n.inventory(sqlite3.connect(':memory:'), run)}
    assert inv['wlo1']['network'] == 'ORBI16' and inv['wlo1']['label'] == 'ORBI16 Wi-Fi' and not inv['wlo1']['mobile']
    assert [n.kind(x) for x in ('proton0', 'ipv6leakintrf0', 'wg0', 'tun0')] == ['vpn'] * 4
    s = n.status(sqlite3.connect(':memory:'), run, wifi=True)
    assert s['main'] == 'enp5s0' and [w['network'] for w in s['wifi']] == ['ORBI16', 'S9FE', 'Far']    # never the machine's own Hotspot
    assert s['wifi'][1] == {'name': 'Auto S9FE', 'network': 'S9FE', 'in_range': True, 'signal': 71, 'active': False}


def test_practice_132_select_wins_but_mobile_keeps_its_floor():
    c = sqlite3.connect(':memory:')
    assert 'HB uses wlo1' in n.command(c, ['use', 'wlo1'], 'jd', run)
    assert n.pick(c, 10 * 1024 ** 3, n.inventory(c, run))['name'] == 'wlo1'
    n.mark(c, 'wlo1', True, 'jd'); n.set_budget(c, 5, 2, 'jd')
    assert n.pick(c, 10 * 1024 ** 3, n.inventory(c, run))['name'] == 'enp5s0'       # 10 GB would go under the 2 GB floor
    n.command(c, ['use', 'auto'], 'jd', run)
    assert n.choice(c) is None


def test_practice_132_control_is_bounded():
    c, done = sqlite3.connect(':memory:'), []
    act = lambda cmd: (done.append(cmd), (True, ''))[1]
    assert n.connect(c, 'S9FE', 'jd', run, act).startswith('Connected to S9FE') and done[-1] == ['nmcli', 'connection', 'up', 'id', 'Auto S9FE']
    assert 'not in range' in n.connect(c, 'Far', 'jd', run, act) and 'Already connected' in n.connect(c, 'ORBI16', 'jd', run, act)
    assert 'not a saved Wi-Fi' in n.connect(c, 'Hotspot', 'jd', run, act)
    assert 'main route' in n.disconnect(c, 'enp5s0', 'jd', run, act) and 'VPN' in n.disconnect(c, 'tailscale0', 'jd', run, act)
    assert n.disconnect(c, 'wlo1', 'jd', run, act) == 'Disconnected wlo1.' and done[-1] == ['nmcli', 'device', 'disconnect', 'wlo1']
    assert len(done) == 2


def test_practice_132_downloads_name_the_wifi_network(monkeypatch):
    from core import hb_downloads
    monkeypatch.setattr(n, 'networks', lambda run=None: {'wlo1': 'ORBI16'})
    assert hb_downloads.connection('wlo1') == 'ORBI16 Wi-Fi'
    monkeypatch.setattr(n, 'networks', lambda run=None: {'wlo1': 'S9FE'})
    assert hb_downloads.connection('wlo1') == 'S9FE Wi-Fi (Samsung hotspot, mobile data)'


def test_practice_132_network_bar_is_loaded_and_themed():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'frontend/static/js/hb-network.js').read_text()
    assert 'hb-network.js' in (root / 'frontend/templates/terminal_base.html').read_text()
    assert '/api/network/action' in js and 'window.confirm' in js and 'var(--accent)' in js
    import re
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', js)
    if shutil.which('node'):
        assert subprocess.run(['node', '--check', str(root / 'frontend/static/js/hb-network.js')], capture_output=True).returncode == 0
