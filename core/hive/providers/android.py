"""core.hive.providers.android — telemetry provider for Android (Termux).

Runs as an unprivileged Termux app, so the SELinux ``untrusted_app``
context blocks most of ``/proc`` and all of ``/sys/class/{thermal,
power_supply}``. We sample only what is reliably readable from a
non-rooted Termux process:

    /proc/meminfo                              -> RAM
    /proc/cpuinfo                              -> core count, ARM ISA
    /sys/devices/system/cpu/cpu*/cpufreq/...   -> scaling freq ratio
    getprop                                    -> model, Android version
    termux-battery-status (if Termux:API)      -> battery %, charging,
                                                  battery temp

CPU load is approximated as the average ratio of current scaling
frequency to max scaling frequency across online CPUs. It is not a
true busy-time figure (we cannot read /proc/stat) but it is a useful
signal: 0% when the kernel parks every core at idle floor, ~100% when
governor pins to fmax. Documented in the field as ``cpu_load_pct``
with this caveat in the contract notes.

All file reads are wrapped in best-effort try/except. A missing or
unreadable source yields ``None`` rather than raising; the agent must
keep sampling even on weird OEM kernels.
"""
from __future__ import annotations

import json
import logging
import os
import platform as _platform
import shutil
import subprocess
from typing import Optional

_LOG = logging.getLogger(__name__)


