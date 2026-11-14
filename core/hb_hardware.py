"""Truthful hardware view for the sundial: GPU (amdgpu sysfs, nvidia-smi fallback) and every running
local model server with its real VRAM / RAM, plus the owner switch for the APEX systemd service.

Readings come from the kernel, not from model registries:
  * GPU: /sys/class/drm/card*/device/{mem_info_vram_used, mem_info_vram_total, gpu_busy_percent}
  * per-process VRAM: /proc/<pid>/fdinfo/* "drm-memory-vram", counted once per drm-client-id
  * per-process RAM: VmRSS
"""
import os
import re
import subprocess
import threading
import time

SERVICE_UNITS = {'apex-server': 'apex-server.service'}    # owner-switchable model services (systemd --user)
SERVICE_PORTS = {'8080': 'apex-server'}


def _read(path, default=None):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return default


def gpu_stats(root='/sys/class/drm'):
    """{'vram_used_gb','vram_total_gb','vram_percent','busy_percent','source'} or all None."""
    best = None
    for card in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        dev = os.path.join(root, card, 'device')
        total = _read(os.path.join(dev, 'mem_info_vram_total'))
        used = _read(os.path.join(dev, 'mem_info_vram_used'))
        if not (total and used and total.isdigit() and used.isdigit()) or int(total) == 0:
            continue
        busy = _read(os.path.join(dev, 'gpu_busy_percent'))
        item = {'vram_used_gb': round(int(used) / 2**30, 2), 'vram_total_gb': round(int(total) / 2**30, 2),
                'vram_percent': round(int(used) * 100 / int(total), 1),
                'busy_percent': int(busy) if busy and busy.isdigit() else None, 'source': 'amdgpu sysfs'}
        if best is None or item['vram_total_gb'] > best['vram_total_gb']:
            best = item
    if best:
        return best
    try:
        nv = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=3)
        if nv.returncode == 0 and nv.stdout.strip():
            used, total, busy = [float(x) for x in nv.stdout.strip().splitlines()[0].split(',')]
            return {'vram_used_gb': round(used / 1024, 2), 'vram_total_gb': round(total / 1024, 2),
                    'vram_percent': round(used * 100 / total, 1) if total else 0, 'busy_percent': int(busy), 'source': 'nvidia-smi'}
    except Exception:
        pass
    return {'vram_used_gb': None, 'vram_total_gb': None, 'vram_percent': None, 'busy_percent': None, 'source': None}


def _process_vram_gb(pid, proc='/proc'):
    by_client = {}
    fdinfo = os.path.join(proc, str(pid), 'fdinfo')
    try:
        fds = os.listdir(fdinfo)
    except OSError:
        return 0.0
    for fd in fds:
        text = _read(os.path.join(fdinfo, fd), '')
        if 'drm-memory-vram' not in text:
            continue
        cid = re.search(r'drm-client-id:\s*(\d+)', text)
        kib = re.search(r'drm-memory-vram:\s*(\d+)', text)
        if kib:
            key = cid.group(1) if cid else fd
            by_client[key] = max(by_client.get(key, 0), int(kib.group(1)))
    return round(sum(by_client.values()) / 2**20, 2)


def model_processes(proc='/proc'):
    """Every running llama-server of any kind, with its real placement."""
    out = []
    for entry in os.listdir(proc):
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join(proc, entry, 'cmdline'), 'rb') as fh:
                argv = [a.decode('utf-8', 'replace') for a in fh.read().split(b'\0') if a]
        except OSError:
            continue
        if not argv or os.path.basename(argv[0]) != 'llama-server':
            continue

        def opt(name):
            return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None
        alias, port = opt('--alias'), opt('--port')
        unit = SERVICE_PORTS.get(port) if not alias else None
        status = _read(os.path.join(proc, entry, 'status'), '')
        rss = re.search(r'VmRSS:\s*(\d+)', status)
        vram = _process_vram_gb(entry, proc)
        out.append({'pid': int(entry), 'model': alias or (unit or f'llama-server:{port}'), 'port': int(port) if port and port.isdigit() else None,
                    'vram_gb': vram, 'ram_gb': round(int(rss.group(1)) / 2**20, 2) if rss else None,
                    'placement': 'gpu' if vram >= 0.1 else 'ram', 'kind': 'service' if unit else 'managed', 'unit': unit,
                    'model_file': os.path.basename(opt('-m') or opt('--model') or '')[:24]})
    return sorted(out, key=lambda item: (-item['vram_gb'], item['model']))


def _user_env():
    uid = os.getuid()
    env = dict(os.environ)
    env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{uid}')
    env.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path=/run/user/{uid}/bus')
    return env


def service_state(name):
    unit = SERVICE_UNITS.get(name)
    if not unit:
        return None
    try:
        r = subprocess.run(['systemctl', '--user', 'is-active', unit], capture_output=True, text=True, timeout=5, env=_user_env())
        return r.stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def service_action(name, action):
    """Owner switch for a whitelisted model service: 'stop' or 'start'. Returns the new state."""
    unit = SERVICE_UNITS.get(name)
    if not unit or action not in ('stop', 'start'):
        raise ValueError('Unknown model service or action')
    r = subprocess.run(['systemctl', '--user', action, unit], capture_output=True, text=True, timeout=60, env=_user_env())
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or 'systemctl failed').strip()[:300])
    return service_state(name)


# ------------------------------------------------------------------ HB housekeeping (B38)
_HK_LOCK = threading.Lock()
_HK_LAST = [0.0]
HOUSEKEEP_EVERY_S = 60


def housekeeping_log(conn, limit=5):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_housekeeping(ts REAL, model TEXT, pid INTEGER, reason TEXT)')
    return [dict(zip(('ts', 'model', 'pid', 'reason'), r)) for r in
            conn.execute('SELECT ts, model, pid, reason FROM hb_housekeeping ORDER BY ts DESC LIMIT ?', (limit,))]


def housekeeping_tick(now=None, housekeep=None):
    """Called by the HB coordinator; runs the model housekeeping at most once a minute, in its own thread
    (a model load can hold the launcher lock, and the coordinator must never wait for it)."""
    now = time.time() if now is None else now
    if now - _HK_LAST[0] < HOUSEKEEP_EVERY_S or not _HK_LOCK.acquire(blocking=False):
        return False
    _HK_LAST[0] = now

    def work():
        try:
            if housekeep is None:
                from core.seven_llm.llama_server import housekeep as run
            else:
                run = housekeep
            result = run()
            if result.get('stopped'):
                from contextlib import closing
                from utils.db._connection import get_connection
                with closing(get_connection()) as conn, conn:
                    housekeeping_log(conn, 1)
                    conn.executemany('INSERT INTO hb_housekeeping VALUES(?,?,?,?)',
                                     [(time.time(), s['model'], s['pid'], s['reason']) for s in result['stopped']])
        except Exception:
            import logging
            logging.getLogger('hb.housekeeping').exception('model housekeeping failed')
        finally:
            _HK_LOCK.release()
    threading.Thread(target=work, name='hb-housekeeping', daemon=True).start()
    return True
