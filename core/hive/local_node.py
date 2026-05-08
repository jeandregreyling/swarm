"""core.hive.local_node — telemetry for THIS host.

Wraps the auto-detected platform provider, applies derived fields
(thermal pressure from cpu_peak_temp_c when the provider didn't supply
one), and emits a contract-v0 telemetry envelope.

The node_id is stable per host: SHA1 of /etc/machine-id (Linux) or
platform.node() fallback, truncated to 16 hex chars and prefixed with
the platform name. Override via $SWARM_NODE_ID.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform as _platform
from typing import Iterable

from .contract import (
    THERMAL_PRESSURE_LEVELS,
    build_telemetry,
    derive_thermal_pressure,
)
from .providers import detect_provider
from .providers.base import Provider

_LOG = logging.getLogger(__name__)


def _machine_seed() -> str:
    """Return a stable per-host string."""
    for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                seed = f.read().strip()
            if seed:
                return seed
        except OSError:
            pass
    return _platform.node() or 'unknown-host'


def _default_node_id(platform_name: str) -> str:
    env = os.environ.get('SWARM_NODE_ID', '').strip()
    if env:
        return env
    seed = _machine_seed()
    digest = hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]
    short_plat = platform_name.split('-', 1)[0]
    return f'{short_plat}-{digest}'


class LocalNode:
    """Adapter wrapping a platform provider into contract-v0 telemetry."""

    def __init__(self, provider: Provider | None = None,
                 node_id: str | None = None) -> None:
        self.provider: Provider = provider or detect_provider()
        self.platform_name: str = self.provider.platform_name()
        self.node_id: str = node_id or _default_node_id(self.platform_name)

    def capabilities(self) -> list[str]:
        try:
            caps = list(self.provider.capabilities() or [])
        except Exception:
            _LOG.exception('provider.capabilities() failed')
            caps = ['inference.cpu']
        return sorted({str(c) for c in caps if c})

    def sample(self) -> dict:
        """Return contract-v0 telemetry for this host."""
        try:
            bundle = self.provider.sample()
        except Exception:
            _LOG.exception('provider.sample() failed; emitting empty bundle')
            bundle = {'compute': {}, 'thermal': {}, 'memory': {}, 'power': {}}

        compute = dict(bundle.get('compute') or {})
        thermal = dict(bundle.get('thermal') or {})
        memory = dict(bundle.get('memory') or {})
        power = dict(bundle.get('power') or {})

        # Derive thermal_pressure from cpu_peak_temp_c if the provider
        # didn't pin a value.
        tp = power.get('thermal_pressure')
        if tp not in THERMAL_PRESSURE_LEVELS:
            cpu_temp = compute.get('cpu_peak_temp_c')
            if isinstance(cpu_temp, (int, float)):
                power['thermal_pressure'] = derive_thermal_pressure(cpu_temp)
            else:
                power['thermal_pressure'] = 'nominal'

        return build_telemetry(
            self.node_id,
            self.platform_name,
            compute=compute,
            thermal=thermal,
            memory=memory,
            power=power,
            capabilities=self.capabilities(),
        )


_SINGLETON: LocalNode | None = None


def get_local_node() -> LocalNode:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LocalNode()
    return _SINGLETON


def build_local_telemetry(node_id: str | None = None,
                          capabilities: Iterable[str] | None = None) -> dict:
    """Convenience: one-shot telemetry sample for the current host.

    ``capabilities``, when provided, is unioned with the provider's own
    capability list (lets callers add e.g. ``inference.lmstudio`` after
    sniffing ports).
    """
    node = LocalNode(node_id=node_id) if node_id else get_local_node()
    payload = node.sample()
    if capabilities:
        merged = sorted(set(payload['capabilities']) | {str(c) for c in capabilities if c})
        payload['capabilities'] = merged
    return payload
