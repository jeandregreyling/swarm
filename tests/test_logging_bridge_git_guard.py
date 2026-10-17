import importlib.util
from pathlib import Path


def _load_logging_bridge():
    path = Path('lib/system/logging_bridge.py')
    spec = importlib.util.spec_from_file_location('logging_bridge_git_guard_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_query_batch_commit_is_disabled_by_default(monkeypatch):
    bridge = _load_logging_bridge()
    calls = []
    monkeypatch.delenv('SWARM_ENABLE_AUTO_GIT_COMMIT', raising=False)
    monkeypatch.setattr(bridge.subprocess, 'run', lambda *args, **kwargs: calls.append(args))

    assert bridge.batch_commit('[seven] completed query') is False
    assert calls == []


def test_auto_git_commit_requires_explicit_switch(monkeypatch):
    bridge = _load_logging_bridge()
    monkeypatch.setenv('SWARM_ENABLE_AUTO_GIT_COMMIT', '1')

    assert bridge._auto_git_commit_enabled() is True
