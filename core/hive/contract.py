"""core.hive.contract — Node Resource Contract v0.

Single source of truth for the JSON shapes every Hive node speaks. Two
envelopes:

    node.resource/v0   telemetry  (node → executive)
    node.policy/v0     policy     (executive → node)

Spec: docs/NODE_RESOURCE_CONTRACT.md.

Design rules:
    1. Any field a platform cannot provide is ``None`` — never absent.
    2. ``controllable: False`` means telemetry-only; policy commands accepted
       but no-op'd, and the executive must surface that.
    3. ``capabilities`` is a flat list of well-known strings. New strings
       added to the doc when first emitted by a node.

This module has no I/O. Builders create dicts; validators raise
``ContractError`` on shape violations.
"""
from __future__ import annotations

import time
from typing import Any, Iterable

CONTRACT_VERSION = 'v0'
TELEMETRY_CONTRACT = f'node.resource/{CONTRACT_VERSION}'
POLICY_CONTRACT = f'node.policy/{CONTRACT_VERSION}'

THERMAL_PRESSURE_LEVELS = ('nominal', 'fair', 'serious', 'critical')

# Well-known capability strings. Add new ones to docs/NODE_RESOURCE_CONTRACT.md
# when first emitted.
KNOWN_CAPABILITIES = frozenset({
    'inference.cpu',
    'inference.gpu',
    'inference.npu',
    'inference.ollama',
    'inference.lmstudio',
    'inference.coreml',
    'inference.tflite',
    'scheduler.coordinator',
    'scheduler.worker',
    'storage.bulk',
    'audio.capture',
    'audio.playback',
    'video.capture',
    'sensors.location',
    'sensors.imu',
})

FAN_MODES = ('auto', 'boost', 'manual', 'passive', 'silent', 'unknown')


class ContractError(ValueError):
    """Raised when a payload violates the contract shape."""


# ─────────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────────

def _empty_compute() -> dict:
    return {
        'cpu_load_pct': None,
        'cpu_peak_temp_c': None,
        'cpu_throttled': None,
        'gpu_present': False,
        'gpu_load_pct': None,
        'gpu_temp_c': None,
        'npu_present': False,
    }


def _empty_thermal() -> dict:
    return {
        'fan_rpm': None,
        'fan_pwm': None,
        'fan_max_rpm': None,
        'fan_mode': 'unknown',
        'controllable': False,
    }


def _empty_memory() -> dict:
    return {
        'ram_total_mb': None,
        'ram_free_mb': None,
        'swap_used_mb': None,
    }


def _empty_power() -> dict:
    return {
        'on_battery': False,
        'battery_pct': None,
        'thermal_pressure': 'nominal',
    }


def build_telemetry(
    node_id: str,
    platform: str,
    *,
    compute: dict | None = None,
    thermal: dict | None = None,
    memory: dict | None = None,
    power: dict | None = None,
    capabilities: Iterable[str] | None = None,
    ts: float | None = None,
) -> dict:
    """Build a v0 telemetry envelope, filling in null-default subtrees.

    Callers pass partial subtrees; missing fields are populated with
    ``None`` / sensible defaults so downstream consumers can rely on a
    fully-populated shape.
    """
    if not node_id or not isinstance(node_id, str):
        raise ContractError('node_id must be a non-empty string')
    if not platform or not isinstance(platform, str):
        raise ContractError('platform must be a non-empty string')

    out_compute = _empty_compute()
    if compute:
        out_compute.update({k: v for k, v in compute.items()
                            if k in out_compute})
    out_thermal = _empty_thermal()
    if thermal:
        out_thermal.update({k: v for k, v in thermal.items()
                            if k in out_thermal})
    out_memory = _empty_memory()
    if memory:
        out_memory.update({k: v for k, v in memory.items()
                           if k in out_memory})
    out_power = _empty_power()
    if power:
        out_power.update({k: v for k, v in power.items()
                          if k in out_power})

    caps_list = sorted(set(capabilities or ()))

    payload = {
        'contract': TELEMETRY_CONTRACT,
        'node_id': node_id,
        'platform': platform,
        'ts': int(ts if ts is not None else time.time()),
        'compute': out_compute,
        'thermal': out_thermal,
        'memory': out_memory,
        'power': out_power,
        'capabilities': caps_list,
    }
    validate_telemetry(payload)
    return payload


