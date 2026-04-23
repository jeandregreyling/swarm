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
    out = []
    for hwmon in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
        for pwm in sorted(glob.glob(os.path.join(hwmon, 'pwm[0-9]'))):
            enable = pwm + '_enable'
            if os.path.exists(enable):
                out.append((pwm, enable))
    return out


def _apply_mode(mode: str) -> dict:
    applied = []
    if mode == 'auto':
        if _write_platform_profile('balanced'):
            applied.append('platform_profile=balanced')
        # Release any pwm overrides (enable=2 = automatic on most hwmon).
        for pwm, enable in _pwm_paths():
            try:
                with open(enable, 'w') as f:
                    f.write('2')
                applied.append(f'{enable}=2')
            except OSError:
                pass
        STATE['mode'] = 'auto'
    elif mode == 'boost':
        if _write_platform_profile('performance'):
            applied.append('platform_profile=performance')
        for pwm, enable in _pwm_paths():
            try:
                with open(enable, 'w') as f:
                    f.write('1')
                with open(pwm, 'w') as f:
                    f.write('255')
                applied.append(f'{pwm}=255')
            except OSError:
                pass
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
