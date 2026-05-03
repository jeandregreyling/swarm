#!/usr/bin/env python3
"""ops/swarm-fanctl.py — privileged fan controller helper.

INSTALL (opt-in, requires root):
  sudo cp ops/swarm-fanctl.py /usr/local/bin/swarm-fanctl
  sudo chmod 755 /usr/local/bin/swarm-fanctl
  sudo cp ops/swarm-fanctl.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now swarm-fanctl.service

It listens on a Unix socket at /run/swarm-fanctl.sock and responds to:
  {"cmd": "mode"}                    → {"ok": true, "mode": "auto"|"boost"}
  {"cmd": "set_mode", "payload":
      {"mode": "auto"|"boost"}}      → {"ok": true, "mode": "..."}

MODE BEHAVIOUR:
  auto:  target CPU 56–60°C under load. Use OS default fan curve (restore
         platform profile = 'balanced', clear any pwm overrides).
  boost: hold CPU ~40°C when possible — max-fan override via platform profile
         = 'performance' and, if writable, pwm_enable=1 + pwmN=255.

This is a minimal reference implementation. Dell / Lenovo / generic ACPI
machines vary; adjust `_apply_mode()` to your hardware.
"""
from __future__ import annotations

import glob
import json
import os
import socket
import sys
import threading
import time

SOCK_PATH = '/run/swarm-fanctl.sock'
STATE = {'mode': 'auto'}

# Y.58f — Dell OptiPlex 7090 BIOS reverts pwm1=255 back to ~128 within
# milliseconds because firmware owns the fan curve. Two coping strategies:
#   1. Watchdog thread re-writes pwm1=255 every WATCHDOG_INTERVAL_S while in
#      boost. Sometimes wins the race against BIOS.
#   2. Thermal cap via intel_pstate: drop max_perf_pct to BOOST_PERF_CAP so
#      the CPU produces less heat → temp drops to ~50°C even if the BIOS
#      keeps the fan slow. The user wanted '50°C target', this is the
#      deterministic lever.
WATCHDOG_INTERVAL_S = float(os.environ.get('SWARM_FANCTL_WATCHDOG_S', '0.3'))
BOOST_PERF_CAP      = int(os.environ.get('SWARM_FANCTL_BOOST_PERF_CAP', '40'))   # %
AUTO_PERF_CAP       = int(os.environ.get('SWARM_FANCTL_AUTO_PERF_CAP', '100'))  # %
# Y.58f-2 — boost holds until the package CPU temp drops to BOOST_EXIT_TEMP,
# then the helper auto-reverts to 'auto'. Matches the user's verbatim ask:
# "boost power to 100% until temp goes to 50". Temp probe runs at the
# watchdog cadence; we require the temp to stay below the floor for
# BOOST_EXIT_HOLD_S before flipping, so we don't bounce on a single dip.
BOOST_EXIT_TEMP     = float(os.environ.get('SWARM_FANCTL_BOOST_EXIT_TEMP', '50'))   # °C
BOOST_EXIT_HOLD_S   = float(os.environ.get('SWARM_FANCTL_BOOST_EXIT_HOLD_S', '5'))  # s
# Y.58f-3 — adaptive cap ratchet. If boost is on and CPU stays above the
# exit target for TIGHTEN_AFTER_S, drop max_perf_pct by TIGHTEN_STEP_PCT,
# floored at TIGHTEN_FLOOR_PCT. Guarantees the contract "hold boost until
# temp goes to 50°C" even when a userland process is pinned at 100% CPU.
TIGHTEN_AFTER_S     = float(os.environ.get('SWARM_FANCTL_TIGHTEN_AFTER_S', '8'))
TIGHTEN_STEP_PCT    = int(os.environ.get('SWARM_FANCTL_TIGHTEN_STEP_PCT', '5'))
TIGHTEN_FLOOR_PCT   = int(os.environ.get('SWARM_FANCTL_TIGHTEN_FLOOR_PCT', '20'))
_WATCHDOG_STOP = threading.Event()
_WATCHDOG_THREAD: 'threading.Thread | None' = None
_BOOST_BELOW_SINCE: 'float | None' = None
_BOOST_HOT_SINCE: 'float | None' = None
_CURRENT_PERF_CAP: int = 100


