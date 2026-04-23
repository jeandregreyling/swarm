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
    mode = _query_helper('mode') if helper_up else None
    return {
        'cpu_c': cpu,
        'temps': temps,
        'helper_installed': helper_up,
        'mode': mode,
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
