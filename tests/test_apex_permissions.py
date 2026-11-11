import json
from pathlib import Path
import subprocess

import pytest

from core import apex_permissions as permissions
from core.apex_tools import ReadOnlyRepository, run_apex_tools
from core.chat_continuity import APEX_AGENT, apex_system_prompt
from core.tool_approval import ApprovalStore


@pytest.fixture
def granted(tmp_path, monkeypatch):
    root = tmp_path / 'repository'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    (root / 'example.py').write_text('value = 1\n')
    (root / '.gitignore').write_text('ignored.py\n')
    subprocess.run(['git', '-C', str(root), 'add', '.gitignore', 'example.py'], check=True)
    policy = tmp_path / 'permissions.json'
    policy.write_text(json.dumps({'owner': 'ghost', 'workspace': str(root), 'autonomous_writes': True}))
    policy.chmod(0o600)
    monkeypatch.setattr(permissions, 'POLICY_PATH', policy)
    monkeypatch.setattr(permissions, 'ROOT', root)
    return ReadOnlyRepository(root), policy


def execute(repository, path, *, authorize=lambda _: True, store=None):
    return permissions.execute_authorized_write(
        store or ApprovalStore(), repository, 'propose_write_file',
        {'path': path, 'content': 'value = 2\n'}, ('ghost', 'session-one'), 1, authorize)


def test_existing_file_and_new_untracked_file_are_written_and_read_back(granted):
    repository, _ = granted
    for path in ('example.py', 'new.py'):
        result = execute(repository, path)
        assert result['status'] == 'succeeded'
        assert result['authorization'] == 'owner_workspace_grant'
        assert repository.call('read_file', {'path': path, 'raw': True}) == 'value = 2\n'
    search = repository.call('grep_repo', {'path': 'new.py', 'query': 'value'})
    assert 'new.py:1: value = 2' in search


def test_owner_workspace_and_enabled_grant_must_match(granted):
    repository, policy = granted
    assert permissions.autonomous_writes_allowed('ghost')
    assert not permissions.autonomous_writes_allowed('apex')
    assert not permissions.autonomous_writes_allowed('ghost', repository.root.parent)
    for value in (False, 'true', 1):
        policy.write_text(json.dumps({'owner': 'ghost', 'workspace': str(repository.root), 'autonomous_writes': value}))
        assert not permissions.autonomous_writes_allowed('ghost')


def test_policy_is_not_accepted_from_untrusted_or_missing_files(granted):
    repository, policy = granted
    policy.chmod(0o666)
    assert not permissions.autonomous_writes_allowed('ghost')
    policy.chmod(0o600)
    actual = policy.with_suffix('.real')
    policy.rename(actual)
    policy.symlink_to(actual)
    assert not permissions.autonomous_writes_allowed('ghost')
    policy.unlink()
    assert not permissions.autonomous_writes_allowed('ghost')


def test_policy_inside_the_model_writable_repository_is_rejected(granted, monkeypatch):
    repository, policy = granted
    copied = repository.root / 'permissions.json'
    copied.write_bytes(policy.read_bytes())
    copied.chmod(0o600)
    monkeypatch.setattr(permissions, 'POLICY_PATH', copied)
    assert not permissions.autonomous_writes_allowed('ghost')


def test_permission_denial_and_mid_turn_revocation_never_write(granted):
    repository, policy = granted
    store = ApprovalStore()
    with pytest.raises(PermissionError):
        execute(repository, 'example.py', authorize=lambda _: False, store=store)
    calls = []

    def revoke_after_preview(_tool):
        calls.append(True)
        if len(calls) == 2:
            policy.unlink()
        return permissions.autonomous_writes_allowed('ghost')

    result = execute(repository, 'example.py', authorize=revoke_after_preview, store=store)
    assert result['status'] == 'denied'
    assert (repository.root / 'example.py').read_text() == 'value = 1\n'
    assert store.list_for('ghost', 'session-one') == []


@pytest.mark.parametrize('path', ['../outside.py', '.env', 'ignored.py', 'runtime/private.py', 'database.db'])
def test_autonomous_grant_keeps_source_file_boundaries(granted, path):
    repository, _ = granted
    with pytest.raises((PermissionError, ValueError)):
        execute(repository, path)
    assert not (repository.root.parent / 'outside.py').exists()


def test_automatic_write_does_not_grant_git_commit(granted):
    repository, _ = granted
    with pytest.raises(PermissionError):
        permissions.execute_authorized_write(ApprovalStore(), repository, 'propose_commit',
            {'paths': ['example.py'], 'message': 'not authorized'}, ('ghost', 'session-one'), 1, lambda _: True)


def test_prompt_reports_real_autonomous_write_mode():
    prompt = apex_system_prompt(APEX_AGENT, recovery=False, proposals=True, autonomous_writes=True)
    assert 'execute immediately' in prompt
    assert 'There is no direct write or commit tool' not in prompt
    assert 'all file/commit mutations still require HITL' not in prompt
    assert 'Do not ask again for read/write permission' in prompt
    manual = apex_system_prompt(APEX_AGENT, recovery=False, proposals=True)
    assert 'A proposal suspends this turn' in manual
    recovery = apex_system_prompt(APEX_AGENT, recovery=True, proposals=True, autonomous_writes=True)
    assert 'No tools are attached in recovery' in recovery
    assert 'execute immediately' not in recovery


def test_unfounded_refusal_retries_then_writes_with_real_receipts(granted):
    repository, _ = granted
    store = ApprovalStore()
    seen = []
    replies = iter([
        "I don't have permission to write files.",
        json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'example.py'}}], 'answer': ''}),
        json.dumps({'tool_calls': [{'name': 'propose_patch', 'arguments': {
            'file_path': 'example.py', 'exact_old_text': 'value = 1', 'new_text': 'value = 3'}}], 'answer': ''}),
        json.dumps({'tool_calls': [], 'answer': 'Updated example.py to value = 3.'}),
    ])

    def model(_name, messages):
        seen.append([dict(message) for message in messages])
        return next(replies), 1

    def handler(repo, tool, args):
        return permissions.execute_authorized_write(store, repo, tool, args, ('ghost', 'session-one'), 1, lambda _: True)

    answer, _, receipts = run_apex_tools(model, [{'role': 'user', 'content': 'Edit example.py to set value = 3.'}],
        lambda: True, lambda _: None, repository, proposal_handler=handler)
    assert seen[1][-1]['content'].startswith('BACKEND CAPABILITY CHECK')
    assert [receipt['status'] for receipt in receipts] == ['succeeded', 'succeeded']
    assert receipts[-1]['authorization'] == 'owner_workspace_grant'
    assert (repository.root / 'example.py').read_text() == 'value = 3\n'
    assert answer == 'Updated example.py to value = 3.'


def test_real_permission_denial_is_not_hidden_or_retried(granted):
    repository, _ = granted
    replies = iter([
        json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'example.py'}}]}),
        'I cannot read this file because the tool denied access.',
    ])
    answer, _, receipts = run_apex_tools(lambda *_: (next(replies), 1),
        [{'role': 'user', 'content': 'Read example.py'}], lambda: False, lambda _: None, repository)
    assert receipts[0]['status'] == 'denied'
    assert 'denied access' in answer
