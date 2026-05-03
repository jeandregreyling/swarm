"""core/fan_controller.py — read-only fan / temperature monitor.

The actual PWM writes happen in a separate privileged helper
(`ops/swarm-fanctl.py`, installed as `swarm-fanctl.service`). That helper is
*opt-in*: the user installs it manually with `sudo`. Until it's installed, this
module reports status but all mode changes return {ok: false, reason: ...}.

Targets (set by the privileged helper when enabled):
  - auto / normal: hold CPU ≈ 56–60°C under sustained load.
  - boost:         hold CPU ≈ 40°C when possible (max fan, higher noise).

Cross-platform plan:
  - Linux:  read `/sys/class/hwmon/*/temp*_input` and `/sys/class/thermal/...`.
  - macOS:  read via `osx-cpu-temp` binary if available.
  - other:  return best-effort nothing.
"""
from __future__ import annotations

import json
import os
import platform
import socket
from typing import Optional

FANCTL_SOCK = os.environ.get('SWARM_FANCTL_SOCK', '/run/swarm-fanctl.sock')


def _read_linux_temps() -> list:
    temps = []
    root = '/sys/class/hwmon'
    if not os.path.isdir(root):
        return temps
    for name in sorted(os.listdir(root)):
        base = os.path.join(root, name)
        try:
            chip = open(os.path.join(base, 'name')).read().strip()
        except OSError:
            chip = name
        for f in sorted(os.listdir(base)):
            if f.startswith('temp') and f.endswith('_input'):
                try:
                    with open(os.path.join(base, f)) as fh:
                        val_milli = int(fh.read().strip())
                    temps.append({
                        'chip': chip,
                        'sensor': f[:-6],
                        'c': val_milli / 1000.0,
                    })
                except (OSError, ValueError):
                    continue
    return temps


def read_temps() -> list:
    if platform.system() == 'Linux':
        return _read_linux_temps()
    return []


def summary() -> dict:
    temps = read_temps()
    cpu = None
    # Heuristic: the CPU package temp is usually labelled 'coretemp' or 'k10temp'.
    for t in temps:
        if t['chip'].lower() in ('coretemp', 'k10temp', 'zenpower') and cpu is None:
            cpu = t['c']
    if cpu is None and temps:
        cpu = max(t['c'] for t in temps)
    helper_up = os.path.exists(FANCTL_SOCK)
    # Y.58f — pull the richer 'status' response if the helper supports it
    # (mode, pwm_readback, turbo_disabled, max_perf_pct, watchdog_alive).
    # Fall back to the legacy 'mode' command if 'status' isn't recognised.
    status = _query_helper('status') if helper_up else None
    if isinstance(status, dict) and status.get('ok'):
        mode = status.get('mode')
        helper_state = {
            'mode': mode,
            'pwm_readback': status.get('pwm_readback') or [],
            'turbo_disabled': status.get('turbo_disabled'),
            'max_perf_pct': status.get('max_perf_pct'),
            'watchdog_alive': status.get('watchdog_alive'),
            'boost_perf_cap': status.get('boost_perf_cap'),
            'boost_exit_temp': status.get('boost_exit_temp'),
            'cpu_peak_c': status.get('cpu_peak_c'),
        }
    else:
        mode_raw = _query_helper('mode') if helper_up else None
        mode = mode_raw.get('mode') if isinstance(mode_raw, dict) else mode_raw
        helper_state = {'mode': mode}
    return {
        'cpu_c': cpu,
        'temps': temps,
        'helper_installed': helper_up,
        'mode': mode,
        'helper_state': helper_state,
        'targets': {'auto': [56, 60], 'boost': [40, 40]},
    }


def _query_helper(cmd: str, payload: Optional[dict] = None) -> Optional[dict]:
    if not os.path.exists(FANCTL_SOCK):
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(FANCTL_SOCK)
            s.sendall(json.dumps({'cmd': cmd, 'payload': payload or {}}).encode() + b'\n')
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


