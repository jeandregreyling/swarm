"""Nanny bot: a small local model in RAM (CPU) that looks after the system ("the kids").

Owner decisions 12 Nov: it lives in RAM, not on the GPU; it replaces scripts/hummingbird_nanny.py.

* HB gathers facts deterministically (hardware, models, queue, workers, tasks, DOES, DB).
* Fixed rules turn facts into findings; each finding carries the owner command that fixes it.
* The small CPU model (seven-direct:daily = Llama 3.2 3B, --n-gpu-layers 0) only writes the
  short plain-English note; if it is slow or unavailable HB writes the note itself.
* The bot never acts on its own: it posts in main chat (only when findings change) and the
  owner clicks the command. Off until the owner turns it on: /nanny on [minutes].
* Runs in its own thread so a slow model can never delay HB's coordinator loop.
"""
import hashlib
import json
import os
import re
import threading
import time
from contextlib import closing

NANNY_MODEL = 'seven-direct:daily'
DEFAULT_INTERVAL = 600
REPOST_AFTER = 3600            # same findings are repeated at most hourly
_RUNNING = threading.Lock()


def ensure_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS hb_nanny(id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,'
                 ' interval_s INTEGER NOT NULL DEFAULT 600, last_run REAL, last_hash TEXT, last_post REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hb_nanny_reports(id INTEGER PRIMARY KEY, created_at REAL, findings TEXT, note TEXT,'
                 ' note_source TEXT, message_id INTEGER)')


def settings(conn):
    ensure_schema(conn)
    row = conn.execute('SELECT enabled, interval_s, last_run, last_hash, last_post FROM hb_nanny WHERE id=1').fetchone()
    if not row:
        return {'enabled': False, 'interval_s': DEFAULT_INTERVAL, 'last_run': None, 'last_hash': None, 'last_post': None}
    return dict(zip(('enabled', 'interval_s', 'last_run', 'last_hash', 'last_post'), (bool(row[0]), *row[1:])))


def configure(conn, enabled, minutes=None):
    ensure_schema(conn)
    interval = int(minutes) * 60 if minutes else settings(conn)['interval_s']
    if interval < 120:
        raise ValueError('The nanny checks at most every 2 minutes')
    conn.execute('INSERT INTO hb_nanny(id, enabled, interval_s) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET '
                 'enabled=excluded.enabled, interval_s=excluded.interval_s', (int(bool(enabled)), interval))
    return settings(conn)


# ------------------------------------------------------------------ facts
def _meminfo():
    out = {}
    try:
        with open('/proc/meminfo') as fh:
            for line in fh:
                key, value = line.split(':', 1)
                out[key] = int(value.split()[0]) / 2**20          # GB
    except OSError:
        pass
    return out


def facts(conn, now=None):
    now = time.time() if now is None else now
    from core.hb_hardware import gpu_stats, model_processes
    mem = _meminfo()
    f = {'gpu': gpu_stats(),
         'ram': {'total_gb': round(mem.get('MemTotal', 0), 1), 'available_gb': round(mem.get('MemAvailable', 0), 1),
                 'swap_total_gb': round(mem.get('SwapTotal', 0), 1)},
         'models': [], 'queue': {}, 'workers_down': [], 'spinning': [], 'needs_owner': [], 'kc_lag': 0, 'db_gb': None}
    try:
        from core.seven_llm.llama_server import STATE_PATH
        with open(STATE_PATH) as fh:
            state = json.load(fh)
    except Exception:
        state = {}
    for p in model_processes():
        last = (state.get(p['model']) or {}).get('last_used')
        f['models'].append({**{k: p[k] for k in ('model', 'kind', 'vram_gb', 'ram_gb', 'placement')},
                            'idle_min': round((now - last) / 60) if last else None})
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'hb_peer_work' in tables:
        row = conn.execute("SELECT COUNT(*), MIN(updated_at) FROM hb_peer_work WHERE state='queued'").fetchone()
        f['queue'] = {'queued': row[0], 'oldest_hours': round((now - row[1]) / 3600, 1) if row[1] else None,
                      'running': conn.execute("SELECT COUNT(*) FROM hb_peer_work WHERE state='running'").fetchone()[0]}
    if 'hb_peer_workers' in tables:
        f['workers_down'] = [r[0] for r in conn.execute("SELECT principal FROM hb_peer_workers WHERE state<>'running'")]
    if 'hb_task_manager' in tables:
        from core.hb_task_manager import stuck_reason
        for tid, state_ in conn.execute("SELECT task_id, state FROM hb_task_manager WHERE enabled=1"):
            reason = stuck_reason(conn, tid)
            if reason:
                f['spinning'].append({'task_id': tid, 'reason': reason})
            elif state_ == 'needs_owner':
                f['needs_owner'].append(tid)
    if 'hb_kc_index' in tables and 'messages' in tables:
        indexed = conn.execute("SELECT COALESCE(SUM(last_id),0) FROM hb_kc_index WHERE kind='chat'").fetchone()[0]
        latest = conn.execute('SELECT COALESCE(MAX(id),0) FROM messages').fetchone()[0]
        last_chat = conn.execute("SELECT COALESCE(MAX(last_id),0) FROM hb_kc_index WHERE kind='chat'").fetchone()[0]
        f['kc_lag'] = max(0, latest - last_chat) if indexed else 0
    try:
        from utils.db._connection import DB_PATH
        f['db_gb'] = round(os.path.getsize(DB_PATH) / 2**30, 2)
    except Exception:
        pass
    return f


