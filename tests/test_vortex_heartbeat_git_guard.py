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

