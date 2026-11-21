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
import re
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
        value = cast(Path(path).read_text().strip())
        return value if isinstance(value, str) else round(value * scale, 1)
    except (OSError, ValueError, TypeError):
        return None


def telemetry(root='/sys/class/drm'):
    """Live GPU performance, CPU load/temperature and CPU0 clocks/governor, RAM. Missing values are None."""
    gpu = {}
    for card in sorted(Path(root).glob('card*/device')):
        if (card / 'gpu_busy_percent').exists():
            hw = next(iter(sorted(card.glob('hwmon/hwmon*'))), None)
            gpu = {'busy_pct': _read(card / 'gpu_busy_percent'), 'vram_used_gb': _read(card / 'mem_info_vram_used', scale=1 / 2 ** 30),
                   'vram_total_gb': _read(card / 'mem_info_vram_total', scale=1 / 2 ** 30),
                   'temp_c': _read(hw / 'temp1_input', scale=1 / 1000) if hw else None}
            gpu.update({
                'junction_temp_c': _read(hw / 'temp2_input', scale=1 / 1000) if hw else None,
                'fan_rpm': _read(hw / 'fan1_input') if hw else None,
                'power_w': _read(hw / 'power1_average', scale=1 / 10 ** 6) if hw else None,
                'power_cap_w': _read(hw / 'power1_cap', scale=1 / 10 ** 6) if hw else None,
                'performance_mode': _read(card / 'power_dpm_force_performance_level', str),
            })
            clocks = _read(card / 'pp_dpm_sclk', str)
            selected = re.search(r'(?im)^\d+:\s*(\d+)mhz\s*\*', clocks) if clocks else None
            gpu['clock_mhz'] = int(selected[1]) if selected else None
            overdrive = _read(card / 'pp_od_clk_voltage', str)
            maximum = re.search(r'(?im)^1:\s*(\d+)mhz', overdrive.partition('OD_MCLK:')[0]) if overdrive else None
            gpu['clock_limit_mhz'] = int(maximum[1]) if maximum else None
            break
    cpu = {'cores': os.cpu_count()}
    frequency = Path('/sys/devices/system/cpu/cpu0/cpufreq')
    cpu.update({'clock_mhz': _read(frequency / 'scaling_cur_freq', scale=1 / 1000),
                'max_clock_mhz': _read(frequency / 'cpuinfo_max_freq', scale=1 / 1000),
                'governor': _read(frequency / 'scaling_governor', str),
                'epp': _read(frequency / 'energy_performance_preference', str)})   # Practice 280: what the CPU mode really is
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


def _real_model(model):
    """Practice 208 (JD 21 Nov: "APEX is showing QWEN 3.8 at the top and GPT 20B in chat, they can't both be right"): the stand-in names
    of APEX's port (gpt-oss:20b, apex-direct:20b) shown as the model that really plays APEX."""
    try:
        from core.hb_activity_log import who
        return who(model)[3] or model
    except Exception:
        return model


def _title(text):
    """Practice 208: HB's own continuation notes are JSON; a card shows them as words, not as raw JSON."""
    t = str(text or '')
    if '{' not in t or '"task_type"' not in t:
        return t
    head, _, body = t.partition('{')
    try:
        data = json.loads('{' + body)
    except Exception:
        import re
        m = re.search(r'"task_id":\s*"([^"]+)"', t)
        return f"{head}continuing {m.group(1) if m else 'a task'}"
    kind = str(data.get('task_type') or '').replace('hb_', '').replace('_', ' ')
    why = str(data.get('reason') or data.get('next_task') or '')[:90]
    return f"{head}{kind} {data.get('task_id') or ''}" + (f" - {why}" if why else '')


