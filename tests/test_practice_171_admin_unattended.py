"""Practice 171 (owner 19 Nov 2026): the first ROCm step stopped at dpkg config-file questions and hung after its window closed."""
from core import hb_admin as a


def test_practice_171_apt_never_asks():
    assert a.unattended(['apt-get', 'install', '-y', 'x']) == ['apt-get', '-o', 'Dpkg::Options::=--force-confnew', '-o',
                                                             'Dpkg::Options::=--force-confdef', 'install', '-y', 'x']
    assert a.unattended(['amdgpu-install', '--usecase=rocm', '--no-dkms', '-y'])[0] == 'amdgpu-install'
    src = open('core/hb_admin.py').read()
    assert 'sudo -- env DEBIAN_FRONTEND=noninteractive' in src


def test_practice_171_closed_window_is_reported(tmp_path, monkeypatch):
    said = []
    monkeypatch.setattr(a, 'finish', lambda rid, code, text, connect: said.append((rid, code)) or 'x')
    clock = iter(range(0, 10000, 30))
    monkeypatch.setattr(a.time, 'time', lambda: next(clock))
    a._watch('A-1', tmp_path / 'l.log', tmp_path / 's.status', sleep=lambda s: None, running=lambda rid: False)
    assert said == [('A-1', -1)]