# ------------------------------------------------------------------ rules
def findings(f):
    out = []
    gpu = f['gpu']
    if gpu.get('vram_percent') is not None and gpu['vram_percent'] >= 90:
        idle = [m for m in f['models'] if m['kind'] == 'managed' and m['placement'] == 'gpu' and (m['idle_min'] or 0) >= 15]
        for m in idle:
            out.append({'key': f"idle-gpu:{m['model']}", 'severity': 'warn',
                        'text': f"GPU memory is at {gpu['vram_percent']:.0f}% and {m['model']} has been idle {m['idle_min']} min "
                                f"({m['vram_gb']} GB VRAM).", 'command': f"/unload {m['model']}"})
    ram = f['ram']
    if ram['total_gb'] and ram['available_gb'] / ram['total_gb'] < 0.15:
        out.append({'key': 'ram-low', 'severity': 'warn', 'text': f"Only {ram['available_gb']} GB of {ram['total_gb']} GB RAM is free.",
                    'command': '/status'})
    q = f['queue']
    if q.get('queued') and (q.get('oldest_hours') or 0) >= 24:
        out.append({'key': 'queue-old', 'severity': 'info',
                    'text': f"{q['queued']} request(s) waiting; the oldest for {q['oldest_hours']:.0f} h.", 'command': '/queue'})
    for w in f['workers_down']:
        out.append({'key': f'worker:{w}', 'severity': 'warn', 'text': f'Worker {w} is not running.', 'command': '/status'})
    for s in f['spinning']:
        out.append({'key': f"spin:{s['task_id']}", 'severity': 'warn', 'text': f"{s['task_id']} keeps failing: {s['reason']}.",
                    'command': f"/clipboard {s['task_id']}"})
    if f['needs_owner']:
        out.append({'key': 'needs-owner', 'severity': 'info', 'text': f"{len(f['needs_owner'])} task(s) are waiting for your decision.",
                    'command': '/approvals'})
    if f['kc_lag'] >= 200:
        out.append({'key': 'kc-lag', 'severity': 'warn', 'text': f"DOES saving to the Knowledge Centre is {f['kc_lag']} messages behind.",
                    'command': '/status'})
    if f['db_gb'] and f['db_gb'] >= 4:
        out.append({'key': 'db-size', 'severity': 'info', 'text': f"The HB database is {f['db_gb']} GB.", 'command': None})
    return out


def plain_note(items):
    if not items:
        return 'All quiet: nothing needs you right now.'
    warn = [i for i in items if i['severity'] == 'warn']
    return (f"{len(warn)} thing(s) need attention" if warn else 'Nothing urgent') + \
        ': ' + ' '.join(i['text'] for i in (warn or items)[:3])