def build_policy(
    node_id: str,
    *,
    fan_mode: str | None = None,
    boost_exit_temp_c: float | None = None,
    max_load_pct: int | None = None,
    accept_jobs: bool | None = None,
    ts: float | None = None,
) -> dict:
    """Build a v0 policy envelope. All policy fields optional; omitted
    keys are absent from the resulting subtrees so the receiver knows
    they were not specified.
    """
    if not node_id or not isinstance(node_id, str):
        raise ContractError('node_id must be a non-empty string')

    thermal: dict = {}
    if fan_mode is not None:
        if fan_mode not in FAN_MODES:
            raise ContractError(f'fan_mode must be one of {FAN_MODES}, '
                                f'got {fan_mode!r}')
        thermal['fan_mode'] = fan_mode
    if boost_exit_temp_c is not None:
        if not isinstance(boost_exit_temp_c, (int, float)):
            raise ContractError('boost_exit_temp_c must be numeric')
        if boost_exit_temp_c < 30 or boost_exit_temp_c > 110:
            raise ContractError('boost_exit_temp_c outside sane range 30..110')
        thermal['boost_exit_temp_c'] = float(boost_exit_temp_c)

    compute: dict = {}
    if max_load_pct is not None:
        if not isinstance(max_load_pct, int):
            raise ContractError('max_load_pct must be int')
        if max_load_pct < 0 or max_load_pct > 100:
            raise ContractError('max_load_pct out of range 0..100')
        compute['max_load_pct'] = max_load_pct
    if accept_jobs is not None:
        compute['accept_jobs'] = bool(accept_jobs)

    policy: dict = {}
    if thermal:
        policy['thermal'] = thermal
    if compute:
        policy['compute'] = compute

    payload = {
        'contract': POLICY_CONTRACT,
        'node_id': node_id,
        'ts': int(ts if ts is not None else time.time()),
        'policy': policy,
    }
    validate_policy(payload)
    return payload


# ─────────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────────

def _require(d: Any, key: str, types: tuple, *, allow_none: bool = False,
             where: str = '') -> None:
    if not isinstance(d, dict):
        raise ContractError(f'{where}: expected dict, got {type(d).__name__}')
    if key not in d:
        raise ContractError(f'{where}: missing key {key!r}')
    val = d[key]
    if val is None:
        if allow_none:
            return
        raise ContractError(f'{where}.{key}: must not be null')
    if not isinstance(val, types):
        wanted = '|'.join(t.__name__ for t in types)
        raise ContractError(f'{where}.{key}: expected {wanted}, '
                            f'got {type(val).__name__}')


def _require_pct(d: dict, key: str, where: str) -> None:
    val = d.get(key)
    if val is None:
        return
    if not isinstance(val, (int, float)):
        raise ContractError(f'{where}.{key}: expected number')
    if val < 0 or val > 100:
        raise ContractError(f'{where}.{key}: out of range 0..100')


def validate_telemetry(payload: dict) -> None:
    """Raise ``ContractError`` if ``payload`` is not a valid v0 telemetry
    envelope. Returns ``None`` on success.
    """
    if not isinstance(payload, dict):
        raise ContractError('telemetry: not a dict')
    if payload.get('contract') != TELEMETRY_CONTRACT:
        raise ContractError(f'telemetry: contract must be {TELEMETRY_CONTRACT!r}')
    _require(payload, 'node_id', (str,), where='telemetry')
    _require(payload, 'platform', (str,), where='telemetry')
    _require(payload, 'ts', (int, float), where='telemetry')

    # compute
    _require(payload, 'compute', (dict,), where='telemetry')
    c = payload['compute']
    _require_pct(c, 'cpu_load_pct', 'telemetry.compute')
    _require_pct(c, 'gpu_load_pct', 'telemetry.compute')
    for k in ('cpu_peak_temp_c', 'gpu_temp_c'):
        v = c.get(k)
        if v is not None and not isinstance(v, (int, float)):
            raise ContractError(f'telemetry.compute.{k}: expected number')
    for k in ('gpu_present', 'npu_present'):
        v = c.get(k)
        if v is not None and not isinstance(v, bool):
            raise ContractError(f'telemetry.compute.{k}: expected bool')
    if c.get('cpu_throttled') is not None and not isinstance(c['cpu_throttled'], bool):
        raise ContractError('telemetry.compute.cpu_throttled: expected bool')

    # thermal
    _require(payload, 'thermal', (dict,), where='telemetry')
    th = payload['thermal']
    for k in ('fan_rpm', 'fan_pwm', 'fan_max_rpm'):
        v = th.get(k)
        if v is not None and not isinstance(v, (int, float)):
            raise ContractError(f'telemetry.thermal.{k}: expected number')
    fm = th.get('fan_mode')
    if fm is not None and fm not in FAN_MODES:
        raise ContractError(f'telemetry.thermal.fan_mode: must be one of {FAN_MODES}')
    if not isinstance(th.get('controllable'), bool):
        raise ContractError('telemetry.thermal.controllable: expected bool')

    # memory
    _require(payload, 'memory', (dict,), where='telemetry')
    m = payload['memory']
    for k in ('ram_total_mb', 'ram_free_mb', 'swap_used_mb'):
        v = m.get(k)
        if v is not None and not isinstance(v, (int, float)):
            raise ContractError(f'telemetry.memory.{k}: expected number')
        if isinstance(v, (int, float)) and v < 0:
            raise ContractError(f'telemetry.memory.{k}: must be >= 0')

    # power
    _require(payload, 'power', (dict,), where='telemetry')
    p = payload['power']
    if not isinstance(p.get('on_battery'), bool):
        raise ContractError('telemetry.power.on_battery: expected bool')
    if p.get('battery_pct') is not None:
        _require_pct(p, 'battery_pct', 'telemetry.power')
    tp = p.get('thermal_pressure')
    if tp is not None and tp not in THERMAL_PRESSURE_LEVELS:
        raise ContractError(
            f'telemetry.power.thermal_pressure: must be one of '
            f'{THERMAL_PRESSURE_LEVELS}, got {tp!r}'
        )

    # capabilities
    caps = payload.get('capabilities')
    if not isinstance(caps, list):
        raise ContractError('telemetry.capabilities: expected list')
    for cap in caps:
        if not isinstance(cap, str) or not cap:
            raise ContractError(
                'telemetry.capabilities: items must be non-empty strings'
            )


