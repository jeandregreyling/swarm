"""Tests for core.hive.contract — Y.59."""
from __future__ import annotations

import pytest

from core.hive.contract import (
    CONTRACT_VERSION,
    POLICY_CONTRACT,
    TELEMETRY_CONTRACT,
    THERMAL_PRESSURE_LEVELS,
    ContractError,
    build_policy,
    build_telemetry,
    derive_thermal_pressure,
    diff_telemetry,
    validate_policy,
    validate_telemetry,
)


def test_contract_constants():
    assert CONTRACT_VERSION == 'v0'
    assert TELEMETRY_CONTRACT == 'node.resource/v0'
    assert POLICY_CONTRACT == 'node.policy/v0'
    assert 'nominal' in THERMAL_PRESSURE_LEVELS
    assert 'critical' in THERMAL_PRESSURE_LEVELS


def test_build_telemetry_minimum():
    payload = build_telemetry('node-x', 'linux-mint')
    validate_telemetry(payload)
    assert payload['contract'] == TELEMETRY_CONTRACT
    assert payload['node_id'] == 'node-x'
    assert payload['platform'] == 'linux-mint'
    # null-default subtrees populated:
    assert payload['compute']['cpu_load_pct'] is None
    assert payload['thermal']['controllable'] is False
    assert payload['power']['thermal_pressure'] == 'nominal'
    assert payload['capabilities'] == []


def test_build_telemetry_with_data():
    p = build_telemetry(
        'node-x', 'linux-mint',
        compute={'cpu_load_pct': 42, 'cpu_peak_temp_c': 78.5,
                 'cpu_throttled': False, 'gpu_present': True},
        thermal={'fan_rpm': 1500, 'fan_pwm': 128, 'fan_mode': 'boost',
                 'controllable': True},
        memory={'ram_total_mb': 32000, 'ram_free_mb': 12000},
        power={'on_battery': False, 'thermal_pressure': 'fair'},
        capabilities=['inference.cpu', 'inference.ollama'],
    )
    validate_telemetry(p)
    assert p['compute']['cpu_load_pct'] == 42
    assert p['thermal']['fan_mode'] == 'boost'
    assert p['power']['thermal_pressure'] == 'fair'
    assert p['capabilities'] == ['inference.cpu', 'inference.ollama']


def test_build_telemetry_rejects_empty_node_id():
    with pytest.raises(ContractError):
        build_telemetry('', 'linux')
    with pytest.raises(ContractError):
        build_telemetry('node', '')


def test_validate_telemetry_rejects_bad_pressure():
    p = build_telemetry('n', 'linux')
    p['power']['thermal_pressure'] = 'meltdown'
    with pytest.raises(ContractError):
        validate_telemetry(p)


def test_validate_telemetry_rejects_bad_load_pct():
    p = build_telemetry('n', 'linux')
    p['compute']['cpu_load_pct'] = 150
    with pytest.raises(ContractError):
        validate_telemetry(p)


def test_validate_telemetry_rejects_bad_fan_mode():
    p = build_telemetry('n', 'linux')
    p['thermal']['fan_mode'] = 'turbojet'
    with pytest.raises(ContractError):
        validate_telemetry(p)


def test_validate_telemetry_requires_dict():
    with pytest.raises(ContractError):
        validate_telemetry('not a dict')  # type: ignore[arg-type]


def test_build_policy_roundtrip():
    pol = build_policy('node-x', fan_mode='boost', boost_exit_temp_c=85,
                       max_load_pct=70, accept_jobs=True)
    validate_policy(pol)
    assert pol['policy']['thermal']['fan_mode'] == 'boost'
    assert pol['policy']['thermal']['boost_exit_temp_c'] == 85.0
    assert pol['policy']['compute']['max_load_pct'] == 70
    assert pol['policy']['compute']['accept_jobs'] is True


def test_build_policy_rejects_bad_fan_mode():
    with pytest.raises(ContractError):
        build_policy('n', fan_mode='hyperdrive')


def test_build_policy_rejects_bad_boost_temp():
    with pytest.raises(ContractError):
        build_policy('n', boost_exit_temp_c=999)
    with pytest.raises(ContractError):
        build_policy('n', boost_exit_temp_c=-5)


def test_build_policy_rejects_bad_load_pct():
    with pytest.raises(ContractError):
        build_policy('n', max_load_pct=150)


def test_derive_thermal_pressure_thresholds():
    assert derive_thermal_pressure(40) == 'nominal'
    assert derive_thermal_pressure(72) == 'fair'
    assert derive_thermal_pressure(86) == 'serious'
    assert derive_thermal_pressure(100) == 'critical'
    assert derive_thermal_pressure(None) == 'nominal'


def test_diff_telemetry_detects_changes():
    a = build_telemetry('n', 'linux',
                        thermal={'fan_rpm': 1000, 'controllable': True})
    b = build_telemetry('n', 'linux',
                        thermal={'fan_rpm': 2500, 'controllable': True})
    diff = diff_telemetry(a, b)
    assert 'thermal.fan_rpm' in diff


def test_diff_telemetry_empty_when_unchanged():
    a = build_telemetry('n', 'linux')
    b = build_telemetry('n', 'linux', ts=a['ts'])
    diff = diff_telemetry(a, b)
    # ts may differ — but the structural fields should not.
    assert all(not k.startswith('compute.') for k in diff)
    assert all(not k.startswith('thermal.') for k in diff)
