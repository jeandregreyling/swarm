"""Regression tests for the registry `routable` view.

Phase 1 of the rewire plan (22 April 2026) introduced a single routable-view
accessor that chat, relay, queue, and agent-awareness all consult. These tests
lock in the three filters that view must enforce.
"""
import pytest

from utils.db import registry


def _reset_provider():
    """Clear any cached runtime-disabled provider between tests."""
    registry.set_runtime_disabled_provider(None)
    registry.invalidate_cache()


def test_routable_excludes_silent_api_services():
    """Scholar + Seeker (tier='service') must never appear in the routable view.

    They are silent APIs used by local agents for internet / vision access —
    not chat participants.
    """
    _reset_provider()
    names = {a['name'].lower() for a in registry.get_routable_agents()}
    assert 'scholar' not in names, 'scholar (tier=service) leaked into routable view'
    assert 'seeker' not in names, 'seeker (tier=service) leaked into routable view'


def test_routable_excludes_ghost_operator():
    """Ghost (tier='human') is the operator, not an agent to route to."""
    _reset_provider()
    names = {a['name'].lower() for a in registry.get_routable_agents()}
    assert 'ghost' not in names, 'ghost (tier=human) leaked into routable view'


def test_routable_honors_runtime_disable():
    """Adding a name to the runtime-disabled set hides it from the routable view."""
    _reset_provider()
    baseline = {a['name'].lower() for a in registry.get_routable_agents()}
    # Pick the first local agent for the test
    sample = None
    for n in ('gemma', 'llama', 'mistral', 'qwen'):
        if n in baseline:
            sample = n
            break
    if sample is None:
        pytest.skip('no local ollama agent seeded in DB')

    soft_disabled = set()
    registry.set_runtime_disabled_provider(lambda: soft_disabled)
    assert sample in {a['name'].lower() for a in registry.get_routable_agents()}

    soft_disabled.add(sample)
    after = {a['name'].lower() for a in registry.get_routable_agents()}
    assert sample not in after, f'{sample} should be hidden when soft-disabled'

    soft_disabled.discard(sample)
    recovered = {a['name'].lower() for a in registry.get_routable_agents()}
    assert sample in recovered, f'{sample} should reappear after removal from set'

    _reset_provider()


def test_is_agent_routable_convenience():
    _reset_provider()
    # Silent-api tier should never be routable
    assert registry.is_agent_routable('scholar') is False
    assert registry.is_agent_routable('seeker') is False
    assert registry.is_agent_routable('ghost') is False
    # Empty / none should return False
    assert registry.is_agent_routable('') is False
    assert registry.is_agent_routable(None) is False


def test_excluded_tiers_constant_shape():
    """The excluded-tiers constant must remain a frozenset with exactly the two
    tiers that should never be user-facing. Widening this set is a material
    change — if you're touching it, re-audit all call sites.
    """
    assert isinstance(registry.ROUTABLE_EXCLUDED_TIERS, frozenset)
    assert registry.ROUTABLE_EXCLUDED_TIERS == frozenset({'service', 'human'})
