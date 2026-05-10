"""Tests for core/hive/self_sampler.py — leader's own telemetry loop."""
from __future__ import annotations

import time

import pytest

from core.hive import registry as reg_mod
from core.hive import self_sampler


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    db = tmp_path / 'hive.db'
    monkeypatch.setenv('SWARM_HIVE_DB', str(db))
    # CRITICAL: any previous test (or create_app in prod mode) may have
    # started the self-sampler.  Stop it *before* resetting the singleton
    # so the new test sees a clean slate.
    self_sampler.stop(timeout=2.0)
    reg_mod.reset_singleton()
    yield reg_mod.get_registry()
    self_sampler.stop(timeout=2.0)
    reg_mod.reset_singleton()


def test_self_sampler_writes_to_registry(isolated_registry, monkeypatch):
    monkeypatch.delenv('SWARM_HIVE_DISABLE_SELF_SAMPLER', raising=False)
    t = self_sampler.start(interval=5.0)
    assert t is not None
    assert self_sampler.is_running()
    # Wait up to 5s for the first tick.
    deadline = time.time() + 5.0
    nodes: list = []
    while time.time() < deadline:
        nodes = isolated_registry.list_nodes()
        if nodes:
            break
        time.sleep(0.1)
    assert nodes, 'self-sampler did not produce a node within 5s'
    self_sampler.stop()
    assert not self_sampler.is_running()


def test_self_sampler_disable_via_env(isolated_registry, monkeypatch):
    monkeypatch.setenv('SWARM_HIVE_DISABLE_SELF_SAMPLER', '1')
    self_sampler.stop()
    t = self_sampler.start()
    assert t is None
    assert not self_sampler.is_running()


def test_self_sampler_idempotent(isolated_registry, monkeypatch):
    monkeypatch.delenv('SWARM_HIVE_DISABLE_SELF_SAMPLER', raising=False)
    t1 = self_sampler.start(interval=10.0)
    t2 = self_sampler.start(interval=10.0)
    assert t1 is t2
    self_sampler.stop()
