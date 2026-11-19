"""Practice 170 (owner 19 Nov 2026): /admin - HB proposes allowlisted admin commands; only JD's own main chat approves; the command runs
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