def validate_policy(payload: dict) -> None:
    """Raise ``ContractError`` if ``payload`` is not a valid v0 policy
    envelope.
    """
    if not isinstance(payload, dict):
        raise ContractError('policy: not a dict')
    if payload.get('contract') != POLICY_CONTRACT:
        raise ContractError(f'policy: contract must be {POLICY_CONTRACT!r}')
    _require(payload, 'node_id', (str,), where='policy')
    _require(payload, 'ts', (int, float), where='policy')
    _require(payload, 'policy', (dict,), where='policy')

    pol = payload['policy']
    if 'thermal' in pol:
        th = pol['thermal']
        if not isinstance(th, dict):
            raise ContractError('policy.thermal: expected dict')
        if 'fan_mode' in th and th['fan_mode'] not in FAN_MODES:
            raise ContractError(
                f'policy.thermal.fan_mode: must be one of {FAN_MODES}'
            )
        if 'boost_exit_temp_c' in th:
            v = th['boost_exit_temp_c']
            if not isinstance(v, (int, float)):
                raise ContractError(
                    'policy.thermal.boost_exit_temp_c: expected number'
                )
            if v < 30 or v > 110:
                raise ContractError(
                    'policy.thermal.boost_exit_temp_c: out of range 30..110'
                )
    if 'compute' in pol:
        c = pol['compute']
        if not isinstance(c, dict):
            raise ContractError('policy.compute: expected dict')
        if 'max_load_pct' in c:
            _require_pct(c, 'max_load_pct', 'policy.compute')
        if 'accept_jobs' in c and not isinstance(c['accept_jobs'], bool):
            raise ContractError('policy.compute.accept_jobs: expected bool')


# ─────────────────────────────────────────────────────────────────────────
# Diff / merge helpers
# ─────────────────────────────────────────────────────────────────────────

def diff_telemetry(prev: dict | None, curr: dict) -> dict:
    """Return a flat diff dict {field_path: (old, new)} for fields that
    changed between two telemetry payloads. Used by the registry to drive
    SSE updates without spamming.
    """
    if prev is None:
        return {'__new__': (None, curr.get('node_id'))}
    out: dict = {}
    for section in ('compute', 'thermal', 'memory', 'power'):
        a = (prev.get(section) or {}) if isinstance(prev, dict) else {}
        b = (curr.get(section) or {}) if isinstance(curr, dict) else {}
        for k in set(a) | set(b):
            if a.get(k) != b.get(k):
                out[f'{section}.{k}'] = (a.get(k), b.get(k))
    if set(prev.get('capabilities') or ()) != set(curr.get('capabilities') or ()):
        out['capabilities'] = (
            prev.get('capabilities'), curr.get('capabilities'),
        )
    return out


def derive_thermal_pressure(cpu_temp_c: float | None,
                            *,
                            fair_at: float = 70.0,
                            serious_at: float = 85.0,
                            critical_at: float = 95.0) -> str:
    """Heuristic mapping cpu temperature → contract thermal_pressure level.
    Used by Linux/macOS providers that don't have a native equivalent.
    """
    if cpu_temp_c is None:
        return 'nominal'
    if cpu_temp_c >= critical_at:
        return 'critical'
    if cpu_temp_c >= serious_at:
        return 'serious'
    if cpu_temp_c >= fair_at:
        return 'fair'
    return 'nominal'
