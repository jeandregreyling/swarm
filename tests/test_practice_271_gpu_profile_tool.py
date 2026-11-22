"""Practice 271: APEX's gpu_profile tool only runs the installed helper with an approved profile name."""
import json
import types

import pytest

from core import hb_agent_tools as at, apex_tools, hb_task_manager


def fake(stdout):
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(stdout=stdout, stderr='')
    return run, calls


def test_list_and_status_call_the_helper_through_sudo():
    run, calls = fake(json.dumps({'ok': True, 'profiles': {'stock': {}}}))
    assert at.gpu_profile_tool({'action': 'list'}, run=run)['ok']
    assert calls[0] == ['sudo', '-n', '/usr/local/sbin/hb-gpu-profile', 'list']


def test_apply_needs_a_plain_profile_name():
    with pytest.raises(ValueError):
        at.gpu_profile_tool({'action': 'apply', 'profile': 'x; rm -rf /'})
    with pytest.raises(ValueError):
        at.gpu_profile_tool({'action': 'overclock', 'profile': 'x'})


def test_not_installed_says_what_jd_runs():
    run, _ = fake('sudo: a password is required')
    with pytest.raises(PermissionError, match='install-gpu-profile.sh'):
        at.gpu_profile_tool({'action': 'status'}, run=run)


def test_apex_has_the_tool():
    assert 'gpu_profile' in apex_tools.TOOL_SCHEMAS and 'gpu_profile' in hb_task_manager.EXECUTION_TOOLS
