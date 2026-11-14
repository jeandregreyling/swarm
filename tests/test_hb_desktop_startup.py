"""Practice 59 (owner 12 Nov): the desktop app starts the services itself and shows the start-up live."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import hummingbird_startup as s


class Done:
    def __init__(self, stdout='', returncode=0, stderr=''):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def test_practice_59_commands_need_no_password_and_follow_both_units():
    assert s.start_command('swarm-terminal.service', 'system') == ['sudo', '-n', 'systemctl', 'start', 'swarm-terminal.service']
    assert s.start_command('apex-server.service', 'user') == ['systemctl', '--user', 'start', 'apex-server.service']
    j = s.journal_command()
    assert j[:2] == ['journalctl', '--follow'] and j[-4:] == ['--unit', 'swarm-terminal.service', '--user-unit', 'apex-server.service']


def test_practice_59_only_stopped_services_are_started():
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if 'is-active' in cmd:
            return Done('active\n' if 'apex-server.service' in cmd else 'inactive\n')
        return Done(returncode=0)
    assert s.start_all(run=run) == [('swarm-terminal.service', 'HB web app', 'starting'), ('apex-server.service', "APEX's model server", 'already running')]
    assert ['sudo', '-n', 'systemctl', 'start', 'swarm-terminal.service'] in calls and not any(c[:3] == ['systemctl', '--user', 'start'] for c in calls)
    failed = s.start_all(run=lambda cmd, **kw: Done('inactive\n') if 'is-active' in cmd else Done(returncode=1, stderr='a password is required'))
    assert failed[0][2] == 'could not start: a password is required'
    assert s.status_line(run=lambda cmd, **kw: Done('active\n')) == "HB web app: up · APEX's model server: up"


def test_practice_59_desktop_app_uses_it_and_still_parses():
    src = (ROOT / 'scripts/hummingbird_desktop.py').read_text()
    ast.parse(src)
    for piece in ('startup.start_all()', 'startup.journal_command()', 'startup.status_line', 'def journal_line', 'def append_log'):
        assert piece in src, piece
    assert src.count('self.start_services()') == 1
