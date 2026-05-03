"""core.hive.providers.macos — Darwin telemetry provider.

Read-only. Uses POSIX/userland tools when available:
    - sysctl hw.ncpu, hw.memsize
    - vm_stat (free/active/inactive pages)
    - pmset -g batt (on-battery, charge level)
    - osx-cpu-temp / istats (optional, third-party)
    - powermetrics (root-only — not invoked from here)
    - system_profiler SPDisplaysDataType (gpu detect, optional)

Anything we cannot read returns None / safe defaults so the contract
validator stays happy. No hardware writes.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess

from .generic import GenericProvider

_LOG = logging.getLogger(__name__)
_PAGE_SIZE = 4096  # macOS default; refined at import time below
try:
    _PAGE_SIZE = os.sysconf('SC_PAGE_SIZE')
except (ValueError, AttributeError, OSError):
    pass


def _run(cmd: list[str], timeout: float = 1.5) -> str | None:
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
        if out.returncode != 0:
            return None
        return out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _sysctl_int(key: str) -> int | None:
    if not shutil.which('sysctl'):
        return None
    out = _run(['sysctl', '-n', key])
    if out is None:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def _vm_stat() -> dict[str, int]:
    if not shutil.which('vm_stat'):
        return {}
    raw = _run(['vm_stat'])
    if not raw:
        return {}
    rows: dict[str, int] = {}
    for line in raw.splitlines():
        m = re.match(r'^(.+?):\s+(\d+)\.', line)
        if not m:
            continue
        rows[m.group(1).strip()] = int(m.group(2))
    return rows


def _osx_cpu_temp() -> float | None:
    if not shutil.which('osx-cpu-temp'):
        return None
    raw = _run(['osx-cpu-temp'])
    if not raw:
        return None
    m = re.search(r'([\d.]+)\s*°?C', raw)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _pmset_battery() -> tuple[bool, float | None]:
    if not shutil.which('pmset'):
        return False, None
    raw = _run(['pmset', '-g', 'batt'])
    if not raw:
        return False, None
    on_battery = 'Battery Power' in raw
    pct = None
    m = re.search(r'(\d+)%', raw)
    if m:
        try:
            pct = float(m.group(1))
        except ValueError:
            pass
    return on_battery, pct


class MacOSProvider(GenericProvider):
    def platform_name(self) -> str:
        return 'darwin'

    def capabilities(self) -> list:
        caps = ['inference.cpu', 'scheduler.coordinator', 'storage.bulk']
        # Apple Silicon → assume Metal/CoreML/ANE present.
        machine = _run(['uname', '-m']) or ''
        if 'arm64' in machine:
            caps.extend(['inference.gpu', 'inference.coreml', 'inference.npu'])
        if shutil.which('ollama'):
            caps.append('inference.ollama')
        return caps

    def compute(self) -> dict:
        return {
            'cpu_load_pct': None,  # would need iterating host_processor_info
            'cpu_peak_temp_c': _osx_cpu_temp(),
            'cpu_throttled': None,
            'gpu_present': True,  # Macs always have a GPU
            'gpu_load_pct': None,
            'gpu_temp_c': None,
            'npu_present': True,
        }

    def thermal(self) -> dict:
        # Mac fans are SMC-controlled; we don't speak SMC from this layer.
        return {
            'fan_rpm': None,
            'fan_pwm': None,
            'fan_max_rpm': None,
            'fan_mode': 'auto',
            'controllable': False,
        }

    def memory(self) -> dict:
        total = _sysctl_int('hw.memsize')
        ram_total_mb = total // (1024 * 1024) if total else None
        free_mb = None
        rows = _vm_stat()
        if rows:
            free_pages = rows.get('Pages free', 0) + rows.get('Pages inactive', 0)
            free_mb = (free_pages * _PAGE_SIZE) // (1024 * 1024)
        return {
            'ram_total_mb': ram_total_mb,
            'ram_free_mb': free_mb,
            'swap_used_mb': None,
        }

    def power(self) -> dict:
        on_bat, pct = _pmset_battery()
        return {
            'on_battery': on_bat,
            'battery_pct': pct,
            'thermal_pressure': 'nominal',  # contract layer derives from CPU temp
        }
