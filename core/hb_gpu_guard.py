"""HB manages the GPU model server (owner 14 Nov 2026: "HB should actually be managing system resources ... this is preventing actual work").

The card's compute ring times out now and then (kernel: "ring comp timeout ... reset"). The card recovers; APEX's model server does not - every
answer then fails with ErrorDeviceLost until it is restarted. tick(): when an APEX request failed that way, HB restarts the model server (at most
once per RESTART_GAP_S), proves it answers with a real test answer, says so in main chat, and gives the interrupted tasks another go.
Service and address come from the environment (HB_GPU_SERVICE, HB_GPU_URL), not from code."""
import json
import os
import re
import subprocess
import time
import urllib.request

RESTART_GAP_S = 300
SERVICE = os.environ.get('HB_GPU_SERVICE', 'apex-server')
URL = os.environ.get('HB_GPU_URL', 'http://127.0.0.1:8080')
SIGN = '%ErrorDeviceLost%'


def _restart():
    uid = os.getuid()
    env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{uid}', 'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{uid}/bus'}
    return subprocess.run(['systemctl', '--user', 'restart', SERVICE], env=env, capture_output=True, timeout=120).returncode == 0


def _answers():
    for _ in range(60):
        try:
            with urllib.request.urlopen(URL + '/health', timeout=2) as r:
                if json.loads(r.read()).get('status') == 'ok':
                    break
        except Exception:
            time.sleep(2)
    try:
        body = json.dumps({'prompt': 'Say OK.', 'n_predict': 4}).encode()
        with urllib.request.urlopen(urllib.request.Request(URL + '/completion', body, {'Content-Type': 'application/json'}), timeout=60) as r:
            return bool(json.loads(r.read()).get('content'))
    except Exception:
        return False


def tick(conn, now=None, restart=_restart, answers=_answers, say=None):
    now = now or time.time()
    conn.execute('CREATE TABLE IF NOT EXISTS hb_gpu_guard(at REAL, failed TEXT, ok INTEGER)')
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_peer_work'").fetchone():
        return None
    last = conn.execute('SELECT MAX(at) FROM hb_gpu_guard').fetchone()[0]
    if last and now - last < RESTART_GAP_S:
        return None
    failed = [r[0] for r in conn.execute("SELECT request_id FROM hb_peer_work WHERE state='failed' AND stage LIKE ? AND updated_at>?",
                                         (SIGN, last or now - 900)).fetchall()]
    if not failed:
        return None
    ok = bool(restart() and answers())
    conn.execute('INSERT INTO hb_gpu_guard(at, failed, ok) VALUES (?,?,?)', (now, json.dumps(failed), int(ok)))
    tasks = []
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_task_requests'").fetchone():
        tasks = sorted({r[0] for r in conn.execute(f"SELECT task_id FROM hb_task_requests WHERE request_id IN ({','.join('?' * len(failed))})",
                                                   failed).fetchall()})
    text = (f"↺ HB restarted the GPU model server ({SERVICE}): the card had reset and APEX's answers failed with ErrorDeviceLost "
            f"({len(failed)} request(s)). " + ("A test answer works again; " + (f"{len(tasks)} interrupted task(s) get another go." if tasks else 'nothing was waiting.')
                                              if ok else "It does not answer yet; HB tries again in 5 minutes."))
    if say:
        say(text)
    else:
        from core.hb_chat import owner_chat   # Practice 105
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)", (owner_chat(conn), text))
    if ok:
        from core import hb_commands
        for tid in tasks:
            try:
                hb_commands.handle(conn, __import__('core.hb_chat', fromlist=['owner_chat']).owner_chat(conn), f'/continue {tid}', 'HB GPU guard')
            except Exception:
                pass
    return text


