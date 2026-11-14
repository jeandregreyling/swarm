"""Start-up helper for the Hummingbird desktop app (owner 12 Nov 2026): which services the app starts, how, and how to watch them.
Plain functions without GTK, so they can be tested; scripts/hummingbird_desktop.py shows the result."""
import subprocess

# (unit, scope, what it is in plain words)
UNITS = (('swarm-terminal.service', 'system', 'HB web app'),
         ('apex-server.service', 'user', "APEX's model server"))


def start_command(unit, scope):
    """The command that starts a unit without asking for a password (sudoers allows it for the system unit)."""
    return ['systemctl', '--user', 'start', unit] if scope == 'user' else ['sudo', '-n', 'systemctl', 'start', unit]


def journal_command(units=UNITS, lines=15):
    """One journalctl that follows every unit the app starts, live."""
    cmd = ['journalctl', '--follow', '--lines', str(lines), '--output', 'short', '--no-hostname']
    for unit, scope, _ in units:
        cmd += ['--user-unit' if scope == 'user' else '--unit', unit]
    return cmd


def is_active(unit, scope, run=subprocess.run):
    cmd = ['systemctl'] + (['--user'] if scope == 'user' else []) + ['is-active', unit]
    try:
        return run(cmd, capture_output=True, text=True, timeout=4).stdout.strip() == 'active'
    except Exception:
        return False


def start_all(units=UNITS, run=subprocess.run):
    """Start every unit that is not active. Returns [(unit, words, 'already running' | 'starting' | 'could not start: ...')]."""
    out = []
    for unit, scope, words in units:
        if is_active(unit, scope, run):
            out.append((unit, words, 'already running'))
            continue
        try:
            done = run(start_command(unit, scope), capture_output=True, text=True, timeout=20)
            out.append((unit, words, 'starting' if done.returncode == 0 else 'could not start: ' + (done.stderr or done.stdout).strip()[:160]))
        except Exception as exc:
            out.append((unit, words, f'could not start: {exc}'))
    return out


def status_line(units=UNITS, run=subprocess.run):
    """'HB web app: up · APEX's model server: starting' - one line for the start-up screen."""
    return ' · '.join(f"{words}: {'up' if is_active(unit, scope, run) else 'starting'}" for unit, scope, words in units)