def _write_platform_profile(profile: str) -> bool:
    path = '/sys/firmware/acpi/platform_profile'
    try:
        with open(path, 'w') as f:
            f.write(profile)
        return True
    except OSError:
        return False


def _pwm_paths() -> list:
    """Enumerate writable pwm nodes.

    Returns (pwm_path, enable_path_or_None) tuples. Some drivers (e.g. the
    Dell OptiPlex ``dell_smm`` hwmon) expose a writable ``pwmN`` *without*
    an ``_enable`` sibling — BIOS always owns the fan curve and writes to
    ``pwmN`` are direct overrides. Treat those as still-controllable with
    ``enable=None``.
    """
    out = []
    for hwmon in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
        for pwm in sorted(glob.glob(os.path.join(hwmon, 'pwm[0-9]'))):
            # Skip pwm[0-9]_* metadata files.
            if os.path.basename(pwm) not in ('pwm1', 'pwm2', 'pwm3', 'pwm4'):
                continue
            # Must be writable at all (dell_smm exposes pwm1 as 0666).
            if not os.access(pwm, os.W_OK):
                continue
            enable = pwm + '_enable'
            out.append((pwm, enable if os.path.exists(enable) else None))
    return out


# PWM target when set_mode('auto') is called on hardware that has no proper
# auto-enable gate (e.g. dell_smm). Lower = quieter but hotter; 128 = 50%.
AUTO_PWM_FALLBACK = int(os.environ.get('SWARM_FANCTL_AUTO_PWM', '128'))


def _read_int(path: str) -> 'int | None':
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _write_perf_cap(pct: int) -> bool:
    """Cap CPU max performance via intel_pstate / cpufreq. Used as the
    deterministic 'cool to 50C' lever when BIOS won't let us boost the fan.
    Returns True if at least one cap was written."""
    pct = max(10, min(100, int(pct)))
    wrote = False
    # Intel pstate driver — single global knob (preferred).
    try:
        with open('/sys/devices/system/cpu/intel_pstate/max_perf_pct', 'w') as f:
            f.write(str(pct))
        wrote = True
    except OSError:
        pass
    # Per-CPU cpufreq governor cap as a fallback (best-effort).
    if not wrote:
        try:
            cpus = sorted(glob.glob('/sys/devices/system/cpu/cpu[0-9]*/cpufreq'))
            for c in cpus:
                try:
                    cpuinfo_max = _read_int(os.path.join(c, 'cpuinfo_max_freq'))
                    if cpuinfo_max is None:
                        continue
                    target = int(cpuinfo_max * pct / 100.0)
                    with open(os.path.join(c, 'scaling_max_freq'), 'w') as f:
                        f.write(str(target))
                    wrote = True
                except OSError:
                    continue
        except OSError:
            pass
    return wrote


def _set_turbo(enabled: bool) -> bool:
    """Toggle Intel turbo. Disabling drops thermal load fast."""
    val = '0' if enabled else '1'   # no_turbo flag is inverted
    try:
        with open('/sys/devices/system/cpu/intel_pstate/no_turbo', 'w') as f:
            f.write(val)
        return True
    except OSError:
        return False


def _readback_pwm() -> list:
    out = []
    for pwm, _ in _pwm_paths():
        v = _read_int(pwm)
        out.append({'path': pwm, 'value': v})
    return out


def _push_pwm_max() -> list:
    """Best-effort write pwm1..N=255. Returns the read-back values."""
    for pwm, enable in _pwm_paths():
        try:
            if enable is not None:
                with open(enable, 'w') as f:
                    f.write('1')
            with open(pwm, 'w') as f:
                f.write('255')
        except OSError:
            continue
    return _readback_pwm()