# Practice 133 (owner 17 Nov 2026: "keep letting apex do it, it needs to know how to use the system anyway"). APEX ran at 14 tokens/s and
# its turns timed out: at boot llama.cpp --fit sized the window (115k tokens) to ALL free VRAM; VS Code and the desktop grew later and
# 2.6 GB of APEX's buffers moved to system RAM (amdgpu GTT), which the card reads slowly. spill_tick(): when the model server has spilled,
# HB raises the --fit margin (-fitt, MiB kept free) in its own drop-in (a copy of the old one is kept), restarts it while it is idle,
# proves it answers, and says so in main chat. The window stays automatic, just smaller. One step per SPILL_GAP_S, margin capped.
# Practice 135 (17 Nov 2026): healthy APEX keeps ~1.4-1.5 GB of host buffers in GTT all the time; the broken state had 2.5-2.6 GB.
# 0.5 GB raised the margin again at 13:37 on a healthy 1.43 GB, the window fell to 16,384 tokens and a research turn ran out of room.
SPILL_GB = 2.0
SPILL_GAP_S = 1800
MARGIN_START_MIB, MARGIN_STEP_MIB, MARGIN_MAX_MIB = 1536, 512, 4096
PORT = URL.rsplit(':', 1)[-1].strip('/')


def dropin():
    from pathlib import Path
    return Path(os.environ.get('HB_GPU_DROPIN') or Path.home() / '.config/systemd/user' / f'{SERVICE}.service.d' / 'gpu-offload.conf')


def margin(text):
    m = re.search(r'(?:-fitt|--fit-target)\s+(\d+)', text)
    return int(m.group(1)) if m else None


def with_margin(text, mib):
    """The drop-in with the --fit margin set to mib; None when it does not use --fit."""
    if re.search(r'(?:-fitt|--fit-target)\s+\d+', text):
        return re.sub(r'((?:-fitt|--fit-target)\s+)\d+', lambda m: m.group(1) + str(mib), text, count=1)
    if '--fit on' not in text:
        return None
    return text.replace('--fit on', f'--fit on -fitt {mib}', 1)


def _idle():
    try:
        with urllib.request.urlopen(URL + '/slots', timeout=3) as r:
            return not any(s.get('is_processing') for s in json.loads(r.read()))
    except Exception:
        return True


def _reload():
    uid = os.getuid()
    env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{uid}', 'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{uid}/bus'}
    return subprocess.run(['systemctl', '--user', 'daemon-reload'], env=env, capture_output=True, timeout=60).returncode == 0


def spill_tick(conn, now=None, procs=None, path=None, idle=_idle, reload=_reload, restart=_restart, answers=_answers, say=None):
    now = now or time.time()
    conn.execute('CREATE TABLE IF NOT EXISTS hb_gpu_spill(at REAL, spilled_gb REAL, margin_from INTEGER, margin_to INTEGER, ok INTEGER)')
    last = conn.execute('SELECT MAX(at) FROM hb_gpu_spill').fetchone()[0]
    if last and now - last < SPILL_GAP_S:
        return None
    # Practice 135: a raise made on less than SPILL_GB was a false alarm (APEX's normal ~1.45 GB) - put the previous settings back once.
    path = path or dropin()
    prev = conn.execute('SELECT spilled_gb, margin_from, margin_to FROM hb_gpu_spill ORDER BY at DESC LIMIT 1').fetchone()
    before = path.with_name(path.name + '.before-hb')
    if (prev and prev[1] is not None and prev[2] is not None and prev[2] > prev[1] and prev[0] < SPILL_GB and before.exists()
            and margin(before.read_text()) == prev[1] and idle()):
        path.write_text(before.read_text())
        ok = bool(reload() and restart() and answers())
        conn.execute('INSERT INTO hb_gpu_spill VALUES (?,?,?,?,?)', (now, 0.0, prev[2], prev[1], int(ok)))
        line = (f"↺ HB undid its last GPU change: the {prev[0]} GB it saw outside the GPU is APEX's normal level, not a spill, and the "
                f"bigger margin had shrunk APEX's window so far that research answers ran out of room. Margin back to {prev[1]} MiB."
                + (' A test answer works.' if ok else ' It does not answer yet; the ErrorDeviceLost guard keeps watching.'))
        if say:
            say(line)
        else:
            from core.hb_chat import owner_chat
            conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                         (owner_chat(conn), line))
        return line
    if procs is None:
        from core.hb_hardware import model_processes
        procs = model_processes()
    server = next((p for p in procs if str(p.get('port')) == PORT and p.get('placement') == 'gpu'), None)
    if not server or server.get('spilled_gb', 0) < SPILL_GB or not idle():
        return None
    path = path or dropin()
    try:
        text = path.read_text()
    except OSError:
        return None
    old = margin(text)
    new = MARGIN_START_MIB if old is None or old < MARGIN_START_MIB else min(old + MARGIN_STEP_MIB, MARGIN_MAX_MIB)
    changed = with_margin(text, new)
    if changed is None or new == old:
        conn.execute('INSERT INTO hb_gpu_spill VALUES (?,?,?,?,0)', (now, server['spilled_gb'], old, old))
        line = (f"⚠ APEX's model server has {server['spilled_gb']} GB outside the GPU (in system RAM), so it runs slowly, and HB cannot "
                f"leave more room by itself ({'its margin is already ' + str(old) + ' MiB' if old else 'its settings do not use --fit'}). "
                "Closing other GPU programs or a smaller model would help.")
    else:
        path.with_name(path.name + '.before-hb').write_text(text)
        path.write_text(changed)
        ok = bool(reload() and restart() and answers())
        conn.execute('INSERT INTO hb_gpu_spill VALUES (?,?,?,?,?)', (now, server['spilled_gb'], old, new, int(ok)))
        line = (f"↺ HB restarted APEX's model server: {server['spilled_gb']} GB of it had moved out of the GPU into system RAM (the desktop "
                f"and VS Code took GPU memory after it started), which made APEX slow and its turns time out. It now keeps {new} MiB of GPU "
                f"memory free{' (was ' + str(old) + ')' if old else ''}; its window stays automatic, just smaller. "
                + ('A test answer works.' if ok else 'It does not answer yet; the ErrorDeviceLost guard keeps watching.')
                + f' Old settings kept in {path.name}.before-hb.')
    if say:
        say(line)
    else:
        from core.hb_chat import owner_chat
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (owner_chat(conn), line))
    return line


