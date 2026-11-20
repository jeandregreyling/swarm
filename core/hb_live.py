"""HB Live L2 (owner 20 Nov 2026; spec docs/spec-hb-live-dashboard.md): the ONE read model of what is going on. Main chat's live strip and
windows render only from snapshot(); nothing else decides what is running.

snapshot(conn) -> {version, lanes, telemetry, needs_you, master, history, unexplained, at}

Sources (read only, nothing is written here):
  hb_activity_log      open runs (APEX turns, model calls, Claude Code) and finished runs (history)       - core/hb_activity_log
  hb_activity.chains   running peer requests (APEX workflow, Fred, Codex, Gemini, Claude Code) + background jobs
  hb_admin_requests    sudo steps running in JD's terminal
  hb_translator        the translator's mode (manual / auto / off)
  sysfs, /proc         GPU busy %, VRAM, temperatures, CPU load, RAM
  hb_commands.waiting_items   Needs you (same list as /approvals)
  hb_queue.status      the clipboard (master list) with doer, importance, parked; joined with what is live per task"""
import hashlib
import json
import os
import time
from pathlib import Path

LANES = (('gpu', 'GPU · APEX'), ('fred', 'CPU · Fred'), ('small', 'CPU · small models'), ('online', 'Online'), ('hb', 'HB'),
         ('admin', 'Admin'), ('claude-code', 'Claude Code'), ('system', 'System'))
ONLINE = ('codex', 'gemini', 'claude', 'copilot', 'online')
BUSY_GPU_PCT = 30


def _lane_for(actor='', model='', agent='', lane=''):
    text = ' '.join(str(x or '').lower() for x in (actor, model, agent))
    if lane == 'claude-code' or 'claude-code' in str(agent):
        return 'claude-code'
    if lane == 'admin':
        return 'admin'
    if any(k in text for k in ONLINE):
        return 'online'
    if 'fred' in text:
        return 'fred'
    if lane == 'cpu' or any(k in text for k in ('homework', 'small', 'translate', 'embed', 'counsel', 'tests')):
        return 'small'
    if lane == 'gpu' or 'apex' in text:
        return 'gpu'
    return 'hb'


def _read(path, cast=float, scale=1.0):
    try:
        return round(cast(Path(path).read_text().strip()) * scale, 1)
    except Exception:
        return None


def telemetry(root='/sys/class/drm'):
    """GPU (first card with gpu_busy_percent), CPU load and temperature, RAM. Missing values are None."""
    gpu = {}
    for card in sorted(Path(root).glob('card*/device')):
        if (card / 'gpu_busy_percent').exists():
            hw = next(iter(sorted(card.glob('hwmon/hwmon*'))), None)
            gpu = {'busy_pct': _read(card / 'gpu_busy_percent'), 'vram_used_gb': _read(card / 'mem_info_vram_used', scale=1 / 2 ** 30),
                   'vram_total_gb': _read(card / 'mem_info_vram_total', scale=1 / 2 ** 30),
                   'temp_c': _read(hw / 'temp1_input', scale=1 / 1000) if hw else None}
            break
    cpu = {'cores': os.cpu_count()}
    try:
        cpu['load1'] = float(Path('/proc/loadavg').read_text().split()[0])
    except Exception:
        cpu['load1'] = None
    for hw in Path('/sys/class/hwmon').glob('hwmon*'):
        if _read(hw / 'name', str) in ('k10temp', 'coretemp', 'zenpower'):
            cpu['temp_c'] = _read(hw / 'temp1_input', scale=1 / 1000)
            break
    ram = {}
    try:
        info = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines() if ':' in line)
        total, avail = (float(info[k].split()[0]) / 2 ** 20 for k in ('MemTotal', 'MemAvailable'))
        ram = {'total_gb': round(total, 1), 'used_gb': round(total - avail, 1)}
    except Exception:
        pass
    return {'gpu': gpu, 'cpu': cpu, 'ram': ram}


def _log_items(conn, now):
    from core import hb_activity_log as live
    items = []
    for r in live.open_runs(conn, now=now):
        if r['parent']:
            continue                                 # a model call inside a turn shows in that turn's trail
        trail = [t for t in live.trail(conn, r['run_id']) if t['kind'] != 'start' or t['text'] != r['title']]
        items.append({'lane': _lane_for(r['actor'], r['model'], lane=r['lane']), 'source': 'log', 'run_id': r['run_id'], 'actor': r['actor'],
                      'model': r['model'], 'device': r['device'], 'title': r['title'], 'since': r['at'], 'task_id': r['task_id'],
                      'step_id': r['step_id'], 'purpose': r['purpose'], 'last_step': trail[-1]['text'] if trail else '', 'trail': trail})
    return items


