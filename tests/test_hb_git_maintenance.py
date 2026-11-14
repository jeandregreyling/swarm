"""Owner 13 Nov (practices 19-21, APEX): APEX may clear git's stale index lock, a harness fix. Only .git/index.lock, only when it is
empty, older than ten minutes and no git process runs."""
import os
import time

import pytest


def _lock(tmp_path, content=b'', age=3600):
    (tmp_path / '.git').mkdir()
    lock = tmp_path / '.git' / 'index.lock'
    lock.write_bytes(content)
    old = time.time() - age
    os.utime(lock, (old, old))
    return lock


def test_practice_19_stale_lock_is_removed(tmp_path):
    from core.hb_git_maintenance import clear_stale_lock
    lock = _lock(tmp_path)
    result = clear_stale_lock(tmp_path, running=lambda: False)
    assert result['removed'] is True and not lock.exists() and result['age_minutes'] >= 59


@pytest.mark.parametrize('content,age,running,reason', [
    (b'x', 3600, False, 'not empty'),
    (b'', 60, False, 'younger than 10 minutes'),
    (b'', 3600, True, 'git process is running'),
])
def test_practice_19_a_lock_that_may_be_live_is_kept(tmp_path, content, age, running, reason):
    from core.hb_git_maintenance import clear_stale_lock
    lock = _lock(tmp_path, content, age)
    result = clear_stale_lock(tmp_path, running=lambda: running)
    assert result['removed'] is False and reason in result['reason'] and lock.exists()


def test_practice_19_no_lock_is_fine(tmp_path):
    from core.hb_git_maintenance import clear_stale_lock
    assert clear_stale_lock(tmp_path, running=lambda: False) == {'removed': False, 'reason': 'no lock file'}


def test_practice_20_apex_is_granted_and_routed_the_tool():
    from pathlib import Path
    from core.hb_agent_tools import WRITE_TOOLS
    assert 'git_clear_stale_lock' in WRITE_TOOLS     # offered only on the task that needs it (a tool_scope), not every turn
    source = (Path(__file__).resolve().parents[1] / 'core' / 'hb_agent_tools.py').read_text()
    assert "if tool=='git_clear_stale_lock':" in source and 'return clear_stale_lock()' in source


def test_practice_21_the_tool_has_a_schema():
    from core.apex_tools import TOOL_SCHEMAS, _REQUIRED_ARGUMENTS
    assert TOOL_SCHEMAS['git_clear_stale_lock'] == {} and _REQUIRED_ARGUMENTS['git_clear_stale_lock'] == []
