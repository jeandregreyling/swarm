"""
frontend/blueprints/diamond.py — Diamond Layer governance API.

Central hub for the Swarm's operational pulse:
  /api/diamond/pulse      — aggregate health + processing metrics (last 7 days)
  /api/diamond/landscape   — full system capability map
  /api/diamond/attention    — per-tile attention flags (dot indicators)

This replaces the old "Needs Attention" section with richer, combined data
that the home dashboard renders as a processing graph + attention dots.
"""

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify

logger = logging.getLogger('seven.diamond')

_SWARM_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SWARM_ROOT / 'utils'))
sys.path.insert(0, str(_SWARM_ROOT))

diamond_bp = Blueprint('diamond', __name__)


# ── Pulse cache ──────────────────────────────────────────────────────────────
# The home-page sundial polls this endpoint every ~2s. Every call otherwise
# fans out to 6 DB queries + psutil vitals. A short in-memory cache lets
# multiple tiles (sundial, monitor, chat mini-stats) share the same payload
# without turning the sundial into a DB hammer.
_PULSE_CACHE_TTL_S = 2.0
_pulse_cache = {'ts': 0.0, 'payload': None}


# ── Pulse ─────────────────────────────────────────────────────────────────────

@diamond_bp.route('/api/diamond/pulse', methods=['GET'])
def api_diamond_pulse():
    """
    Aggregate health + processing metrics.

    Returns:
      system    — CPU, RAM, temp, swap, disk (current snapshot)
      queue     — depth, processing flag, consults today
      tickets   — open, closed_7d, trend (daily counts last 7 days)
      proposals — pending, active, executed_7d, trend
      agents    — total, enabled, online count
      governance — ALM status, vortex active, sniffles
    """
    try:
        # Serve from short-lived cache when fresh — avoids re-fanning 6 DB
        # queries on every 2s sundial tick while still feeling real-time.
        # Bypassed under TESTING so per-test DB mutations are observed.
        now = time.time()
        testing = bool(current_app and current_app.config.get('TESTING'))
        cached = _pulse_cache.get('payload')
        if (not testing
                and cached is not None
                and (now - _pulse_cache.get('ts', 0.0)) < _PULSE_CACHE_TTL_S):
            return jsonify(cached)

        # ── System vitals ──────────────────────────────────────────────────
        system = _get_system_vitals()

        # ── Queue ──────────────────────────────────────────────────────────
        queue = _get_queue_status()

        # ── Tickets trend ──────────────────────────────────────────────────
        tickets = _get_ticket_trend()

        # ── Proposals trend ────────────────────────────────────────────────
        proposals = _get_proposal_trend()

        # ── Agents ─────────────────────────────────────────────────────────
        agents = _get_agent_summary()

        # ── Governance ─────────────────────────────────────────────────────
        governance = _get_governance_status()

        payload = {
            'ok': True,
            'ts': datetime.now(timezone.utc).isoformat(),
            'system': system,
            'queue': queue,
            'tickets': tickets,
            'proposals': proposals,
            'agents': agents,
            'governance': governance,
        }
        _pulse_cache['payload'] = payload
        _pulse_cache['ts'] = now
        return jsonify(payload)
    except Exception as exc:
        logger.exception('[Diamond] pulse')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Attention (per-tile dots) ─────────────────────────────────────────────────

