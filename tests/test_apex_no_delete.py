import pytest
from core import agent_identity, hb_agent_tools


@pytest.mark.parametrize('principal', ['apex', 'gemini-advisor'])
@pytest.mark.parametrize(('tool', 'args'), [
    ('does_rename', {'action': 'remove_alias', 'path': 'core/example.py'}),
    ('does_rename', {'action': 'move', 'path': 'core/example.py'}),
    ('layout', {'action': 'move', 'path': 'a', 'to': 'b'}),
    ('layout', {'action': 'undo'}),
    ('git_clear_stale_lock', {}),
])
def test_agents_cannot_use_unapproved_file_deletion_or_move_tools(tool, args, principal):
    token = agent_identity.CURRENT.set({'principal': principal, 'task_id': 'T-EXAMPLE'})
    try:
        with pytest.raises(PermissionError, match='requires approval'):
            hb_agent_tools.call(tool, args)
    finally:
        agent_identity.CURRENT.reset(token)
