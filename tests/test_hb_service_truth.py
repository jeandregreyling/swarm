"""Practice 44 (owner 15 Nov): the services list agrees with systemd and with live port ownership (Studio S-C0FDABC627)."""
from pathlib import Path
import core.hb_service_truth as t

SS = """LISTEN 0 512 0.0.0.0:8080 0.0.0.0:* users:(("llama-server",pid=2437,fd=6))
LISTEN 0 5 0.0.0.0:5050 0.0.0.0:* users:(("python3",pid=18727,fd=12))
LISTEN 0 128 127.0.0.1:631 0.0.0.0:*
"""
UNITS = {18727: 'swarm-terminal.service', 2437: 'apex-server.service', 99: ''}


def test_practice_44_ss_output_is_parsed():
    assert t.parse_ss(SS) == {8080: {'name': 'llama-server', 'pid': 2437}, 5050: {'name': 'python3', 'pid': 18727}}
    assert t.parse_ss('') == {}


def test_practice_44_verdict_compares_systemd_with_the_port_owner():
    owners = t.parse_ss(SS)
    look = UNITS.get
    assert t.verdict('swarm-terminal.service', True, 5050, owners, look)['truth'] == 'ok'
    assert t.verdict('swarm-monitor.service', True, None, owners, look) == {'truth': 'no port', 'port_owner': None}
    assert t.verdict('swarm-terminal-dev.service', True, 5051, owners, look)['truth'] == 'systemd says active, but nothing listens on port 5051'
    assert t.verdict('swarm-terminal-dev.service', False, 5051, owners, look)['truth'] == 'ok'
    wrong = t.verdict('swarm-terminal-uat.service', False, 5050, owners, look)
    assert wrong['truth'] == 'port 5050 is held by python3 (pid 18727, swarm-terminal.service), not by this service'
    assert wrong['port_owner']['unit'] == 'swarm-terminal.service'
    assert 'still holds port 5050' in t.verdict('swarm-terminal.service', False, 5050, owners, look)['truth']
    stray = t.verdict('swarm-terminal.service', True, 5050, {5050: {'name': 'nc', 'pid': 99}}, look)['truth']
    assert stray == 'port 5050 is held by nc (pid 99), not by this service'


def test_practice_44_services_api_carries_the_truth():
    src = (Path(__file__).resolve().parents[1] / 'frontend/blueprints/exec_bp.py').read_text()
    assert "'apex-server.service'" in src and "'port': 8080" in src
    assert 'hb_service_truth' in src and "'truth': truth['truth']" in src and "'port_owner': truth['port_owner']" in src