class AndroidProvider:
    """Android-on-Termux telemetry. Read-only, no hardware control."""

    def platform_name(self) -> str:
        return 'android'

    def capabilities(self) -> list:
        caps = ['inference.cpu', 'inference.tflite']
        if self._gpu_present():
            caps.append('inference.gpu')
        if self._npu_present():
            caps.append('inference.npu')
        return caps

    def _gpu_present(self) -> bool:
        """All Android devices with a display have a GLES GPU."""
        return True

    def _npu_present(self) -> bool:
        """Best-effort NPU detection for Samsung and other Android devices."""
        # Samsung-specific driver probe via getprop / file system.
        manufacturer = (self._getprop('ro.product.manufacturer') or '').lower()
        if manufacturer == 'samsung':
            samsung_libs = [
                '/vendor/lib/libeden_nn_on_system.so',
                '/vendor/lib64/libeden_nn_on_system.so',
                '/vendor/lib/libeden_nn_onsystem.so',
                '/vendor/lib64/libeden_nn_onsystem.so',
                '/system/lib/libeden_nn_on_system.so',
                '/system/lib64/libeden_nn_on_system.so',
            ]
            if any(os.path.exists(p) for p in samsung_libs):
                return True

            # SoC fingerprint heuristic.
            hardware = (self._getprop('ro.hardware') or '').lower()
            board = (self._getprop('ro.product.board') or '').lower()
            known_npu_socs = [
                'exynos2100', 'exynos2200', 'exynos2400',
                'sm8450',   # Snapdragon 8 Gen 1
                'sm8550',   # Snapdragon 8 Gen 2
                'sm8650',   # Snapdragon 8 Gen 3
            ]
            if any(s in hardware or s in board for s in known_npu_socs):
                return True

        # Generic: check for NNAPI HAL libraries.
        nnapi_libs = [
            '/vendor/lib/libneuralnetworks.so',
            '/vendor/lib64/libneuralnetworks.so',
        ]
        if any(os.path.exists(p) for p in nnapi_libs):
            return True

        return False

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _read_text(path: str) -> Optional[str]:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        except OSError:
            return None

    @staticmethod
    def _read_int_file(path: str) -> Optional[int]:
        txt = AndroidProvider._read_text(path)
        if not txt:
            return None
        try:
            return int(txt.strip().splitlines()[0])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _getprop(key: str) -> Optional[str]:
        exe = shutil.which('getprop')
        if not exe:
            return None
        try:
            out = subprocess.run(
                [exe, key],
                capture_output=True, text=True, timeout=2,
            )
            v = (out.stdout or '').strip()
            return v or None
        except (OSError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _termux_battery() -> Optional[dict]:
        """Best-effort Termux:API battery probe. None if unavailable."""
        exe = shutil.which('termux-battery-status')
        if not exe:
            return None
        try:
            out = subprocess.run(
                [exe], capture_output=True, text=True, timeout=4,
            )
            if out.returncode != 0:
                return None
            return json.loads(out.stdout or '{}')
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None

    # ---- compute ---------------------------------------------------------

    def _cpu_load_pct(self) -> Optional[float]:
        """Approximate CPU load from cpufreq ratio across online cores."""
        ratios: list[float] = []
        for n in range(0, 32):
            base = f'/sys/devices/system/cpu/cpu{n}'
            if not os.path.isdir(base):
                if n == 0:
                    return None
                break
            online_path = f'{base}/online'
            # cpu0 has no 'online' file on most kernels (always online).
            if os.path.exists(online_path):
                online = self._read_int_file(online_path)
                if online == 0:
                    continue
            cur = self._read_int_file(f'{base}/cpufreq/scaling_cur_freq')
            mx = self._read_int_file(f'{base}/cpufreq/cpuinfo_max_freq')
            if cur is None or mx is None or mx <= 0:
                continue
            ratio = max(0.0, min(1.0, cur / mx))
            ratios.append(ratio)
        if not ratios:
            return None
        avg = sum(ratios) / len(ratios)
        return round(avg * 100.0, 1)

    def _cpu_peak_temp_c(self) -> Optional[float]:
        """Best source available to untrusted_app: battery temp.

        The kernel's per-cluster CPU thermal zones live under
        /sys/class/thermal which Android blocks for non-system apps.
        Battery temperature tracks SoC heat with a small lag and is the
        most useful proxy we can read. Falls back to None when the
        Termux:API package isn't installed.
        """
        b = self._termux_battery()
        if not b:
            return None
        # Field is reported as float Celsius (e.g. 31.5).
        t = b.get('temperature')
        try:
            return float(t) if t is not None else None
        except (TypeError, ValueError):
            return None

    def compute(self) -> dict:
        load = self._cpu_load_pct()
        return {
            'cpu_load_pct': load,
            'cpu_peak_temp_c': self._cpu_peak_temp_c(),
            # We cannot read thermal throttle state on stock Android.
            'cpu_throttled': None,
            'gpu_present': self._gpu_present(),
            'gpu_load_pct': None,
            'gpu_temp_c': None,
            'npu_present': self._npu_present(),
        }

    # ---- thermal (no fan) -----------------------------------------------

    def thermal(self) -> dict:
        # Phones/tablets are passively cooled; controllable=False is correct.
        return {
            'fan_rpm': None,
            'fan_pwm': None,
            'fan_max_rpm': None,
            'fan_mode': 'passive',
            'controllable': False,
        }

    # ---- memory ----------------------------------------------------------

    def memory(self) -> dict:
        txt = self._read_text('/proc/meminfo') or ''
        kv: dict[str, int] = {}
        for line in txt.splitlines():
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
            k = parts[0].strip()
            v = parts[1].strip().split()
            try:
                kv[k] = int(v[0])
            except (ValueError, IndexError):
                continue
        total_kb = kv.get('MemTotal')
        # MemAvailable is the right "free for new work" figure on modern
        # kernels; falls back to MemFree when MemAvailable is missing.
        avail_kb = kv.get('MemAvailable', kv.get('MemFree'))
        swap_total = kv.get('SwapTotal') or 0
        swap_free = kv.get('SwapFree') or 0
        swap_used_kb = max(0, swap_total - swap_free)

        return {
            'ram_total_mb': (total_kb // 1024) if total_kb else None,
            'ram_free_mb':  (avail_kb // 1024) if avail_kb else None,
            'swap_used_mb': (swap_used_kb // 1024) if swap_total else None,
        }

    # ---- power -----------------------------------------------------------

    def power(self) -> dict:
        b = self._termux_battery() or {}
        pct = b.get('percentage')
        try:
            pct = int(pct) if pct is not None else None
        except (TypeError, ValueError):
            pct = None

        plugged = b.get('plugged')
        # Termux:API reports 'PLUGGED_AC' / 'PLUGGED_USB' / 'UNPLUGGED'.
        on_battery: bool
        if isinstance(plugged, str):
            on_battery = plugged.upper().startswith('UNPLUGGED')
        else:
            on_battery = True  # Default for mobile devices when unknown.

        # Thermal pressure derived from battery temp where available.
        # The contract validator expects one of THERMAL_PRESSURE_LEVELS;
        # local_node.py applies the canonical derive_thermal_pressure()
        # when we leave it as None, so omit it here.
        return {
            'on_battery': on_battery,
            'battery_pct': pct,
            'thermal_pressure': None,
        }

    # ---- bundle ----------------------------------------------------------

    def sample(self) -> dict:
        return {
            'compute': self.compute(),
            'thermal': self.thermal(),
            'memory': self.memory(),
            'power': self.power(),
        }


# ---- detection helper ------------------------------------------------------

def is_android() -> bool:
    """Return True when this Python process is running on Android.

    Detection priorities (any one is sufficient):
      1. ``ANDROID_ROOT`` / ``ANDROID_DATA`` env vars set by the OS init.
      2. Termux's ``$PREFIX`` points inside ``/data/data/com.termux/``.
      3. ``platform.system() == 'Linux'`` and ``/system/build.prop`` or
         ``/system/bin/getprop`` exists (covers proot-distro on Android).
    """
    if os.environ.get('ANDROID_ROOT') or os.environ.get('ANDROID_DATA'):
        return True
    prefix = os.environ.get('PREFIX', '')
    if '/com.termux/' in prefix:
        return True
    if _platform.system().lower() != 'linux':
        return False
    if os.path.exists('/system/build.prop'):
        return True
    if os.path.exists('/system/bin/getprop'):
        return True
    return False
