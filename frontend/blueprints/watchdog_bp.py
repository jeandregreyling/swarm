"""watchdog_bp.py — Local AI watchdog status, controls, and settings.

Surfaces the persistent `watchdog_repair_lessons` queue and `detect_and_record_stalls`
to the Local AI panel so an operator can see stuck tasks, scan on demand, and
tune basic thresholds without touching the database.
"""
from __future__ import annotations

import json
import os
from flask import Blueprint, jsonify, request

watchdog_bp = Blueprint('watchdog', __name__)


_SETTINGS_KEYS = {
    'stale_minutes':  ('SWARM_WATCHDOG_STALE_MINUTES', 15, 1, 720),
    'scan_limit':     ('SWARM_WATCHDOG_SCAN_LIMIT',    20, 1, 200),
    'auto_recover':   ('SWARM_WATCHDOG_AUTO_RECOVER',   1, 0, 1),
}


def _settings_path():
    base = os.environ.get('SWARM_STATE_DIR') or os.path.expanduser('~/.swarm')
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, 'watchdog_settings.json')


def _load_settings():
    out = {}
    path = _settings_path()
    try:
        if os.path.exists(path):
            with open(path) as f:
                raw = json.load(f) or {}
        else:
            raw = {}
    except Exception:
        raw = {}
    for key, (env_var, default, lo, hi) in _SETTINGS_KEYS.items():
        env_val = os.environ.get(env_var)
        if env_val is not None:
            try:
                out[key] = max(lo, min(int(env_val), hi))
                continue
            except Exception:
                pass
        if key in raw:
            try:
                out[key] = max(lo, min(int(raw[key]), hi))
                continue
            except Exception:
                pass
        out[key] = default
    return out


def _save_settings(updates):
    path = _settings_path()
    current = _load_settings()
    for key, val in (updates or {}).items():
        if key not in _SETTINGS_KEYS:
            continue
        _, _, lo, hi = _SETTINGS_KEYS[key]
        try:
            current[key] = max(lo, min(int(val), hi))
        except Exception:
            continue
    try:
        with open(path, 'w') as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        return current, str(e)
    return current, None


@watchdog_bp.route('/api/watchdog/status', methods=['GET'])
def api_watchdog_status():
    """Combined snapshot for the Local AI watchdog panel."""
    try:
        from utils.db.watchdog_lessons import list_open_repair_lessons
        lessons = list_open_repair_lessons(limit=20)
    except Exception as e:
        lessons = []
        err = str(e)
    else:
        err = None
    return jsonify({
        'ok': err is None,
        'error': err,
        'open_count': len(lessons),
        'lessons': lessons,
        'settings': _load_settings(),
    })


@watchdog_bp.route('/api/watchdog/scan', methods=['POST'])
def api_watchdog_scan():
    """Run stall detection on demand using current settings."""
    body = request.get_json(silent=True) or {}
    settings = _load_settings()
    stale = int(body.get('stale_minutes', settings['stale_minutes']))
    limit = int(body.get('scan_limit',    settings['scan_limit']))
    auto  = bool(body.get('auto_recover', settings['auto_recover']))
    try:
        from utils.db.watchdog_lessons import detect_and_record_stalls
        created = detect_and_record_stalls(
            max_age_minutes=stale, limit=limit, auto_recover=auto
        )
        return jsonify({
            'ok': True,
            'created_lessons': len(created),
            'stale_minutes': stale,
            'limit': limit,
            'auto_recover': auto,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@watchdog_bp.route('/api/watchdog/settings', methods=['GET', 'POST'])
def api_watchdog_settings():
    if request.method == 'GET':
        return jsonify({'ok': True, 'settings': _load_settings()})
    body = request.get_json(silent=True) or {}
    current, err = _save_settings(body)
    if err:
        return jsonify({'ok': False, 'error': err, 'settings': current}), 500
    return jsonify({'ok': True, 'settings': current})


@watchdog_bp.route('/api/watchdog/missing-models', methods=['GET'])
def api_watchdog_missing_models():
    """Compare local-tier agents.model against installed Ollama models.

    Surfaces the "DeepSeek 27B expected but not found" class of issues from
    the improvement intake.
    """
    expected = []
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT name, label, model, tier FROM agents "
            "WHERE enabled=1 AND tier='local' AND model IS NOT NULL AND model != ''"
        ).fetchall()
        conn.close()
        for r in rows:
            d = dict(r)
            expected.append({
                'agent': d.get('name', ''),
                'label': d.get('label', ''),
                'model': d.get('model', ''),
            })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'missing': []}), 500

    installed = set()
    try:
        import requests as _rq
        r = _rq.get('http://localhost:11434/api/tags', timeout=3)
        if r.status_code == 200:
            for m in (r.json() or {}).get('models', []) or []:
                name = (m.get('name') or '').lower()
                if name:
                    installed.add(name)
    except Exception:
        installed = set()

    def _matches(model_name):
        m = (model_name or '').lower()
        if not m:
            return False
        if m in installed:
            return True
        for n in installed:
            if n == m or n.startswith(m) or m.startswith(n):
                return True
        return False

    missing = [e for e in expected if not _matches(e['model'])]
    return jsonify({
        'ok': True,
        'expected_count': len(expected),
        'installed_count': len(installed),
        'missing': missing,
    })