@diamond_bp.route('/api/diamond/attention', methods=['GET'])
def api_diamond_attention():
    """
    Returns attention flags for each home tile.
    Each flag: { level: 'none'|'info'|'warn'|'crit', count: int, label: str }

    Frontend renders these as coloured dots on the tile corners.
    """
    try:
        flags = {}

        # Tickets
        try:
            from db import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM tickets WHERE status IN ('open','in_progress')"
            ).fetchone()
            conn.close()
            n = row['n'] if row else 0
            if n > 5:
                flags['tickets'] = {'level': 'crit', 'count': n, 'label': f'{n} open tickets'}
            elif n > 0:
                flags['tickets'] = {'level': 'warn', 'count': n, 'label': f'{n} open tickets'}
        except Exception:
            pass

        # Proposals
        try:
            from db import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM work_proposals WHERE status IN ('pending','approved','in_progress')"
            ).fetchone()
            conn.close()
            n = row['n'] if row else 0
            pending_row = conn.execute(
                "SELECT COUNT(*) AS n FROM work_proposals WHERE status='pending'"
            ).fetchone() if False else None
            if n > 0:
                flags['studio'] = {'level': 'warn' if n > 0 else 'none', 'count': n,
                                   'label': f'{n} active proposals'}
        except Exception:
            pass

        # Library (empty = info nudge)
        try:
            from lib.knowledge.store import source_stats
            stats = source_stats()
            total = stats.get('total_sources', 0)
            if total == 0:
                flags['library'] = {'level': 'info', 'count': 0, 'label': 'Library empty — seed knowledge'}
        except Exception:
            pass

        # Memory (duck flags)
        try:
            from db import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM duck_flags WHERE created_at > datetime('now', '-24 hours')"
            ).fetchone()
            conn.close()
            n = row['n'] if row else 0
            if n > 0:
                flags['chat'] = {'level': 'crit', 'count': n, 'label': f'{n} duck flags (24h)'}
        except Exception:
            pass

        # Monitor (CPU/RAM high)
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0)
            ram = psutil.virtual_memory().percent
            if cpu > 80 or ram > 85:
                flags['monitor'] = {'level': 'crit', 'count': 1,
                                    'label': f'CPU {cpu:.0f}% / RAM {ram:.0f}%'}
            elif cpu > 60 or ram > 70:
                flags['monitor'] = {'level': 'warn', 'count': 1,
                                    'label': f'CPU {cpu:.0f}% / RAM {ram:.0f}%'}
        except Exception:
            pass

        return jsonify({'ok': True, 'flags': flags})

    except Exception as exc:
        logger.exception('[Diamond] attention')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Landscape ─────────────────────────────────────────────────────────────────

@diamond_bp.route('/api/diamond/landscape', methods=['GET'])
def api_diamond_landscape():
    """
    Full system capability map — agents, tiers, models, capabilities,
    proposals in flight, library stats, and service health.
    """
    try:
        from utils.db.registry import get_all_agents_raw
        agents_raw = get_all_agents_raw()

        agents = []
        for a in agents_raw:
            agents.append({
                'name': a.get('name'),
                'number': a.get('number'),
                'label': a.get('display_label') or a.get('label') or a.get('name'),
                'tier': a.get('tier', 'local'),
                'model': a.get('model'),
                'enabled': bool(a.get('enabled', 1)),
                'role': a.get('role', ''),
            })

        # Library stats
        try:
            from lib.knowledge.store import source_stats
            lib_stats = source_stats()
        except Exception:
            lib_stats = {}

        # Proposal summary
        try:
            from db import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM work_proposals GROUP BY status"
            ).fetchall()
            conn.close()
            prop_summary = {r['status']: r['n'] for r in rows}
        except Exception:
            prop_summary = {}

        return jsonify({
            'ok': True,
            'agents': agents,
            'library': lib_stats,
            'proposals': prop_summary,
        })
    except Exception as exc:
        logger.exception('[Diamond] landscape')
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_system_vitals():
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        temps = psutil.sensors_temperatures()
        temp_c = None
        for name in ('coretemp', 'k10temp', 'cpu_thermal', 'acpitz'):
            if name in temps and temps[name]:
                temp_c = temps[name][0].current
                break
        disks = []
        for p in psutil.disk_partitions():
            if 'snap' in p.mountpoint or 'loop' in p.mountpoint:
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
                disks.append({'mount': p.mountpoint, 'percent': u.percent,
                              'total_gb': round(u.total / (1024**3), 1),
                              'free_gb': round(u.free / (1024**3), 1)})
            except Exception:
                continue
        # GPU VRAM — nvidia-smi if available, else None
        gpu_vram_percent = None
        gpu_vram_used_gb = None
        gpu_vram_total_gb = None
        try:
            import subprocess
            nv = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=3
            )
            if nv.returncode == 0 and nv.stdout.strip():
                parts = nv.stdout.strip().split(',')
                used_mb, total_mb = float(parts[0].strip()), float(parts[1].strip())
                gpu_vram_used_gb = round(used_mb / 1024, 2)
                gpu_vram_total_gb = round(total_mb / 1024, 2)
                gpu_vram_percent = round((used_mb / total_mb) * 100, 1) if total_mb > 0 else 0
        except Exception:
            pass

        agent_residency = _get_agent_residency()

        return {
            'cpu_percent': round(cpu, 1),
            'ram_percent': round(mem.percent, 1),
            'ram_used_gb': round(mem.used / (1024**3), 2),
            'ram_total_gb': round(mem.total / (1024**3), 2),
            'swap_percent': round(swap.percent, 1),
            'swap_used_gb': round(swap.used / (1024**3), 2),
            'swap_total_gb': round(swap.total / (1024**3), 2),
            'cpu_temp_c': round(temp_c, 1) if temp_c else None,
            'gpu_vram_percent': gpu_vram_percent,
            'gpu_vram_used_gb': gpu_vram_used_gb,
            'gpu_vram_total_gb': gpu_vram_total_gb,
            'agent_residency': agent_residency,
            'disks': disks,
        }
    except Exception as exc:
        logger.warning(f'[Diamond] system vitals: {exc}')
        return {}


