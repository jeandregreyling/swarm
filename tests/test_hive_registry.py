"""Tests for core.hive.registry — Y.59."""
from __future__ import annotations

import pytest

from core.hive.contract import build_policy, build_telemetry
from core.hive.registry import HiveRegistry


@pytest.fixture
def reg(tmp_path):
    return HiveRegistry(str(tmp_path / 'hive.db'))


def test_enrol_and_get(reg):
    reg.enrol('node-a', 'linux-mint', label='dev box')
    n = reg.get_node('node-a')
    assert n is not None
    assert n['node_id'] == 'node-a'
    assert n['platform'] == 'linux-mint'
    assert n['label'] == 'dev box'


def test_record_telemetry_auto_enrols(reg):
    payload = build_telemetry('node-x', 'darwin',
                              compute={'cpu_peak_temp_c': 55})
    reg.record_telemetry(payload)
    n = reg.get_node('node-x')
    assert n is not None
    assert n['platform'] == 'darwin'
    latest = reg.latest_telemetry('node-x')
    assert latest is not None
    assert latest['compute']['cpu_peak_temp_c'] == 55


def test_list_nodes_filters_by_age(reg):
    payload = build_telemetry('fresh', 'linux')
    reg.record_telemetry(payload)
    nodes = reg.list_nodes()
    assert any(n['node_id'] == 'fresh' for n in nodes)


def test_set_policy_requires_known_node(reg):
    pol = build_policy('ghost', fan_mode='boost')
    with pytest.raises(KeyError):
        reg.set_policy(pol)


def test_set_policy_persists(reg):
    reg.enrol('n1', 'linux')
    pol = build_policy('n1', fan_mode='boost', boost_exit_temp_c=82)
    reg.set_policy(pol)
    stored = reg.latest_policy('n1')
    assert stored is not None
    assert stored['policy']['thermal']['fan_mode'] == 'boost'


def test_remove_node(reg):
    reg.enrol('gone', 'linux')
    assert reg.get_node('gone') is not None
    reg.remove('gone')
    assert reg.get_node('gone') is None


def test_recent_events_returned(reg):
    reg.enrol('n1', 'linux')
    pol = build_policy('n1', fan_mode='auto')
    reg.set_policy(pol)
    events = reg.recent_events(node_id='n1', limit=10)
    kinds = [e['kind'] for e in events]
    assert 'policy-set' in kinds
