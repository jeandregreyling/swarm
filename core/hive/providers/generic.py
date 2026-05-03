"""core.hive.providers.generic — fallback provider for unknown platforms.

Returns null-shape dicts so the contract validator passes everywhere.
Real platforms supply LinuxProvider / MacOSProvider / etc.
"""
from __future__ import annotations

import platform as _platform


class GenericProvider:
    def platform_name(self) -> str:
        sysname = _platform.system().lower() or 'unknown'
        return sysname

    def capabilities(self) -> list:
        return ['inference.cpu']

    def compute(self) -> dict:
        return {
            'cpu_load_pct': None,
            'cpu_peak_temp_c': None,
            'cpu_throttled': None,
            'gpu_present': False,
            'gpu_load_pct': None,
            'gpu_temp_c': None,
            'npu_present': False,
        }

    def thermal(self) -> dict:
        return {
            'fan_rpm': None,
            'fan_pwm': None,
            'fan_max_rpm': None,
            'fan_mode': 'unknown',
            'controllable': False,
        }

    def memory(self) -> dict:
        return {
            'ram_total_mb': None,
            'ram_free_mb': None,
            'swap_used_mb': None,
        }

    def power(self) -> dict:
        return {
            'on_battery': False,
            'battery_pct': None,
            'thermal_pressure': 'nominal',
        }

    def sample(self) -> dict:
        return {
            'compute': self.compute(),
            'thermal': self.thermal(),
            'memory': self.memory(),
            'power': self.power(),
        }