def _model_aliases(name):
    raw = str(name or '').strip().lower()
    if not raw:
        return set()
    aliases = {raw}
    if ':' in raw:
        aliases.add(raw.split(':', 1)[0])
    return aliases


def _get_agent_residency():
    try:
        from core import llm as _llm
        from utils.db.registry import get_all_agents_raw

        roster = get_all_agents_raw() or []
        agent_rows = []
        for row in roster:
            name = str(row.get('name') or '').strip().lower()
            if not name:
                continue
            label = str(row.get('display_label') or row.get('label') or name).strip()
            number = row.get('number')
            model = str(row.get('model') or '').strip()
            agent_rows.append({
                'name': name,
                'label': f'{number} · {label}' if number is not None else label,
                'model': model,
            })

        model_map = {}
        for agent in agent_rows:
            for alias in _model_aliases(agent['model']):
                model_map.setdefault(alias, []).append(agent)

        running = _llm.ps()
        models = list(running.models if hasattr(running, 'models') else [])
        residency = {'ram': [], 'swap': [], 'gpu': []}
        seen = {'ram': set(), 'swap': set(), 'gpu': set()}
        swap_pref_agents = {'qwen', 'eight', 'sniffles'}

        for model in models:
            model_name = str(getattr(model, 'model', '') or getattr(model, 'name', '') or '').strip()
            if not model_name:
                continue
            size_bytes = int(getattr(model, 'size', 0) or 0)
            vram_bytes = int(getattr(model, 'size_vram', 0) or 0)
            matched = []
            for alias in _model_aliases(model_name):
                matched.extend(model_map.get(alias, []))
            unique = []
            used_names = set()
            for agent in matched:
                if agent['name'] in used_names:
                    continue
                used_names.add(agent['name'])
                unique.append(agent)

            for agent in unique:
                if vram_bytes > 0:
                    bucket = 'gpu'
                elif agent['name'] in swap_pref_agents or size_bytes >= 8 * (1024 ** 3):
                    bucket = 'swap'
                else:
                    bucket = 'ram'
                if agent['name'] in seen[bucket]:
                    continue
                seen[bucket].add(agent['name'])
                residency[bucket].append({
                    'agent': agent['name'],
                    'label': agent['label'],
                    'model': model_name,
                    'size_gb': round(size_bytes / (1024 ** 3), 2),
                    'size_vram_gb': round(vram_bytes / (1024 ** 3), 2),
                })

        for bucket in residency.values():
            bucket.sort(key=lambda item: item.get('label') or item.get('agent') or '')
        return residency
    except Exception as exc:
        logger.warning(f'[Diamond] residency: {exc}')
        return {'ram': [], 'swap': [], 'gpu': []}


def _get_queue_status():
    try:
        from db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS depth FROM ticket_queue WHERE status='queued'"
        ).fetchone()
        processing = conn.execute(
            "SELECT COUNT(*) AS n FROM ticket_queue WHERE status='processing'"
        ).fetchone()
        consults = conn.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE created_at > datetime('now', '-24 hours')"
        ).fetchone()
        conn.close()
        return {
            'depth': row['depth'] if row else 0,
            'processing': (processing['n'] if processing else 0) > 0,
            'consults_today': consults['n'] if consults else 0,
        }
    except Exception:
        return {'depth': 0, 'processing': False, 'consults_today': 0}


def _get_ticket_trend():
    """Open count + daily closed count for last 7 days."""
    result = {'open': 0, 'closed_7d': 0, 'trend': []}
    try:
        from db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE status IN ('open','in_progress')"
        ).fetchone()
        result['open'] = row['n'] if row else 0

        # Daily trend: how many tickets were resolved/closed each day
        rows = conn.execute("""
            SELECT date(updated_at) AS day, COUNT(*) AS n
            FROM tickets
            WHERE status IN ('resolved','closed')
              AND updated_at > datetime('now', '-7 days')
            GROUP BY date(updated_at)
            ORDER BY day
        """).fetchall()
        conn.close()

        # Build 7-day array with 0-fill
        today = datetime.now(timezone.utc).date()
        day_map = {r['day']: r['n'] for r in rows}
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            result['trend'].append({'day': d, 'closed': day_map.get(d, 0)})

        result['closed_7d'] = sum(t['closed'] for t in result['trend'])
    except Exception:
        result['trend'] = [{'day': '', 'closed': 0}] * 7
    return result


