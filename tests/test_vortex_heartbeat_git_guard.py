from __future__ import annotations


def test_vortex_heartbeat_checkpoint_does_not_write_git(monkeypatch, tmp_path):
    from core import time_machine

    root = tmp_path / 'repo'
    root.mkdir()
    (root / '.git').mkdir()
    monkeypatch.setattr(time_machine, '_SWARM_PROD_ROOT', str(root))
    monkeypatch.setattr(time_machine, '_SWARM_UAT_ROOT', str(tmp_path / 'missing-uat'))
    monkeypatch.setattr(time_machine, '_SWARM_DEV_ROOT', str(tmp_path / 'missing-dev'))
    monkeypatch.delenv('SWARM_VORTEX_GIT_HEARTBEAT', raising=False)

    git_calls = []
    monkeypatch.setattr(time_machine, '_git_cmd', lambda *a, **k: git_calls.append((a, k)) or ('', 0))

    tm = time_machine.TimeMachine.__new__(time_machine.TimeMachine)
    monkeypatch.setattr(tm, 'capture_workflow_state', lambda: {'captured_at': 'now', 'counts': {}})
    monkeypatch.setattr(tm, 'create_checkpoint', lambda *a, **k: 123)
    monkeypatch.setattr(tm, 'record_event', lambda *a, **k: None)
    monkeypatch.setattr(tm, '_write_activity_log', lambda *a, **k: None)

    result = tm.create_workflow_checkpoint('heartbeat-prod', agent='vortex')

    assert result['checkpoint_id'] == 123
    assert result['git_tags'] == {}
    assert git_calls == []


def test_vortex_non_heartbeat_checkpoint_still_writes_git(monkeypatch, tmp_path):
    from core import time_machine

    root = tmp_path / 'repo'
    root.mkdir()
    (root / '.git').mkdir()
    monkeypatch.setattr(time_machine, '_SWARM_PROD_ROOT', str(root))
    monkeypatch.setattr(time_machine, '_SWARM_UAT_ROOT', str(tmp_path / 'missing-uat'))
    monkeypatch.setattr(time_machine, '_SWARM_DEV_ROOT', str(tmp_path / 'missing-dev'))

    git_calls = []

    def _fake_git(args, cwd=None):
        git_calls.append((args, cwd))
        return '', 0

    monkeypatch.setattr(time_machine, '_git_cmd', _fake_git)

    tm = time_machine.TimeMachine.__new__(time_machine.TimeMachine)
    monkeypatch.setattr(tm, 'capture_workflow_state', lambda: {'captured_at': 'now', 'counts': {}})
    monkeypatch.setattr(tm, 'create_checkpoint', lambda *a, **k: 123)
    monkeypatch.setattr(tm, 'record_event', lambda *a, **k: None)
    monkeypatch.setattr(tm, '_write_activity_log', lambda *a, **k: None)

    result = tm.create_workflow_checkpoint('before-real-change', agent='vortex')

    assert result['git_tags']['prod'].endswith('-prod')
    assert [call[0][0] for call in git_calls] == ['add', 'commit', 'tag']


def test_vortex_git_sync_skips_below_threshold(monkeypatch, tmp_path):
    from core import time_machine

    root = tmp_path / 'repo'
    root.mkdir()
    (root / '.git').mkdir()

    git_calls = []

    def _fake_git(args, cwd=None):
        git_calls.append(args)
        if args[:2] == ['status', '--porcelain']:
            return ' M a.py\n?? b.py', 0
        return '', 0

    monkeypatch.setattr(time_machine, '_git_cmd', _fake_git)

    result = time_machine._vortex_maybe_git_sync(cwd=str(root), threshold=10)

    assert result['status'] == 'skipped'
    assert result['reason'] == 'below-threshold'
    assert result['change_count'] == 2
    assert ['add', '-A'] not in git_calls
    assert ['push'] not in git_calls


def test_vortex_git_sync_commits_and_pushes_at_threshold(monkeypatch, tmp_path):
    from core import time_machine

    root = tmp_path / 'repo'
    root.mkdir()
    (root / '.git').mkdir()

    git_calls = []
    status = '\n'.join(f' M file_{i}.py' for i in range(10))

    def _fake_git(args, cwd=None):
        git_calls.append(args)
        if args[:2] == ['status', '--porcelain']:
            return status, 0
        if args == ['commit', '-m', git_calls[-1][-1]]:
            return '', 0
        if args == ['rev-parse', 'HEAD']:
            return 'abcdef1234567890', 0
        if args == ['rev-parse', '--abbrev-ref', 'HEAD']:
            return 'master', 0
        if args == ['push']:
            return '', 0
        return '', 0

    monkeypatch.setattr(time_machine, '_git_cmd', _fake_git)
    monkeypatch.setattr(time_machine, '_run_secret_scan_include_untracked', lambda cwd=None: ('ok', 0))

    result = time_machine._vortex_maybe_git_sync(cwd=str(root), threshold=10, reason='unit-test')

    assert result['status'] == 'synced'
    assert result['change_count'] == 10
    assert result['commit'] == 'abcdef123456'
    assert ['add', '-A'] in git_calls
    assert ['push'] in git_calls