def _peer_items(conn):
    try:
        from core import hb_activity
        chains = hb_activity.chains(conn)
    except Exception:
        return []
    items = []
    for chain in chains:
        for m in chain['members']:
            lane = _lane_for(m.get('role'), m.get('model'))
            items.append({'lane': lane, 'source': 'peer', 'run_id': f"P-{m['request_id']}" if m.get('request_id') else None,
                          'actor': m.get('role'), 'model': m.get('model'), 'device': m.get('where'), 'title': chain.get('task') or m.get('role'),
                          'since': None, 'task_id': chain.get('task_id'), 'step_id': None, 'purpose': 'peer request',
                          'last_step': m.get('now') or '', 'trail': [{'at': s.get('at'), 'kind': 'step', 'text': s.get('what')} for s in m.get('steps', [])]})
    return items


def _admin_items(conn):
    try:
        rows = conn.execute("SELECT id, argv, why, updated_at FROM hb_admin_requests WHERE state='running'").fetchall()
    except Exception:
        return []
    out = []
    for rid, argv, why, at in rows:
        try:
            cmd = ' '.join(json.loads(argv))
        except Exception:
            cmd = str(argv)
        out.append({'lane': 'admin', 'source': 'admin', 'run_id': rid, 'actor': 'jd', 'model': None, 'device': 'your terminal',
                     'title': f'sudo {cmd}'[:120], 'since': at, 'task_id': None, 'step_id': None, 'purpose': why, 'last_step': 'running', 'trail': []})
    return out


def _merge(items):
    """A task can be seen by the log and by its peer request; keep one per (lane, task), the log's run first, with the longer trail."""
    seen, out = {}, []
    for it in sorted(items, key=lambda i: 0 if i['source'] == 'log' else 1):
        key = (it['lane'], it['task_id']) if it['task_id'] else None
        if key and key in seen:
            kept = seen[key]
            if not kept['trail'] and it['trail']:
                kept['trail'], kept['last_step'] = it['trail'], it['last_step']
            continue
        if key:
            seen[key] = it
        out.append(it)
    return out


def _translator(conn):
    try:
        from core import hb_translator
        mode, _ = hb_translator.mode(conn)
        return mode
    except Exception:
        return None


def _needs_you(conn):
    try:
        from core.hb_commands import waiting_items
        return [{k: (str(v)[:200] if isinstance(v, str) else v) for k, v in dict(i).items()} for i in waiting_items(conn)][:30]
    except Exception:
        return []


def _master(conn, by_task):
    try:
        from core import hb_queue
        q = hb_queue.status(conn)
    except Exception:
        return {'on': None, 'auto': None, 'items': []}
    items = []
    for i in q.get('items', []):
        live = by_task.get(i.get('task_id'))
        items.append({**{k: i.get(k) for k in ('step_id', 'task_id', 'title', 'state', 'why', 'doer', 'importance', 'ready', 'check_result', 'parked')},
                      'live': {'lane': live['lane'], 'last_step': live['last_step'], 'since': live['since']} if live else None})
    return {'on': q.get('on'), 'auto': q.get('auto'), 'note': q.get('note', '')[:300], 'items': items}


def _history(conn):
    try:
        from core import hb_activity_log as live
        return [{**h, 'lane': _lane_for(h['actor'], h['model'], lane=h['lane'])} for h in live.finished(conn, 20)]
    except Exception:
        return []


def snapshot(conn, now=None, tele=None, items=None):
    now = now or time.time()
    found = items if items is not None else _merge(_log_items(conn, now) + _peer_items(conn) + _admin_items(conn))
    tele = tele if tele is not None else telemetry()
    lanes = []
    for lane_id, label in LANES:
        mine = [i for i in found if i['lane'] == lane_id]
        lanes.append({'id': lane_id, 'label': label, 'state': 'busy' if mine else 'idle', 'items': mine})
    mode = _translator(conn)
    if mode in ('manual', 'auto'):
        small = next(l for l in lanes if l['id'] == 'small')
        small['note'] = f'translator on ({mode})'
    by_task = {i['task_id']: i for i in found if i.get('task_id')}
    unexplained = []
    busy = (tele.get('gpu') or {}).get('busy_pct')
    if busy is not None and busy >= BUSY_GPU_PCT and not any(i['lane'] == 'gpu' for i in found):
        unexplained.append({'lane': 'gpu', 'evidence': f'GPU {busy:.0f}% busy and no APEX run is recorded'})
    out = {'lanes': lanes, 'needs_you': _needs_you(conn), 'master': _master(conn, by_task), 'history': _history(conn), 'unexplained': unexplained}
    out['version'] = hashlib.sha1(json.dumps(out, sort_keys=True, default=str).encode()).hexdigest()[:12]
    out['telemetry'], out['at'] = tele, now
    return out
