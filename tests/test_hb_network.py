"""Practice 58 (owner 14 Nov): HB network manager - connections found live, benchmark saved, mobile data budget, route by job size."""
import json
import sqlite3
import core.hb_network as n
import core.hb_commands as cmds

ADDR = json.dumps([{'ifname': 'lo', 'operstate': 'UNKNOWN', 'addr_info': [{'family': 'inet', 'local': '127.0.0.1'}]},
                   {'ifname': 'enp5s0', 'operstate': 'UP', 'addr_info': [{'family': 'inet', 'local': '10.0.0.8', 'scope': 'global'}]},
                   {'ifname': 'wlo1', 'operstate': 'UP', 'addr_info': [{'family': 'inet', 'local': '10.0.0.12', 'scope': 'global'}]},
                   {'ifname': 'enxfe36', 'operstate': 'UNKNOWN', 'addr_info': [{'family': 'inet', 'local': '10.68.9.172', 'scope': 'global'},
                                                                              {'family': 'inet6', 'local': '2001::1', 'scope': 'global'}]},
                   {'ifname': 'tailscale0', 'operstate': 'UNKNOWN', 'addr_info': [{'family': 'inet', 'local': '100.9.9.9', 'scope': 'global'}]},
                   {'ifname': 'wlan9', 'operstate': 'DOWN', 'addr_info': []}])
ROUTE = json.dumps([{'dst': 'default', 'dev': 'enxfe36', 'metric': 100}, {'dst': 'default', 'dev': 'enp5s0', 'metric': 101}])


def run(cmd, timeout=20):
    if cmd[:3] == ['ip', '-j', 'addr']:
        return ADDR
    if cmd[:3] == ['ip', '-j', 'route']:
        return ROUTE
    if cmd[0] == 'curl':
        return {'enp5s0': '2100000 16800000', 'wlo1': '2600000 20000000'}.get(cmd[cmd.index('--interface') + 1], '0 0')
    return ''


def test_practice_58_inventory_is_found_live():
    inv = n.inventory(sqlite3.connect(':memory:'), run)
    assert [c['name'] for c in inv] == ['enxfe36', 'enp5s0', 'tailscale0', 'wlan9', 'wlo1']
    by = {c['name']: c for c in inv}
    assert by['enxfe36']['kind'] == 'usb tether' and by['enxfe36']['mobile'] and by['enxfe36']['default'] and by['enxfe36']['ipv6']
    assert by['enp5s0']['kind'] == 'wired' and not by['enp5s0']['mobile'] and by['wlan9']['up'] is False and by['tailscale0']['kind'] == 'vpn'


def test_practice_58_benchmark_is_saved_and_counted():
    c = sqlite3.connect(':memory:')
    assert n.benchmark(c, 'enp5s0', run) == 2.1 and n.benchmark(c, 'enxfe36', run) == 0.0
    assert c.execute('SELECT name, mbytes_per_s, ok FROM hb_network_bench ORDER BY id').fetchall() == [('enp5s0', 2.1, 1), ('enxfe36', 0.0, 0)]
    assert c.execute('SELECT name, bytes, what FROM hb_network_usage').fetchall() == [('enp5s0', 16800000, 'benchmark')]


def test_practice_58_budget_counts_only_mobile_links_and_warns():
    c = sqlite3.connect(':memory:')
    inv = n.inventory(c, run)
    assert n.budget(c, inv)['set'] is False
    n.mark(c, 'wlo1', True, 'jd', 'S9FE hotspot')
    inv = n.inventory(c, run)
    n.set_budget(c, 100, 20, 'jd', now=0)
    n.record_usage(c, 'wlo1', 70 * 1024 ** 3, 'model download')
    n.record_usage(c, 'enp5s0', 50 * 1024 ** 3, 'home line')
    b = n.budget(c, inv)
    assert (b['left_gb'], b['used_gb'], b['warn']) == (30.0, 70.0, True)


def test_practice_58_pick_by_job_size_and_budget():
    c = sqlite3.connect(':memory:')
    n.mark(c, 'wlo1', True, 'jd')
    n.benchmark(c, 'enp5s0', run); n.benchmark(c, 'wlo1', run)
    inv = n.inventory(c, run)
    assert n.pick(c, 50 * 1024 ** 2, inv) == {'name': 'enp5s0', 'why': 'small job: the home line'}
    assert 'no budget set' in n.pick(c, 20 * 1024 ** 3, inv)['why'] and n.pick(c, 20 * 1024 ** 3, inv)['name'] == 'enp5s0'
    n.set_budget(c, 100, 20, 'jd', now=0)
    big = n.pick(c, 20 * 1024 ** 3, inv)
    assert big['name'] == 'wlo1' and 'uses mobile data' in big['why']
    assert n.pick(c, 90 * 1024 ** 3, inv)['name'] == 'enp5s0'                 # would go under the floor
    assert all(p['name'] != 'tailscale0' for p in (n.pick(c, 1, inv), big))


def test_practice_58_text_warns_when_mobile_is_the_default_route_and_net_is_a_command():
    c = sqlite3.connect(':memory:')
    out = n.text(c, run)
    assert out.startswith('Connections:') and '⚠ The system\'s first default route is enxfe36, which is mobile data' in out
    assert n.command(c, ['pick', '0.1'], 'jd', run) == 'enp5s0: small job: the home line.'
    assert n.command(c, ['budget', 'x', '1'], 'jd', run).startswith('Use numbers')
    assert 'net' in cmds.NAMES and cmds.parse('net bench wlo1') == ('net', ['bench', 'wlo1'])
