"""Prepare Practice 170: /admin - admin steps through Linux's own sudo prompt in a desktop terminal, JD approves each one."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
H = '/home/jd/swarm/runtime/claude_helpers/p170/'
C = 'core/hb_commands.py'
edits = [
    {'path': C, 'old': "    if cmd == 'apex':   # Practice 152 (owner 18 Nov): the model that plays APEX is swappable (core/hb_apex_swap.py)\n",
     'new': ("    if cmd == 'admin':   # Practice 170 (owner 19 Nov): admin steps through Linux's own sudo prompt (core/hb_admin.py)\n"
             "        return ('admin', words[1:])\n"
             "    if cmd == 'apex':   # Practice 152 (owner 18 Nov): the model that plays APEX is swappable (core/hb_apex_swap.py)\n")},
    {'path': C, 'old': "    if command == 'apex':\n        from core import hb_apex_swap\n",
     'new': ("    if command == 'admin':   # only a command typed in JD's own main chat (the owner route passes `after`) can approve\n"
             "        from core import hb_admin\n        return hb_admin.command(conn, args, actor, owner=after is not None)\n"
             "    if command == 'apex':\n        from core import hb_apex_swap\n")},
    {'path': C, 'old': "    ('apex', '/apex [models | model <name> | back]',",
     'new': ("    ('admin', '/admin [rocm | approve A-xxxx | decline A-xxxx | check rocm]', \"Admin steps: HB proposes, you approve, Linux asks for your password in a terminal window\", False),\n"
             "    ('apex', '/apex [models | model <name> | back]',")},
]

test = r'''"""Practice 170 (owner 19 Nov 2026): /admin - HB proposes allowlisted admin commands; only JD's own main chat approves; the command runs
as `sudo` in a terminal window on his desktop, so Linux asks for the password and HB never sees it."""
import json
import sqlite3

import pytest

from core import hb_admin as a, hb_commands


@pytest.fixture
def conn(monkeypatch):
    c = sqlite3.connect(':memory:')
    said = []
    monkeypatch.setattr(a, '_say', lambda conn, text: said.append(text))
    return c, said


def test_practice_170_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'ADMIN_DIR', tmp_path)
    deb = tmp_path / 'amdgpu-install_7.1_all.deb'
    deb.write_bytes(b'x')
    assert a.validate(['apt-get', 'update'])
    assert 'amdgpu-install_7.1_all.deb' in a.validate(['apt-get', 'install', '-y', str(deb)])
    assert a.validate(['amdgpu-install', '--usecase=rocm,hiplibsdk', '--no-dkms', '-y'])
    for bad in (['rm', '-rf', '/'], ['apt-get', 'install', '-y', '/etc/passwd.deb'], ['apt-get', 'install', '-y', 'x;rm'],
                ['amdgpu-install', '--usecase=rocm', '-y'], ['amdgpu-install', '--usecase=rocm,evil', '--no-dkms', '-y'], ['bash', '-c', 'id']):
        with pytest.raises(ValueError):
            a.validate(bad)


def test_practice_170_only_jd_approves_and_it_runs_in_a_terminal(conn, tmp_path, monkeypatch):
    c, said = conn
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    rid = a.propose(c, ['apt-get', 'update'])
    assert 'sudo apt-get update' in said[0] and f'/admin approve {rid}' in said[0]
    launched = []
    assert 'Only JD' in a.approve(c, rid, 'Claude Code', owner=True, launcher=lambda *x: launched.append(x), watch=False)
    assert 'Only JD' in a.approve(c, rid, 'jd', owner=False, launcher=lambda *x: launched.append(x), watch=False)
    out = a.approve(c, rid, 'jd', owner=True, launcher=lambda *x: launched.append(x), watch=False)
    assert 'terminal window' in out and launched and launched[0][1] == ['apt-get', 'update']
    assert c.execute('SELECT state FROM hb_admin_requests WHERE id=?', (rid,)).fetchone()[0] == 'running'


def test_practice_170_order_and_finish(conn, tmp_path, monkeypatch):
    c, said = conn
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    first = a.propose(c, ['apt-get', 'update'])
    second = a.propose(c, ['amdgpu-install', '--usecase=rocm', '--no-dkms', '-y'], needs=first)
    assert 'runs after' in a.approve(c, second, 'jd', owner=True, launcher=lambda *x: None, watch=False)

    class Keep:
        def __enter__(self): return c
        def __exit__(self, *e): return False
        def close(self): pass
    import contextlib
    monkeypatch.setattr(contextlib, 'closing', lambda x: x)
    assert a.finish(first, 0, 'Reading package lists... Done\n', lambda: Keep()) == 'done'
    assert 'done' in said[-1] and 'Reading package lists' in said[-1]


def test_practice_170_command_is_wired():
    assert hb_commands.parse('admin approve A-1A2B3C') == ('admin', ['approve', 'A-1A2B3C'])
    assert any(cmd[0] == 'admin' for cmd in hb_commands.COMMANDS)
    src = open('core/hb_commands.py').read()
    assert 'owner=after is not None' in src


def test_practice_170_terminal_still_refuses_sudo():
    from core import hb_chat_terminal as t
    assert 'sudo' in t.NEVER and 'pkexec' in t.NEVER
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 19 Nov (\"if it's bound by the linux HB can use it and it's not built into HB so it can't really change it, go ahead\"): "
                            "/admin. HB proposes one allowlisted admin command as a card (apt-get update / install named packages or a .deb HB "
                            "downloaded / amdgpu-install with approved use cases, --no-dkms); only /admin approve typed in JD's own main chat "
                            "(owner route) starts it; it runs as sudo in a gnome-terminal window on JD's desktop, so Linux asks for the password "
                            "and HB never sees it; HB reports the exit code and the end of the output. /admin rocm downloads AMD's installer from "
                            "repo.radeon.com and proposes the two ROCm steps; /admin check rocm runs rocminfo. The $ terminal still refuses sudo."),
                 edits=edits, new_files={'core/hb_admin.py': open(H + 'hb_admin.py').read(),
                                         'tests/test_practice_170_admin_steps.py': test},
                 test={'tests': ['tests/test_practice_170_admin_steps.py', 'tests/test_practice_152_apex_swap.py'],
                       'keyword': ''}, run=run)
print(out['verified'])
