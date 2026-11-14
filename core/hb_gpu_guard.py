"""HB manages the GPU model server (owner 14 Nov 2026: "HB should actually be managing system resources ... this is preventing actual work").

The card's compute ring times out now and then (kernel: "ring comp timeout ... reset"). The card recovers; APEX's model server does not - every
answer then fails with ErrorDeviceLost until it is restarted. tick(): when an APEX request failed that way, HB restarts the model server (at most
once per RESTART_GAP_S), proves it answers with a real test answer, says so in main chat, and gives the interrupted tasks another go.
Service and address come from the environment (HB_GPU_SERVICE, HB_GPU_URL), not from code."""
import json
import os
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
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2834,'hummingbird','user',?,'response',0)", (text,))
    if ok:
        from core import hb_commands
        for tid in tasks:
            try:
                hb_commands.handle(conn, 2834, f'/continue {tid}', 'HB GPU guard')
            except Exception:
                pass
    return text
