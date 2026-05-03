"""core.hive.providers.base — provider abstract interface."""
from __future__ import annotations

from typing import Protocol


class Provider(Protocol):
    """Telemetry provider protocol. Returns dicts shaped per contract.py."""

    def platform_name(self) -> str: ...
    def capabilities(self) -> list: ...
    def compute(self) -> dict: ...
    def thermal(self) -> dict: ...
    def memory(self) -> dict: ...
    def power(self) -> dict: ...

    def sample(self) -> dict:
        """Convenience: full bundle (compute, thermal, memory, power)."""
        return {
            'compute': self.compute(),
            'thermal': self.thermal(),
            'memory': self.memory(),
            'power': self.power(),
        }
