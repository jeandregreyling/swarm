"""core.hive.providers.windows — Windows telemetry provider.

Read-only. Tries WMI via the optional ``wmi`` package; falls back to
``ctypes`` GlobalMemoryStatusEx for memory and ``GetSystemPowerStatus``
for battery. CPU temp is firewalled by most consumer BIOSes so we
return None rather than guessing.

If imports fail (running tests on non-Windows or wmi not installed) we
fall back to the GenericProvider shape — the contract still validates.
"""
from __future__ import annotations

import ctypes
import logging
import platform as _platform
import shutil
from ctypes import wintypes

from .generic import GenericProvider

_LOG = logging.getLogger(__name__)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength', wintypes.DWORD),
        ('dwMemoryLoad', wintypes.DWORD),
        ('ullTotalPhys', ctypes.c_uint64),
        ('ullAvailPhys', ctypes.c_uint64),
        ('ullTotalPageFile', ctypes.c_uint64),
        ('ullAvailPageFile', ctypes.c_uint64),
        ('ullTotalVirtual', ctypes.c_uint64),
        ('ullAvailVirtual', ctypes.c_uint64),
        ('sullAvailExtendedVirtual', ctypes.c_uint64),
    ]


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ('ACLineStatus', wintypes.BYTE),
        ('BatteryFlag', wintypes.BYTE),
        ('BatteryLifePercent', wintypes.BYTE),
        ('SystemStatusFlag', wintypes.BYTE),
        ('BatteryLifeTime', wintypes.DWORD),
        ('BatteryFullLifeTime', wintypes.DWORD),
    ]


def _is_windows() -> bool:
    return _platform.system().lower() == 'windows'


def _global_memory_status() -> tuple[int | None, int | None]:
    if not _is_windows():
        return None, None
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return (
                stat.ullTotalPhys // (1024 * 1024),
                stat.ullAvailPhys // (1024 * 1024),
            )
    except OSError:
        _LOG.debug('GlobalMemoryStatusEx failed', exc_info=True)
    return None, None


def _power_status() -> tuple[bool, float | None]:
    if not _is_windows():
        return False, None
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        sps = _SYSTEM_POWER_STATUS()
        if kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
            on_battery = sps.ACLineStatus == 0
            pct = float(sps.BatteryLifePercent) if 0 <= sps.BatteryLifePercent <= 100 else None
            return on_battery, pct
    except OSError:
        _LOG.debug('GetSystemPowerStatus failed', exc_info=True)
    return False, None


def _wmi_thermal_zone_temp_c() -> float | None:
    """Try MSAcpi_ThermalZoneTemperature via the ``wmi`` package.

    BIOS firewalls block this on most consumer hardware; treat as
    best-effort.
    """
    if not _is_windows():
        return None
    try:
        import wmi  # type: ignore
    except ImportError:
        return None
    try:
        c = wmi.WMI(namespace=r'root\wmi')
        zones = c.MSAcpi_ThermalZoneTemperature()
        for z in zones:
            # Reported in tenths of Kelvin.
            kelvin10 = getattr(z, 'CurrentTemperature', None)
            if kelvin10 and kelvin10 > 0:
                return round((kelvin10 / 10.0) - 273.15, 1)
    except Exception:
        _LOG.debug('WMI thermal zone read failed', exc_info=True)
    return None


class WindowsProvider(GenericProvider):
    def platform_name(self) -> str:
        return 'windows'

    def capabilities(self) -> list:
        caps = ['inference.cpu', 'scheduler.coordinator', 'storage.bulk']
        if shutil.which('ollama') or shutil.which('ollama.exe'):
            caps.append('inference.ollama')
        return caps

    def compute(self) -> dict:
        return {
            'cpu_load_pct': None,
            'cpu_peak_temp_c': _wmi_thermal_zone_temp_c(),
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
            'fan_mode': 'auto',
            'controllable': False,
        }

    def memory(self) -> dict:
        total, avail = _global_memory_status()
        return {
            'ram_total_mb': total,
            'ram_free_mb': avail,
            'swap_used_mb': None,
        }

    def power(self) -> dict:
        on_bat, pct = _power_status()
        return {
            'on_battery': on_bat,
            'battery_pct': pct,
            'thermal_pressure': 'nominal',
        }
