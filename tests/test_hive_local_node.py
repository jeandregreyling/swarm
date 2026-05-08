"""Tests for core.hive.local_node + providers.generic — Y.59."""
from __future__ import annotations

from core.hive.contract import validate_telemetry
from core.hive.local_node import LocalNode, build_local_telemetry
from core.hive.providers import GenericProvider, detect_provider


def test_generic_provider_sample_validates():
    g = GenericProvider()
    bundle = g.sample()
    assert set(bundle) == {'compute', 'thermal', 'memory', 'power'}
    assert bundle['thermal']['controllable'] is False


def test_local_node_with_generic_provider():
    node = LocalNode(provider=GenericProvider(), node_id='unit-test-host')
    payload = node.sample()
    validate_telemetry(payload)
    assert payload['node_id'] == 'unit-test-host'
    assert payload['contract'] == 'node.resource/v0'


def test_build_local_telemetry_real_host():
    """End-to-end: whatever provider auto-detects on this CI host must
    still produce a contract-valid payload."""
    payload = build_local_telemetry()
    validate_telemetry(payload)
    assert isinstance(payload['capabilities'], list)


def test_capabilities_merge():
    payload = build_local_telemetry(capabilities=['inference.lmstudio'])
    assert 'inference.lmstudio' in payload['capabilities']


def test_detect_provider_returns_something():
    p = detect_provider()
    assert hasattr(p, 'sample')
    assert hasattr(p, 'platform_name')