def set_mode(mode: str) -> dict:
    """Request a mode change via the privileged helper."""
    if mode not in ('auto', 'boost'):
        return {'ok': False, 'error': 'invalid mode'}
    if not os.path.exists(FANCTL_SOCK):
        return {
            'ok': False,
            'reason': 'helper-not-installed',
            'hint': 'Install swarm-fanctl.service (ops/swarm-fanctl.service). '
                    'See docs/runbooks/fan-controller.md.',
        }
    resp = _query_helper('set_mode', {'mode': mode}) or {'ok': False,
                                                          'error': 'no response'}
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# Phase-6 S-C194440A7C — cross-platform fan profile lookup + self-install.
# ═══════════════════════════════════════════════════════════════════════════
def _read_macos_temps() -> list:
    """macOS thermal read via the `osx-cpu-temp` helper if present."""
    try:
        import shutil
        import subprocess
        binp = shutil.which('osx-cpu-temp')
        if not binp:
            return []
        out = subprocess.run([binp], capture_output=True, text=True, timeout=2)
        txt = (out.stdout or '').strip()
        if not txt:
            return []
        # "56.2°C" -> 56.2
        val = float(txt.replace('°C', '').strip())
        return [{'chip': 'osx-cpu-temp', 'sensor': 'cpu', 'c': val}]
    except Exception:
        return []


def _read_windows_temps() -> list:
    """Windows thermal read via WMI MSAcpi_ThermalZoneTemperature.

    Values are returned in tenths of Kelvin; convert to Celsius.
    Requires ``pywin32``/``wmi``; on failure we silently report nothing.
    """
    try:
        import wmi  # type: ignore
        c = wmi.WMI(namespace=r'root\wmi')
        temps = []
        for probe in c.MSAcpi_ThermalZoneTemperature():  # type: ignore
            k = float(probe.CurrentTemperature) / 10.0
            temps.append({'chip': 'wmi', 'sensor': 'ThermalZone', 'c': k - 273.15})
        return temps
    except Exception:
        return []


def read_temps_cross_platform() -> list:
    sys_name = platform.system()
    if sys_name == 'Linux':
        return _read_linux_temps()
    if sys_name == 'Darwin':
        return _read_macos_temps()
    if sys_name == 'Windows':
        return _read_windows_temps()
    return []


def self_install_hint() -> dict:
    """Return the exact operator command to install the privileged helper
    for the current platform. Used by the Settings → System modifications
    tile and by the onboarding sysmod pack wizard.
    """
    sys_name = platform.system()
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if sys_name == 'Linux':
        return {
            'platform': 'linux',
            'cmd': f"sudo cp {repo}/ops/swarm-fanctl.service /etc/systemd/system/ && "
                   f"sudo systemctl daemon-reload && "
                   f"sudo systemctl enable --now swarm-fanctl.service",
            'notes': 'Helper writes to /sys/class/hwmon PWM files; requires root.',
        }
    if sys_name == 'Darwin':
        return {
            'platform': 'darwin',
            'cmd': 'brew install osx-cpu-temp smcFanControl',
            'notes': 'smcFanControl handles mode changes; Swarm only reads temps.',
        }
    if sys_name == 'Windows':
        return {
            'platform': 'windows',
            'cmd': 'pip install wmi pywin32 && install NoteBook FanControl or FanCtrl.exe',
            'notes': 'WMI thermal read works without admin; fan control requires vendor tooling.',
        }
    return {'platform': sys_name.lower() or 'unknown', 'cmd': None, 'notes': 'unsupported platform'}


def summary_cross_platform() -> dict:
    """Cross-platform summary: picks the right backend, always returns a dict."""
    temps = read_temps_cross_platform()
    cpu = None
    for t in temps:
        if t.get('sensor', '').lower() == 'cpu' and cpu is None:
            cpu = t['c']
    if cpu is None and temps:
        cpu = max(t['c'] for t in temps)
    helper_up = platform.system() == 'Linux' and os.path.exists(FANCTL_SOCK)
    return {
        'platform': platform.system().lower(),
        'cpu_c': cpu,
        'temps': temps,
        'helper_installed': helper_up,
        'self_install': self_install_hint(),
        'targets': {'auto': [56, 60], 'boost': [40, 40]},
    }
