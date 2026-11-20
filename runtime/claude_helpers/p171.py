"""Prepare Practice 171: admin steps never stop at a question, and a window closed early is noticed."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
A = 'core/hb_admin.py'
edits = [
    {'path': A, 'old': '''    script = ('echo "HB admin step $HB_ADMIN_ID: sudo $*"; echo; sudo -- "$@" 2>&1 | tee "$HB_ADMIN_LOG"; s=${PIPESTATUS[0]}; \'''',
     'new': '''    # Practice 171 (owner 19 Nov 2026): the first ROCm step stopped at dpkg's "amdgpu.list / rocm.list (Y/I/N/O/D/Z)?" questions, and when
    # the window was closed the install hung on a terminal nobody could reach. Admin steps now never ask (noninteractive, new config files).
    script = ('echo "HB admin step $HB_ADMIN_ID: sudo $*"; echo; sudo -- env DEBIAN_FRONTEND=noninteractive "$@" 2>&1 | tee "$HB_ADMIN_LOG"; s=${PIPESTATUS[0]}; \''''},
    {'path': A, 'old': '''    (launcher or _launch)(rid, argv, log, status)
''', 'new': '''    (launcher or _launch)(rid, unattended(argv), log, status)
'''},
    {'path': A, 'old': '''def _watch(rid, log, status, limit=4 * 3600, sleep=time.sleep):
    from contextlib import closing
    from utils.db._connection import get_connection
    start = time.time()
    while not status.exists() and time.time() - start < limit:
        sleep(5)
    code = int(status.read_text().strip() or 1) if status.exists() else None
''', 'new': '''def unattended(argv):
    """Practice 171: apt-get takes the package's new config files instead of asking (the 19 Nov amdgpu.list / rocm.list prompts)."""
    a = list(argv)
    if a[:1] == ['apt-get']:
        return ['apt-get', '-o', 'Dpkg::Options::=--force-confnew', '-o', 'Dpkg::Options::=--force-confdef'] + a[1:]
    return a


def _running(rid):
    """Is the admin step's sudo still running (its window may have been closed)?"""
    try:
        out = subprocess.run(['pgrep', '-f', 'sudo -- env DEBIAN_FRONTEND=noninteractive'], capture_output=True, text=True, timeout=10)
        return bool(out.stdout.strip())
    except Exception:
        return True


def _watch(rid, log, status, limit=4 * 3600, sleep=time.sleep, running=None):
    from contextlib import closing
    from utils.db._connection import get_connection
    running = running or _running
    start = time.time()
    gone = 0
    while not status.exists() and time.time() - start < limit:
        sleep(5)
        # Practice 171: the window was closed before the step finished - say so instead of waiting for hours
        gone = gone + 1 if time.time() - start > 60 and not running(rid) else 0
        if gone >= 3:
            break
    if not status.exists() and gone >= 3:
        return finish(rid, -1, log.read_text(errors='replace') if log.exists() else '', get_connection)
    code = int(status.read_text().strip() or 1) if status.exists() else None
'''},
    {'path': A, 'old': '''    state = 'done' if code == 0 else ('timed out' if code is None else 'failed')
''', 'new': '''    state = 'done' if code == 0 else ('timed out' if code is None else 'window closed before it finished' if code == -1 else 'failed')
'''},
    {'path': 'tests/test_practice_170_admin_steps.py',
     'old': "    assert 'terminal window' in out and launched and launched[0][1] == ['apt-get', 'update']\n",
     'new': "    assert 'terminal window' in out and launched and launched[0][1][0] == 'apt-get' and launched[0][1][-1] == 'update'   # + Practice 171 options\n"},
]

test = r'''"""Practice 171 (owner 19 Nov 2026): the first ROCm step stopped at dpkg config-file questions and hung after its window closed."""
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
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 19 Nov: the first ROCm admin step (A-26EEBA) stopped at dpkg's amdgpu.list / rocm.list config-file questions, and "
                            "after its window closed the install hung on a terminal nobody could reach (JD finished it with dpkg --configure -a "
                            "--force-confnew). core/hb_admin: steps run as sudo -- env DEBIAN_FRONTEND=noninteractive; apt-get gets --force-confnew "
                            "--force-confdef; the watcher reports 'window closed before it finished' instead of waiting for hours."),
                 edits=edits, new_files={'tests/test_practice_171_admin_unattended.py': test},
                 test={'tests': ['tests/test_practice_171_admin_unattended.py', 'tests/test_practice_170_admin_steps.py'], 'keyword': ''}, run=run)
print(out['verified'])