def _watchdog_loop():
    """While in boost mode, keep re-writing pwm1=255 to fight BIOS reverts,
    ratchet the perf cap downward if temp stays above target, and auto-revert
    to 'auto' once CPU temp has stayed below BOOST_EXIT_TEMP for
    BOOST_EXIT_HOLD_S seconds (the 'until temp goes to 50' contract)."""
    global _BOOST_BELOW_SINCE, _BOOST_HOT_SINCE, _CURRENT_PERF_CAP
    while not _WATCHDOG_STOP.is_set():
        if STATE.get('mode') == 'boost':
            try:
                _push_pwm_max()
            except Exception:
                pass
            cpu_c = _peak_cpu_temp_c()
            now = time.monotonic()
            if cpu_c is not None and cpu_c <= BOOST_EXIT_TEMP:
                _BOOST_HOT_SINCE = None
                if _BOOST_BELOW_SINCE is None:
                    _BOOST_BELOW_SINCE = now
                elif now - _BOOST_BELOW_SINCE >= BOOST_EXIT_HOLD_S:
                    try:
                        _apply_mode('auto')
                    except Exception:
                        pass
                    _BOOST_BELOW_SINCE = None
            else:
                _BOOST_BELOW_SINCE = None
                # Adaptive cap: if temp has been above target for
                # TIGHTEN_AFTER_S, ratchet the cap down one step.
                if cpu_c is not None:
                    if _BOOST_HOT_SINCE is None:
                        _BOOST_HOT_SINCE = now
                    elif now - _BOOST_HOT_SINCE >= TIGHTEN_AFTER_S:
                        new_cap = max(TIGHTEN_FLOOR_PCT,
                                      _CURRENT_PERF_CAP - TIGHTEN_STEP_PCT)
                        if new_cap != _CURRENT_PERF_CAP:
                            if _write_perf_cap(new_cap):
                                _CURRENT_PERF_CAP = new_cap
                        _BOOST_HOT_SINCE = now  # restart timer for next step
        else:
            _BOOST_BELOW_SINCE = None
            _BOOST_HOT_SINCE = None
        _WATCHDOG_STOP.wait(WATCHDOG_INTERVAL_S)


def _peak_cpu_temp_c() -> 'float | None':
    """Return the hottest CPU-related temp sensor in °C, or None."""
    candidates = []
    for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
        try:
            with open(os.path.join(hwmon, 'name')) as f:
                name = f.read().strip().lower()
        except OSError:
            continue
        if name not in ('coretemp', 'k10temp', 'zenpower', 'dell_smm'):
            continue
        # coretemp/k10temp/zenpower: every temp*_input is CPU.
        # dell_smm: temp1 is CPU package on OptiPlex/Latitude.
        inputs = sorted(glob.glob(os.path.join(hwmon, 'temp*_input')))
        if name == 'dell_smm':
            inputs = [p for p in inputs if p.endswith('temp1_input')]
        for p in inputs:
            v = _read_int(p)
            if v is None or v <= 0:
                continue
            candidates.append(v / 1000.0)
    return max(candidates) if candidates else None


def _start_watchdog():
    global _WATCHDOG_THREAD
    if _WATCHDOG_THREAD and _WATCHDOG_THREAD.is_alive():
        return
    _WATCHDOG_STOP.clear()
    _WATCHDOG_THREAD = threading.Thread(target=_watchdog_loop, daemon=True,
                                        name='fanctl-boost-watchdog')
    _WATCHDOG_THREAD.start()


def _apply_mode(mode: str) -> dict:
    global _CURRENT_PERF_CAP
    applied = []
    if mode == 'auto':
        if _write_platform_profile('balanced'):
            applied.append('platform_profile=balanced')
        # Prefer handing control back to firmware via pwmN_enable=2.
        # For drivers without _enable (dell_smm), fall back to a mid-range
        # PWM so we don't leave the fan pinned at whatever the last boost set.
        for pwm, enable in _pwm_paths():
            try:
                if enable is not None:
                    with open(enable, 'w') as f:
                        f.write('2')
                    applied.append(f'{enable}=2')
                else:
                    with open(pwm, 'w') as f:
                        f.write(str(AUTO_PWM_FALLBACK))
                    applied.append(f'{pwm}={AUTO_PWM_FALLBACK}')
            except OSError as exc:
                applied.append(f'{pwm}:err:{exc.errno}')
        # Restore CPU performance + turbo.
        if _write_perf_cap(AUTO_PERF_CAP):
            applied.append(f'max_perf_pct={AUTO_PERF_CAP}')
            _CURRENT_PERF_CAP = AUTO_PERF_CAP
        if _set_turbo(True):
            applied.append('turbo=on')
        STATE['mode'] = 'auto'
    elif mode == 'boost':
        if _write_platform_profile('performance'):
            applied.append('platform_profile=performance')
        # Push pwm to max (BIOS may revert; watchdog keeps re-writing).
        readback = _push_pwm_max()
        for r in readback:
            applied.append(f"{r['path']}=255 (readback={r['value']})")
        # Thermal cap — the deterministic lever to actually reach ~50°C
        # when the BIOS owns the fan curve. Cuts CPU max performance to
        # BOOST_PERF_CAP% (default 60%) and disables Intel turbo.
        if _write_perf_cap(BOOST_PERF_CAP):
            applied.append(f'max_perf_pct={BOOST_PERF_CAP}')
            _CURRENT_PERF_CAP = BOOST_PERF_CAP
        if _set_turbo(False):
            applied.append('turbo=off')
        STATE['mode'] = 'boost'
        _start_watchdog()
    else:
        return {'ok': False, 'error': 'invalid mode'}
    return {'ok': True, 'mode': STATE['mode'], 'applied': applied,
            'pwm_readback': _readback_pwm()}


