"""core.hive.providers — per-platform telemetry providers.

Each provider exposes:

    sample() -> dict     subset of contract-v0 sections (compute/thermal/...)
    capabilities() -> list[str]
    platform_name() -> str

Providers are pure read functions; they never write to hardware. Hardware
control routes through ``ops/swarm-fanctl.py`` (Linux) or platform-specific
helpers, never directly from a provider.
"""
from __future__ import annotations

import platform as _platform

from .base import Provider
from .generic import GenericProvider


def detect_provider() -> Provider:
    """Return the best provider for the current platform."""
    sysname = _platform.system().lower()
    if sysname == 'linux':
        from .linux import LinuxProvider
        return LinuxProvider()
    if sysname == 'darwin':
        from .macos import MacOSProvider
        return MacOSProvider()
    if sysname == 'windows':
        from .windows import WindowsProvider
        return WindowsProvider()
    return GenericProvider()


__all__ = ['Provider', 'GenericProvider', 'detect_provider']
