"""core.hive.providers.linux — Linux telemetry provider.

Reads from procfs / sysfs and (optionally) talks to ``swarm-fanctl`` for
thermal + fan state. No external dependencies. All read-only.
"""
from __future__ import annotations

import glob
import json
import os
import socket
import time
from typing import Optional

from ..contract import derive_thermal_pressure

FANCTL_SOCK = os.environ.get('SWARM_FANCTL_SOCK', '/run/swarm-fanctl.sock')

_LAST_PROC_STAT: Optional[tuple] = None
_LAST_PROC_STAT_TS: float = 0.0


def _read_int(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _read_str(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _query_fanctl(cmd: str) -> dict | None:
    if not os.path.exists(FANCTL_SOCK):
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(FANCTL_SOCK)
            s.sendall(json.dumps({'cmd': cmd, 'payload': {}}).encode() + b'\n')
            buf = b''
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b'\n' in buf:
                    break
        return json.loads(buf.decode().strip())
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _cpu_load_pct() -> float | None:
    """Calculate CPU usage % over the time between successive calls.

    First call returns ``None`` (no baseline). Subsequent calls compute
    the delta from /proc/stat. Caller should call this on a regular
    cadence (e.g. every telemetry tick).
    """
    global _LAST_PROC_STAT, _LAST_PROC_STAT_TS
    try:
        with open('/proc/stat') as f:
            line = f.readline()
    except OSError:
        return None
    parts = line.split()
    if len(parts) < 5 or parts[0] != 'cpu':
        return None
    try:
        nums = [int(p) for p in parts[1:]]
    except ValueError:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    total = sum(nums)
    now = time.monotonic()
    last = _LAST_PROC_STAT
    _LAST_PROC_STAT = (total, idle)
    _LAST_PROC_STAT_TS = now
    if last is None:
        return None
    d_total = total - last[0]
    d_idle = idle - last[1]
    if d_total <= 0:
        return None
    pct = max(0.0, min(100.0, 100.0 * (d_total - d_idle) / d_total))
    return round(pct, 1)


def _cpu_peak_temp_c() -> float | None:
    candidates = []
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        name = _read_str(os.path.join(hwmon, 'name')) or ''
        name = name.lower()
        if name not in ('coretemp', 'k10temp', 'zenpower', 'dell_smm'):
            continue
        inputs = sorted(glob.glob(os.path.join(hwmon, 'temp*_input')))
        if name == 'dell_smm':
            inputs = [p for p in inputs if p.endswith('temp1_input')]
        for p in inputs:
            v = _read_int(p)
            if v is None or v <= 0:
                continue
            candidates.append(v / 1000.0)
    return max(candidates) if candidates else None


def _cpu_throttled() -> bool | None:
    """Best-effort: True if any cpufreq core is currently below cpuinfo_max_freq
    by more than 5%, i.e. capped via thermal/policy."""
    try:
        cores = sorted(glob.glob('/sys/devices/system/cpu/cpu[0-9]*/cpufreq'))
        if not cores:
            return None
        capped = 0
        for c in cores:
            cur = _read_int(os.path.join(c, 'scaling_max_freq'))
            top = _read_int(os.path.join(c, 'cpuinfo_max_freq'))
            if cur is None or top is None or top == 0:
                continue
            if cur < top * 0.95:
                capped += 1
        return capped > 0
    except OSError:
        return None


def _gpu_state() -> tuple:
    """Return (present, load_pct, temp_c). Uses NVIDIA-SMI if present, else
    falls back to AMD's hwmon node names."""
    # NVIDIA
    try:
        import shutil
        import subprocess
        smi = shutil.which('nvidia-smi')
        if smi:
            out = subprocess.run(
                [smi, '--query-gpu=utilization.gpu,temperature.gpu',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2,
            )
            if out.returncode == 0 and out.stdout.strip():
                first = out.stdout.strip().splitlines()[0]
                load_str, temp_str = (s.strip() for s in first.split(','))
                return (True, float(load_str), float(temp_str))
    except Exception:
        pass
    # AMD via amdgpu hwmon
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        if (_read_str(os.path.join(hwmon, 'name')) or '').lower() == 'amdgpu':
            t = _read_int(os.path.join(hwmon, 'temp1_input'))
            return (True, None, t / 1000.0 if t else None)
    # Intel iGPU is nominally always 'present' but we don't pretend to
    # measure load without i915_pmu — leave gpu_present False for
    # unmeasurable GPUs to avoid lying to the scheduler.
    return (False, None, None)


def _meminfo() -> dict:
    out = {'ram_total_mb': None, 'ram_free_mb': None, 'swap_used_mb': None}
    try:
        kv = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, _, v = line.partition(':')
                kv[k.strip()] = v.strip()

        def _kb(k: str) -> int | None:
            v = kv.get(k)
            if not v:
                return None
            try:
                return int(v.split()[0])
            except (ValueError, IndexError):
                return None

        total = _kb('MemTotal')
        avail = _kb('MemAvailable')
        swap_total = _kb('SwapTotal')
        swap_free = _kb('SwapFree')
        if total is not None:
            out['ram_total_mb'] = total // 1024
        if avail is not None:
            out['ram_free_mb'] = avail // 1024
        if swap_total is not None and swap_free is not None:
            out['swap_used_mb'] = max(0, (swap_total - swap_free) // 1024)
    except OSError:
        pass
    return out


def _battery() -> tuple:
    """Return (on_battery: bool, battery_pct: int|None)."""
    try:
        for ps in glob.glob('/sys/class/power_supply/*'):
            ptype = _read_str(os.path.join(ps, 'type')) or ''
            if ptype.lower() != 'battery':
                continue
            status = (_read_str(os.path.join(ps, 'status')) or '').lower()
            cap = _read_int(os.path.join(ps, 'capacity'))
            on_batt = status not in ('charging', 'full', 'unknown', '')
            return (on_batt, cap)
    except OSError:
        pass
    return (False, None)


def _fan_state() -> dict:
    """Pull fan state from swarm-fanctl helper if available, else from
    raw hwmon (read-only).
    """
    helper = _query_fanctl('status')
    if isinstance(helper, dict) and helper.get('ok'):
        # Helper response includes pwm_readback (list of {path, value}).
        readback = helper.get('pwm_readback') or []
        first_pwm = None
        for item in readback:
            if isinstance(item, dict) and item.get('value') is not None:
                first_pwm = int(item['value'])
                break
        return {
            'fan_rpm': _first_fan_rpm(),
            'fan_pwm': first_pwm,
            'fan_max_rpm': _fan_max_rpm(),
            'fan_mode': helper.get('mode') or 'unknown',
            'controllable': True,
        }
    # Read-only fallback.
    return {
        'fan_rpm': _first_fan_rpm(),
        'fan_pwm': _first_pwm_value(),
        'fan_max_rpm': _fan_max_rpm(),
        'fan_mode': 'unknown',
        'controllable': False,
    }


def _first_fan_rpm() -> int | None:
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        for f in sorted(glob.glob(os.path.join(hwmon, 'fan*_input'))):
            v = _read_int(f)
            if v is not None and v > 0:
                return v
    return None


def _fan_max_rpm() -> int | None:
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        for f in sorted(glob.glob(os.path.join(hwmon, 'fan*_max'))):
            v = _read_int(f)
            if v is not None and v > 0:
                return v
    return None


def _first_pwm_value() -> int | None:
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        for f in sorted(glob.glob(os.path.join(hwmon, 'pwm[0-9]'))):
            v = _read_int(f)
            if v is not None:
                return v
    return None


class LinuxProvider:
    def platform_name(self) -> str:
        try:
            with open('/etc/os-release') as f:
                kv = {}
                for line in f:
                    k, _, v = line.partition('=')
                    kv[k.strip()] = v.strip().strip('"')
            distro = kv.get('ID') or 'linux'
            return f'linux-{distro.lower()}'
        except OSError:
            return 'linux'

    def capabilities(self) -> list:
        caps = ['inference.cpu', 'scheduler.coordinator', 'storage.bulk']
        # Ollama detection
        if os.path.exists('/usr/local/bin/ollama') or \
           os.path.exists('/usr/bin/ollama'):
            caps.append('inference.ollama')
        # GPU
        present, _, _ = _gpu_state()
        if present:
            caps.append('inference.gpu')
        return caps

    def compute(self) -> dict:
        gpu_present, gpu_load, gpu_temp = _gpu_state()
        return {
            'cpu_load_pct': _cpu_load_pct(),
            'cpu_peak_temp_c': _cpu_peak_temp_c(),
            'cpu_throttled': _cpu_throttled(),
            'gpu_present': gpu_present,
            'gpu_load_pct': gpu_load,
            'gpu_temp_c': gpu_temp,
            'npu_present': False,
        }

    def thermal(self) -> dict:
        return _fan_state()

    def memory(self) -> dict:
        return _meminfo()

    def power(self) -> dict:
        on_batt, pct = _battery()
        return {
            'on_battery': on_batt,
            'battery_pct': pct,
            'thermal_pressure': derive_thermal_pressure(_cpu_peak_temp_c()),
        }

    def sample(self) -> dict:
        return {
            'compute': self.compute(),
            'thermal': self.thermal(),
            'memory': self.memory(),
            'power': self.power(),
        }
