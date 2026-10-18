import subprocess
import sys

from fridays.shell_agent import _match_whitelist

CMD = 'python3 scripts/db_query.py "select 1"'


def test_whitelisted_read_only():
    assert _match_whitelist(CMD) == (0, 'read-only db query')


def test_whitelist_rejects_chaining():
    assert _match_whitelist(CMD + ' ; rm -rf x') is None
    assert _match_whitelist('python3 scripts/db_query.py "select $(id)"') is None


def test_script_refuses_writes():
    out = subprocess.run(
        [sys.executable, 'scripts/db_query.py', 'delete from agents'],
        capture_output=True, text=True,
    )
    assert out.returncode == 2 and 'Refused' in out.stdout