def _log_items(conn, now):
    from core import hb_activity_log as live
    items = []
    for r in live.open_runs(conn, now=now):
        if r['parent']:
            continue                                 # a model call inside a turn shows in that turn's trail
        if r.get('purpose') == 'main-chat turn' and r['at'] < STARTED:
            continue                                 # Practice 208: a main-chat turn from before HB's last restart is gone, not running
        trail = [t for t in live.trail(conn, r['run_id']) if t['kind'] != 'start' or t['text'] != r['title']]
        items.append({'lane': _lane_for(r['actor'], r['model'], lane=r['lane']), 'source': 'log', 'run_id': r['run_id'], 'actor': r['actor'],
                      'model': _real_model(r['model']), 'device': r['device'], 'title': _title(r['title']), 'since': r['at'], 'task_id': r['task_id'],
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
                          'actor': m.get('role'), 'model': _real_model(m.get('model')), 'device': m.get('where'), 'title': _title(chain.get('task') or m.get('role')),
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


def _group(item, risk):
    """Practice 194: the board's group for a clipboard row - needs_you, now, next, claude, waiting, spec, parked, blocked."""
    state, why = item.get('state') or 'waiting', str(item.get('why') or '').lower()
    if state in ('needs_you', 'now', 'next', 'blocked'):
        return state
    if item.get('parked'):
        return 'parked'
    if 'needs a spec' in why or str(risk or '').lower().startswith('needs a spec') or 'needs a spec' in str(risk or '').lower():
        return 'spec'
    if item.get('doer') == 'claude' and 'no hb task' in why:
        return 'claude'
    return 'waiting'


def _master(conn, by_task):
    try:
        from core import hb_queue
        q = hb_queue.status(conn)
    except Exception:
        return {'on': None, 'auto': None, 'items': []}
    risks = {}
    try:
        risks = {sid: risk for sid, risk in conn.execute('SELECT step_id, residual_risk FROM project_steps')}
    except Exception:
        pass
    items = []
    for i in q.get('items', []):
        live = by_task.get(i.get('task_id'))
        items.append({**{k: i.get(k) for k in ('step_id', 'task_id', 'title', 'state', 'why', 'doer', 'importance', 'ready', 'check_result', 'parked')},
                      'group': _group(i, risks.get(i.get('step_id'))), 'note': (risks.get(i.get('step_id')) or '')[:300],
                      'live': {'lane': live['lane'], 'last_step': live['last_step'], 'since': live['since']} if live else None})
    # Practice 194 (owner 20 Nov: "a clear queue and visual board of open tasks"): steps other actors own (Claude Code's register, the
    # roadmap) are on the board too, folded under Roadmap - the one list shows everything that is open, not only APEX's queue.
    try:
        project = getattr(hb_queue, 'PROJECT', None)
        shown = {i['step_id'] for i in items}
        for sid, title, owner, risk in conn.execute("SELECT step_id, title, COALESCE(owner,''), residual_risk FROM project_steps WHERE project_id=? "
                                                    "AND status NOT IN ('done','skipped') ORDER BY order_idx, created_at", (project,)).fetchall():
            if sid in shown:
                continue
            items.append({'step_id': sid, 'task_id': None, 'title': title, 'state': 'roadmap', 'why': f'owned by {owner or "nobody"}',
                          'doer': owner or None, 'importance': None, 'ready': False, 'check_result': None, 'parked': False,
                          'group': 'roadmap', 'note': (risk or '')[:300], 'live': None})
    except Exception:
        pass
    return {'on': q.get('on'), 'auto': q.get('auto'), 'note': q.get('note', '')[:300], 'items': items}


def _with_chunks(conn, items):
    """Practice 234 (chunk-first interface): every row and every active worker that works on a task carries the task's chunks."""
    from core.hb_chunks import view
    seen = {}
    for item in items:
        tid = item.get('task_id')
        if tid:
            if tid not in seen:
                seen[tid] = view(conn, tid)
            item['chunks'] = seen[tid]
    return items


def _with_lights(conn, items):
    """Practice 272 (JD 22 Nov: "built into HB as icons so I can see the system actually using DREAM to do its work"): each APEX or
    Fred turn carries its DOES lights (queue started, inference, receipts, continuity) and DREAM lights, from its own records."""
    try:
        from core import hb_lights
    except Exception:
        return items
    for item in items:
        if item.get('lane') not in ('gpu', 'fred'):
            continue
        run = str(item.get('run_id') or '')
        request = int(run[2:]) if run.startswith('P-') and run[2:].isdigit() else None
        try:
            lights = hb_lights.turn(conn, task_id=item.get('task_id'), request_id=request, run_id=run if run.startswith('R-') else None)
        except Exception:
            continue
        if lights.get('request_id') or lights.get('task_id'):
            item['lights'] = lights
    return items


def _copilot_linked(conn):
    try:
        row = conn.execute("SELECT last_used_at FROM service_tokens WHERE principal_id='copilot-instructor' AND revoked_at IS NULL "
                           "AND last_used_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        return bool(row and time.time() - row[0] < 900)
    except Exception:
        return False


def _doers(conn):
    """Practice 276 (JD 22 Nov: the task list showed "actors that aren't even available"): who HB can really give a step to from the list.
    APEX always; Fred unless his switch is Off. Other names are not wired into HB's workflow (core/hb_plan_workflow._dispatch_doer)."""
    try:
        from core import hb_model_switches
        off = hb_model_switches.modes(conn).get(hb_model_switches.FRED) == 'off'
    except Exception:
        off = False
    # Practice 278 (JD 22 Nov: "if i could actually click on anything"): Fred stays pickable when his switch is off - picking switches him on
    return [{'id': 'apex', 'name': 'APEX', 'ok': True, 'off': False, 'why': 'APEX does the step on the GPU'},
            {'id': 'fred', 'name': 'Fred', 'ok': True, 'off': off,
             'why': ('Fred is switched off - picking him switches him on and hands him this task now' if off
                     else 'Fred (24B on the CPU) takes this task now; your pick counts as you calling Fred')}] + _online_doers(conn)


def _online_doers(conn):
    """Practice 279 (JD 22 Nov: "where's Claude, Codex, GIT?"): a pick sends the agent the task as JD's @ request; the note says its state."""
    out = []
    try:
        from core import hb_online
        for key, name, mention in (('claude', 'Claude Code', '@claude'), ('codex', 'Codex', '@codex')):
            s = hb_online.status(conn, key)
            note = '' if s.get('available') else ('out of usage' if 'usage' in str(s.get('reason', '')).lower() else 'unavailable')
            out.append({'id': key, 'name': name, 'ok': True, 'off': False, 'note': note,
                        'why': f"Sends it this task as your {mention} request" + (f": {str(s.get('reason', ''))[:120]}" if note else '')})
    except Exception:
        pass
    linked = _copilot_linked(conn)
    out.append({'id': 'copilot', 'name': 'Copilot', 'ok': True, 'off': False, 'note': '' if linked else 'not connected',
                'why': 'Sends it this task as your @git request' + ('' if linked else ': its VS Code link has not called HB in 15 minutes')})
    return out


def _apex_lights(conn):
    """Practice 272: the lights of APEX's newest turn (running now, or the last one) for the meter on top of main chat."""
    try:
        from core import hb_lights
        row = conn.execute("SELECT w.request_id, w.state FROM hb_peer_work w JOIN peer_messages p ON p.id=w.request_id "
                           "WHERE p.recipient='apex' ORDER BY w.request_id DESC LIMIT 1").fetchone()
        if not row:
            return None
        lights = hb_lights.turn(conn, request_id=row[0])
        lights['running'] = row[1] == 'running'
        return lights
    except Exception:
        return None


BOARD_GROUPS = (('needs_you', 'Needs you'), ('now', 'Now'), ('next', 'Next'), ('claude', 'With Claude Code'), ('waiting', 'Waiting'),
                ('spec', 'Needs a spec'), ('parked', 'Parked by HB'), ('blocked', 'Blocked'))


def board_text(snap, roadmap_lines=0):
    """Practice 194: the list as one main-chat post (HB's /board) - every row with the command that moves it. Commands in HB's posts are
    one-click buttons in main chat and work as replies from Telegram."""
    m = snap.get('master') or {}
    items = m.get('items') or []
    needs = [n for n in snap.get('needs_you') or [] if n.get('kind') != 'status']
    open_items = [i for i in items if i.get('group') != 'roadmap']
    lines = [f"📋 HB's list - {len(open_items)} open, {len(needs)} need you · HB is {'paused (Auto off)' if m.get('on') is False else 'driving'}"]
    if needs:
        lines.append('Needs you:')
        for n in needs[:8]:
            cmds = []
            if n.get('kind') == 'accept' and n.get('step_id'):
                cmds.append(f"/accept {n['step_id']}")
            if n.get('task_id') and n.get('kind') != 'accept':
                cmds += [f"/continue {n['task_id']}", f"/cancel {n['task_id']}"]
            lines.append(f"  • {n.get('label', '')}" + (' → ' + ' · '.join(cmds) if cmds else ''))
    for key, word in BOARD_GROUPS[1:]:
        rows = [i for i in open_items if i.get('group') == key]
        if not rows:
            continue
        lines.append(f'{word}:')
        for i in rows[:8]:
            cmd = ''
            if key == 'now' and i.get('task_id'):
                cmd = f" → /pause {i['task_id']}"
            elif key == 'next' and i.get('step_id'):
                cmd = f" → /workflow next {i['step_id']}"
            elif key == 'parked' and i.get('task_id'):
                cmd = f" → /continue {i['task_id']}"
            elif key == 'spec' and i.get('task_id'):
                cmd = f" → /done {i['task_id']} <what done means>"
            live = f" ({i['live']['last_step'][:60]})" if i.get('live') else ''
            lines.append(f"  • {i.get('title', '')[:90]}{live}{cmd}")
        if len(rows) > 8:
            lines.append(f'  … and {len(rows) - 8} more on the board')
    roadmap = [i for i in items if i.get('group') == 'roadmap']
    if roadmap:
        lines.append(f'Roadmap: {len(roadmap)} planned items (folded on the board).')
    lines.append('Options: /drive on (HB drives the list) · /workflow off (pause everything) · /board (this list again)')
    return '\n'.join(lines)


def _history(conn):
    try:
        from core import hb_activity_log as live
        return [{**h, 'lane': _lane_for(h['actor'], h['model'], lane=h['lane'])} for h in live.finished(conn, 20)]
    except Exception:
        return []


STARTED = time.time()      # Practice 200: the page reloads itself when HB restarted (new code loaded)


def apex_live(url='http://127.0.0.1:8080', fetch=None):
    """Practice 200 (owner 20 Nov: "you are still not letting me see the actual token count and what APEX is doing"): APEX's model server
    slot right now - reading (prompt tokens done / total), writing (tokens decoded), the context in use - plus who plays APEX."""
    import urllib.request
    try:
        if fetch is None:
            with urllib.request.urlopen(url + '/slots', timeout=0.6) as r:
                slots = json.loads(r.read())
        else:
            slots = fetch()
        s = slots[0]
    except Exception:
        return {'up': False}
    nxt = (s.get('next_token') or [{}])[0]
    try:
        from core.hb_apex_swap import playing, backend
        model, where = playing(), backend()
    except Exception:
        model, where = None, None
    return {'up': True, 'busy': bool(s.get('is_processing')), 'prompt_tokens': int(s.get('n_prompt_tokens') or 0),
            'prompt_done': int(s.get('n_prompt_tokens_processed') or 0), 'prompt_cached': int(s.get('n_prompt_tokens_cache') or 0),
            'generated': int(nxt.get('n_decoded') or 0), 'ctx': int(s.get('n_ctx') or 0), 'task': s.get('id_task'),
            'model': model, 'device': {'rocm': 'ROCm', 'vulkan': 'Vulkan'}.get(where or '', where)}


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
    master = _master(conn, by_task)
    _with_chunks(conn, found + master.get('items', []))     # Practice 234: chunk n of N on every worker and every row
    _with_lights(conn, found)                               # Practice 272: DOES and DREAM lights on every APEX / Fred turn
    out = {'lanes': lanes, 'needs_you': _needs_you(conn), 'master': master, 'history': _history(conn), 'unexplained': unexplained}
    out['version'] = hashlib.sha1(json.dumps(out, sort_keys=True, default=str).encode()).hexdigest()[:12]
    out['telemetry'], out['at'] = tele, now
    out['apex_live'], out['started'] = apex_live(), STARTED      # Practice 200 (outside the version hash: it changes every read)
    try:                                                       # Practice 280: GPU mode for HB Live's buttons
        from core.hb_power import gpu_mode
        out.setdefault('telemetry', {}).setdefault('gpu', {})
        out['telemetry']['gpu']['gpu_mode'] = gpu_mode(out['telemetry']['gpu'])
    except Exception:
        pass
    out['doers'] = _doers(conn)                                # Practice 276: the task list offers only these
    out['apex_lights'] = _apex_lights(conn)                    # Practice 272: always on the meter, live or the last turn
    return out