def _get_proposal_trend():
    """Pending/active/executed counts + daily executed trend."""
    result = {'pending': 0, 'active': 0, 'executed_7d': 0, 'trend': []}
    try:
        from db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM work_proposals WHERE status='pending'"
        ).fetchone()
        result['pending'] = row['n'] if row else 0

        row = conn.execute(
            "SELECT COUNT(*) AS n FROM work_proposals WHERE status IN ('approved','in_progress')"
        ).fetchone()
        result['active'] = row['n'] if row else 0

        rows = conn.execute("""
            SELECT date(updated_at) AS day, COUNT(*) AS n
            FROM work_proposals
            WHERE status IN ('executed','done')
              AND updated_at > datetime('now', '-7 days')
            GROUP BY date(updated_at)
            ORDER BY day
        """).fetchall()
        conn.close()

        today = datetime.now(timezone.utc).date()
        day_map = {r['day']: r['n'] for r in rows}
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            result['trend'].append({'day': d, 'executed': day_map.get(d, 0)})

        result['executed_7d'] = sum(t['executed'] for t in result['trend'])
    except Exception:
        result['trend'] = [{'day': '', 'executed': 0}] * 7
    return result


def _get_agent_summary():
    try:
        from utils.db.registry import get_all_agents_raw
        all_agents = get_all_agents_raw()
        enabled = [a for a in all_agents if a.get('enabled')]
        return {
            'total': len(all_agents),
            'enabled': len(enabled),
            'local': len([a for a in enabled if a.get('tier') == 'local']),
            'paid': len([a for a in enabled if a.get('tier') == 'paid']),
            'free': len([a for a in enabled if a.get('tier') == 'free']),
        }
    except Exception:
        return {'total': 0, 'enabled': 0, 'local': 0, 'paid': 0, 'free': 0}


def _get_governance_status():
    try:
        from db import get_connection
        conn = get_connection()
        # Check table exists before querying
        tbl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='time_wizard_log'"
        ).fetchone()
        if tbl:
            tw_row = conn.execute(
                "SELECT COUNT(*) AS n FROM time_wizard_log WHERE created_at > datetime('now', '-1 hour')"
            ).fetchone()
            vortex_active = (tw_row['n'] if tw_row else 0) > 0
        else:
            vortex_active = False
        conn.close()

        # Sniffles check
        sniffles = False
        try:
            from utils.db.registry import get_agent_roster
            roster = get_agent_roster()
            sniffles = any(a['name'] == 'sniffles' and a.get('enabled') for a in roster)
        except Exception:
            pass

        return {
            'vortex_active': vortex_active,
            'sniffles_enabled': sniffles,
            'alm_status': 'enforced' if vortex_active else 'standby',
        }
    except Exception:
        return {'vortex_active': False, 'sniffles_enabled': False, 'alm_status': 'standby'}


# ── Governance pause/resume ──────────────────────────────────────────────────
# A file-based flag that the UI can read and toggle. Governance transition
# enforcement can consult this flag to downgrade blocking checks to warnings
# when an operator has temporarily paused the state machine.
_GOV_FLAG = _SWARM_ROOT / '.governance_paused'
_VORTEX_FLAG = _SWARM_ROOT / '.vortex_paused'


def _read_flag(path):
    try:
        return path.exists()
    except Exception:
        return False


@diamond_bp.route('/api/governance/state', methods=['GET'])
def api_governance_state():
    try:
        status = _get_governance_status()
        status['paused'] = _read_flag(_GOV_FLAG)
        status['vortex_paused'] = _read_flag(_VORTEX_FLAG)
        return jsonify({'ok': True, **status})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@diamond_bp.route('/api/governance/toggle', methods=['POST'])
def api_governance_toggle():
    try:
        from flask import request
        data = request.get_json(silent=True) or {}
        target = data.get('target', 'governance')
        flag = _VORTEX_FLAG if target == 'vortex' else _GOV_FLAG
        if flag.exists():
            flag.unlink()
            paused = False
        else:
            flag.write_text(datetime.now(timezone.utc).isoformat())
            paused = True
        return jsonify({'ok': True, 'target': target, 'paused': paused})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