# Practice 158 (owner 18 Nov 2026): at 13:36:56 the card reset during a research turn (kernel: "ring comp_1.0.1 reset ... device wedged,
# but recovered through reset"). APEX's server kept saying /health ok but answered nothing until JD restarted it by hand: tick() only
# reacts to failed background-worker requests, and this failure came through another path. reset_tick() reads the kernel log itself;
# after a reset it waits until APEX is idle, asks for a test answer, and restarts the server only when that fails.
RESET_SIGN = re.compile(r'ring reset|ring \S+ reset|device wedged|ErrorDeviceLost|GPU reset', re.I)
RESET_CHECK_S = 60


def _kernel_resets(since):
    try:
        out = subprocess.run(['journalctl', '-k', '--since', '@%d' % int(since), '--no-pager', '-o', 'cat'],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    return [line for line in out.splitlines() if RESET_SIGN.search(line)]


def reset_tick(conn, now=None, resets=_kernel_resets, idle=None, answers=None, restart=None, say=None):
    """Returns what HB did after a card reset, or None."""
    now = now or time.time()
    idle, answers, restart = idle or _idle, answers or _answers, restart or _restart
    conn.execute('CREATE TABLE IF NOT EXISTS hb_gpu_reset_watch(at REAL, resets INTEGER, answered INTEGER, restarted INTEGER, ok INTEGER)')
    last = conn.execute('SELECT MAX(at) FROM hb_gpu_reset_watch').fetchone()[0] or now - 900
    if now - last < RESET_CHECK_S:
        return None
    lines = resets(last)
    if not lines:
        conn.execute('INSERT INTO hb_gpu_reset_watch VALUES (?,?,?,?,?)', (now, 0, None, 0, None))
        conn.execute('DELETE FROM hb_gpu_reset_watch WHERE resets=0 AND at < ?', (now - 3600,))
        return None
    if not idle():
        return None                              # checked again next tick, from the same point in the log
    if answers():
        conn.execute('INSERT INTO hb_gpu_reset_watch VALUES (?,?,?,?,?)', (now, len(lines), 1, 0, 1))
        return None
    ok = bool(restart() and answers())
    conn.execute('INSERT INTO hb_gpu_reset_watch VALUES (?,?,?,?,?)', (now, len(lines), 0, 1, int(ok)))
    text = (f"↺ HB restarted the GPU model server ({SERVICE}): the card reset ({len(lines)} kernel message(s)) and APEX stopped answering. "
            + ('A test answer works again.' if ok else 'It does not answer yet; HB checks again in a minute.'))
    if say:
        say(text)
    else:
        from core.hb_chat import owner_chat
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",
                     (owner_chat(conn), text))
    return text