def model_note(items, model_call=None, timeout=60):
    """The small CPU model phrases and prioritises the findings. Returns (note, source)."""
    if not items:
        return plain_note(items), 'hb'
    try:   # owner 13 Nov: the HB master protocol (compact form for the small model)
        from core.hb_master_prompt import for_role
        protocol = for_role('nanny', compact=True) + '\n'
    except Exception:
        protocol = ''
    prompt = protocol + ('You are the Hummingbird nanny. Hummingbird is a chat app where AI agents work on tasks. Below are findings about '
              'its tasks, models and memory. In one or two calm, short sentences tell the owner what kind of problem matters '
              'most and what to look at first. Do not repeat task ids or numbers (the exact list is shown under your note). '
              'Use only these facts; do not invent anything; do not give commands.\n'
              + '\n'.join(f"- [{i['severity']}] {i['text']}" for i in items))
    try:
        if model_call:
            text = model_call(prompt)
        else:
            from core import llm
            text, _ = llm.chat_via_gateway(NANNY_MODEL, [{'role': 'user', 'content': prompt}], temperature=0.2,
                                           idle_timeout_s=timeout, absolute_timeout_s=timeout, queue_timeout_s=10,
                                           options={'num_predict': 160})
        text = ' '.join(str(text or '').split())[:600]
        # A small model garbles exact details: ids, numbers or alarm words mean HB writes the note itself.
        if len(text) < 20 or re.search(r'\bT-[0-9A-F]{4,}|\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
                                       r'dozen|twenty|thirty|hundred)\b|machine|critical|catastroph|emergency', text, re.I):
            return plain_note(items), 'hb'
        return text, NANNY_MODEL
    except Exception:
        return plain_note(items), 'hb'


# ------------------------------------------------------------------ run
def _owner_chat(conn):
    row = conn.execute("SELECT conversation_id FROM messages WHERE from_agent='user' ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None


def run_once(conn, now=None, model_call=None, force=False):
    """Check, and post in main chat when the findings changed (or hourly while they persist)."""
    ensure_schema(conn)
    conn.execute('INSERT OR IGNORE INTO hb_nanny(id) VALUES(1)')
    now = time.time() if now is None else now
    items = findings(facts(conn, now))
    digest = hashlib.sha256(json.dumps(sorted(i['key'] for i in items)).encode()).hexdigest()
    cfg = settings(conn)
    conn.execute('UPDATE hb_nanny SET last_run=? WHERE id=1', (now,))
    unchanged = digest == cfg['last_hash'] and cfg['last_post'] and now - cfg['last_post'] < REPOST_AFTER
    if not force and (not items or unchanged):
        return None
    note, source = model_note(items, model_call)
    head = f'Nanny ({NANNY_MODEL}, small model in RAM, summary): ' if source == NANNY_MODEL else 'Nanny: '
    text = head + note + ('\nChecked facts:\n' + '\n'.join(f"- {i['text']}" + (f" {i['command']}" if i['command'] else '') for i in items)
                          if items else '')
    conversation = _owner_chat(conn)
    mid = conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                       "VALUES (?,'hummingbird','user',?,'response',0)", (conversation, text)).lastrowid if conversation else None
    conn.execute('INSERT INTO hb_nanny_reports(created_at, findings, note, note_source, message_id) VALUES(?,?,?,?,?)',
                 (now, json.dumps(items), note, source, mid))
    conn.execute('UPDATE hb_nanny SET last_hash=?, last_post=? WHERE id=1', (digest, now))
    return mid


def tick(conn, now=None):
    """Called by the HB coordinator every few seconds; starts a background check when due."""
    cfg = settings(conn)
    now = time.time() if now is None else now
    if not cfg['enabled'] or (cfg['last_run'] and now - cfg['last_run'] < cfg['interval_s']):
        return False
    if not _RUNNING.acquire(blocking=False):
        return False
    conn.execute('UPDATE hb_nanny SET last_run=? WHERE id=1', (now,))

    def work():
        try:
            from utils.db._connection import get_connection
            with closing(get_connection()) as own, own:
                run_once(own)
        except Exception:
            import logging
            logging.getLogger('hb.nanny').exception('nanny check failed')
        finally:
            _RUNNING.release()
    threading.Thread(target=work, name='hb-nanny', daemon=True).start()
    return True
