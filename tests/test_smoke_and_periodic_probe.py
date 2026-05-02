"""Batch U regression tests — smoke entries + targeted pytest entry +
periodic chat_smoke_probe scheduler installer.

Covers:
  MD-SESSION30-4E189EBAC913   — Smoke: 7 endpoints + new run lifecycle
  MD-SESSION30-0DF692E75371   — Targeted test execution (knowledge + spine + testlab)
  MD-FEATURE-CE649CA367EC     — Periodic chat+AI smoke probe (registry + scheduler)
  MD-SESSION30-D931A65A7F6D   — Periodic chat+AI smoke probe (scheduler installer)
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.knowledge import scripts as kc_scripts


def _by_id(rows, sid):
    for r in rows:
        if r.get('id') == sid:
            return r
    return None


# ── Smoke registry coverage ──────────────────────────────────────────────


class TestSmokeRegistry:
    def test_smoke_endpoints_now_covers_seven(self):
        entry = _by_id(kc_scripts.get_registry(), 'smoke-endpoints')
        assert entry is not None
        cmd = entry['command']
        # Expected endpoint paths.
        for ep in (
            '/api/health', '/api/pulse', '/api/chat/jobs/status',
            '/api/auth/me', '/api/chat/agents/health',
            '/api/knowledge/runs/feed', '/api/knowledge/testlab/scripts',
        ):
            assert ep in cmd, f'smoke-endpoints missing {ep}'

    def test_smoke_endpoints_label_says_seven(self):
        entry = _by_id(kc_scripts.get_registry(), 'smoke-endpoints')
        assert '7' in entry['label']

    def test_change_run_lifecycle_entry_exists(self):
        entry = _by_id(kc_scripts.get_registry(), 'smoke-change-run-lifecycle')
        assert entry is not None
        cmd = entry['command']
        # Validates POST start, PATCH finish, GET timeline are all wired.
        assert '/api/knowledge/test-runs' in cmd
        assert 'PATCH' in cmd
        assert '/timeline' in cmd

    def test_change_run_lifecycle_is_smoke_group(self):
        entry = _by_id(kc_scripts.get_registry(), 'smoke-change-run-lifecycle')
        assert entry['group'] == 'Smoke'


# ── Targeted pytest entry ────────────────────────────────────────────────


class TestTargetedPytest:
    def test_entry_present(self):
        entry = _by_id(
            kc_scripts.get_registry(),
            'pytest-targeted-knowledge-spine-testlab',
        )
        assert entry is not None

    def test_targeted_command_runs_only_relevant_files(self):
        entry = _by_id(
            kc_scripts.get_registry(),
            'pytest-targeted-knowledge-spine-testlab',
        )
        cmd = entry['command']
        for f in (
            'tests/test_knowledge.py',
            'tests/test_knowledge_batch_t.py',
            'tests/test_testlab.py',
            'tests/test_spine.py',
            'tests/test_chat_smoke_probe_spine.py',
        ):
            assert f in cmd, f'targeted run missing {f}'
        # Guard against accidentally pulling in the slow chat_quality slice.
        assert 'test_chat_quality' not in cmd or 'not chat_quality' in cmd

    def test_targeted_in_pytest_group(self):
        entry = _by_id(
            kc_scripts.get_registry(),
            'pytest-targeted-knowledge-spine-testlab',
        )
        assert entry['group'] == 'Pytest'


# ── Periodic chat_smoke_probe scheduler hook ─────────────────────────────


class _FakeScheduler:
    """Captures add_task() calls for assertions."""
    def __init__(self):
        self.added = []
        self.existing = []  # rows returned by list_tasks()

    def list_tasks(self):
        return list(self.existing)

    def add_task(self, name, schedule, action_type, action_data, created_by='system'):
        self.added.append({
            'name': name, 'schedule': schedule,
            'action_type': action_type, 'action_data': action_data,
            'created_by': created_by,
        })
        return len(self.added)


@pytest.fixture
def fake_sched(monkeypatch):
    fake = _FakeScheduler()
    import fridays.scheduler as sched_mod
    monkeypatch.setattr(sched_mod, 'list_tasks', fake.list_tasks)
    monkeypatch.setattr(sched_mod, 'add_task', fake.add_task)
    yield fake


class TestPeriodicSmokeProbeInstaller:
    def test_installs_when_absent(self, fake_sched, monkeypatch):
        monkeypatch.delenv('FRIDAYS_CHAT_SMOKE_PROBE_INTERVAL', raising=False)
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        names = [t['name'] for t in fake_sched.added]
        assert 'chat_smoke_probe' in names

    def test_python_action_type(self, fake_sched, monkeypatch):
        monkeypatch.delenv('FRIDAYS_CHAT_SMOKE_PROBE_INTERVAL', raising=False)
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        smoke = next(t for t in fake_sched.added if t['name'] == 'chat_smoke_probe')
        assert smoke['action_type'] == 'PYTHON'
        assert smoke['action_data'] == 'chat_smoke_probe'

    def test_default_interval_is_30_min(self, fake_sched, monkeypatch):
        monkeypatch.delenv('FRIDAYS_CHAT_SMOKE_PROBE_INTERVAL', raising=False)
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        smoke = next(t for t in fake_sched.added if t['name'] == 'chat_smoke_probe')
        assert smoke['schedule'] == 'interval 30m'

    def test_env_override_interval(self, fake_sched, monkeypatch):
        monkeypatch.setenv('FRIDAYS_CHAT_SMOKE_PROBE_INTERVAL', '15')
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        smoke = next(t for t in fake_sched.added if t['name'] == 'chat_smoke_probe')
        assert smoke['schedule'] == 'interval 15m'

    def test_minimum_interval_clamped(self, fake_sched, monkeypatch):
        monkeypatch.setenv('FRIDAYS_CHAT_SMOKE_PROBE_INTERVAL', '1')
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        smoke = next(t for t in fake_sched.added if t['name'] == 'chat_smoke_probe')
        # Min clamp = 5 minutes.
        assert smoke['schedule'] == 'interval 5m'

    def test_garbage_env_falls_back_to_default(self, fake_sched, monkeypatch):
        monkeypatch.setenv('FRIDAYS_CHAT_SMOKE_PROBE_INTERVAL', 'not-a-number')
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        smoke = next(t for t in fake_sched.added if t['name'] == 'chat_smoke_probe')
        assert smoke['schedule'] == 'interval 30m'

    def test_idempotent_when_already_present(self, fake_sched, monkeypatch):
        fake_sched.existing = [{'name': 'chat_smoke_probe', 'schedule': 'interval 30m'}]
        from core.pipeline import listener
        listener._ensure_digest_scheduled()
        names = [t['name'] for t in fake_sched.added]
        # Second registration should NOT add a duplicate.
        assert 'chat_smoke_probe' not in names
