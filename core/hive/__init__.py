"""core.hive — cross-platform compute hive.

Fridays as the executive layer pooling owner-confirmed hardware (Linux,
Windows, macOS, Android, iOS). Each device is an independent node that
implements the Node Resource Contract v0 (see docs/NODE_RESOURCE_CONTRACT.md)
and reports telemetry to a single executive.

Public surface:
    contract       — JSON shape definitions, builders, validator
    registry       — persistent node registry (SQLite)
    local_node     — produces telemetry for THIS process's host
    providers      — per-platform telemetry providers
    enrolment      — token / handshake helpers for remote nodes

Nothing in this package writes to hardware. Hardware control happens via
``ops/swarm-fanctl.py`` (Linux) and the equivalent platform helpers; this
package only orchestrates and observes.
"""
from __future__ import annotations

from .contract import (
    CONTRACT_VERSION,
    THERMAL_PRESSURE_LEVELS,
    build_telemetry,
    build_policy,
    validate_telemetry,
    validate_policy,
)
from .local_node import LocalNode, build_local_telemetry
from .registry import HiveRegistry, get_registry

__all__ = [
    'CONTRACT_VERSION',
    'THERMAL_PRESSURE_LEVELS',
    'build_telemetry',
    'build_policy',
    'validate_telemetry',
    'validate_policy',
    'LocalNode',
    'build_local_telemetry',
    'HiveRegistry',
    'get_registry',
]
