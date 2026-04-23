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


def _apply_mode(mode: str) -> dict:
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
        STATE['mode'] = 'auto'
    elif mode == 'boost':
        if _write_platform_profile('performance'):
            applied.append('platform_profile=performance')
        for pwm, enable in _pwm_paths():
            try:
                if enable is not None:
                    with open(enable, 'w') as f:
                        f.write('1')
                with open(pwm, 'w') as f:
                    f.write('255')
                applied.append(f'{pwm}=255')
            except OSError as exc:
                applied.append(f'{pwm}:err:{exc.errno}')
        STATE['mode'] = 'boost'
    else:
        return {'ok': False, 'error': 'invalid mode'}
    return {'ok': True, 'mode': STATE['mode'], 'applied': applied}


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
        elif cmd == 'set_mode':
            resp = _apply_mode((req.get('payload') or {}).get('mode', ''))
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
