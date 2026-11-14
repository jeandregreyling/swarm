"""Practice 60 (owner 14 Nov): NVMe swap for very large models - HB sizes it and hands JD the one command; it never changes swap itself."""
from pathlib import Path
import core.hb_swap as s
import core.hb_commands as cmds

ROOT = Path(__file__).resolve().parents[1]


class Out:
    def __init__(self, stdout):
        self.stdout = stdout


def test_practice_60_plan_sizes_the_swap_or_says_why_not():
    assert s.plan(20, 62, 55, 290) == {'needed': False, 'swap_gb': 0, 'ok': True, 'why': '20 GB fits in RAM (55 GB available, 8 GB kept free)'}
    p = s.plan(60, 62, 55, 290)
    assert (p['needed'], p['ok'], p['swap_gb']) == (True, True, 15)
    assert s.plan(60, 62, 55, 30)['ok'] is False and 'disk has only 30 GB free' in s.plan(60, 62, 55, 30)['why']
    assert s.plan(120, 62, 55, 290)['ok'] is False


def test_practice_60_command_gives_jd_the_pkexec_line_and_runs_nothing():
    ran = []

    def run(cmd, **kw):
        ran.append(cmd)
        return Out('')
    text = s.command(['plan', '60'], machine=lambda: (62.0, 55.0, 290.0), run=run)
    assert 'pkexec ' in text and 'hb_swapfile.sh create 15' in text and 'hb_swapfile.sh remove' in text
    assert all(c[0] == 'swapon' and '--show=NAME,SIZE,USED' in c for c in ran)          # only read the swap list
    assert s.command(['plan', '20'], machine=lambda: (62.0, 55.0, 290.0), run=run).startswith('No swap needed')
    assert s.command([], run=lambda cmd, **kw: Out('/srv/hb-swapfile 15G 2G\n/dev/sda3 8G 0B\n')) == \
        'HB swap file: on, 15G (2G used); other swap: /dev/sda3. Plan one with /swap plan <model GB>.'


def test_practice_60_script_is_bounded_and_swap_is_a_command():
    script = (ROOT / 'scripts/hb_swapfile.sh').read_text()
    assert 'FILE=/srv/hb-swapfile' in script and '"$GB" -le 64' in script and 'set -euo pipefail' in script and 'fstab' in script
    assert 'swap' in cmds.NAMES and cmds.parse('swap plan 60') == ('swap', ['plan', '60'])
