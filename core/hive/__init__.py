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
from .local_node import LocalNode, build_local_telemetry, reset_local_node
from .node_enrollment import (
    discover_peer_capabilities,
    enroll_local_node,
    find_peer_for_model,
    load_enrollment,
)
from .registry import HiveRegistry, get_registry
from .system_profile import (
    build_shareable_manifest,
    collect_system_profile,
    probe_hardware,
    probe_runtimes,
    recommend_role_models,
)

__all__ = [
    'CONTRACT_VERSION',
    'THERMAL_PRESSURE_LEVELS',
    'build_telemetry',
    'build_policy',
    'validate_telemetry',
    'validate_policy',
    'LocalNode',
    'build_local_telemetry',
    'reset_local_node',
    'HiveRegistry',
    'get_registry',
    'probe_hardware',
    'probe_runtimes',
    'recommend_role_models',
    'build_shareable_manifest',
    'collect_system_profile',
    'enroll_local_node',
    'load_enrollment',
    'discover_peer_capabilities',
    'find_peer_for_model',
]