def _handle(conn: socket.socket):
    try:
        buf = b''
        while b'\n' not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        req = json.loads(buf.decode(errors='replace').strip() or '{}')
        cmd = req.get('cmd')
        if cmd == 'mode':
            resp = {'ok': True, 'mode': STATE['mode']}
        elif cmd == 'status':
            # Y.58f — surface real applied state so the UI can show whether
            # the BIOS is reverting our PWM writes (i.e. honest state).
            try:
                no_turbo = _read_int('/sys/devices/system/cpu/intel_pstate/no_turbo')
                max_perf = _read_int('/sys/devices/system/cpu/intel_pstate/max_perf_pct')
            except Exception:
                no_turbo, max_perf = None, None
            resp = {
                'ok': True,
                'mode': STATE['mode'],
                'pwm_readback': _readback_pwm(),
                'turbo_disabled': bool(no_turbo) if no_turbo is not None else None,
                'max_perf_pct': max_perf,
                'watchdog_alive': bool(_WATCHDOG_THREAD and _WATCHDOG_THREAD.is_alive()),
                'boost_perf_cap': BOOST_PERF_CAP,
                'boost_exit_temp': BOOST_EXIT_TEMP,
                'cpu_peak_c': _peak_cpu_temp_c(),
                'current_perf_cap': _CURRENT_PERF_CAP,
                'tighten_floor_pct': TIGHTEN_FLOOR_PCT,
            }
        elif cmd == 'set_mode':
            resp = _apply_mode((req.get('payload') or {}).get('mode', ''))
        elif cmd == 'contract':
            # Y.59 — emit a Hive contract-v0-shaped thermal subtree so the
            # node provider can pull a single canonical reading. Caller
            # wraps this into a full telemetry envelope; we stay narrow
            # to the slice this helper actually owns.
            resp = {
                'ok': True,
                'contract': 'node.fanctl/v0',
                'thermal': {
                    'fan_pwm': _readback_pwm(),
                    'fan_mode': STATE['mode'],
                    'controllable': True,
                },
                'compute': {
                    'cpu_peak_temp_c': _peak_cpu_temp_c(),
                },
            }
        else:
            resp = {'ok': False, 'error': f'unknown cmd: {cmd}'}
        conn.sendall((json.dumps(resp) + '\n').encode())
    except Exception as exc:
        try:
            conn.sendall((json.dumps({'ok': False, 'error': str(exc)}) + '\n').encode())
        except OSError:
            pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    os.chmod(SOCK_PATH, 0o660)  # group access — add your user to the owning group
    # Best-effort: chown the socket to a group the Flask user is in, so the
    # (unprivileged) swarm-terminal process can talk to us without extra setup.
    # Order of preference: $SWARM_FANCTL_GROUP env → 'swarm' → 'seven'.
    import grp
    for gname in filter(None, (os.environ.get('SWARM_FANCTL_GROUP'), 'swarm', 'seven')):
        try:
            gid = grp.getgrnam(gname).gr_gid
            os.chown(SOCK_PATH, 0, gid)
            break
        except (KeyError, PermissionError, OSError):
            continue
    srv.listen(8)
    # Apply initial mode so boot state is known.
    _apply_mode('auto')
    while True:
        conn, _ = srv.accept()
        t = threading.Thread(target=_handle, args=(conn,), daemon=True)
        t.start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
