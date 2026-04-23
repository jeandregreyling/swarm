import time
from flask import Blueprint, current_app, jsonify

health_bp = Blueprint('health', __name__)

_START_TIME = time.time()


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'uptime': round(time.time() - _START_TIME, 1)})


@health_bp.route('/api/_introspect/routes', methods=['GET'])
def introspect_routes():
    """Enumerate every /api/* route. Used by tests/api_wide_probe.py."""
    out = {}
    for rule in current_app.url_map.iter_rules():
        p = str(rule.rule)
        if not p.startswith('/api/'):
            continue
        methods = sorted(m for m in rule.methods if m not in ('HEAD', 'OPTIONS'))
        out.setdefault(p, set()).update(methods)
    return jsonify([
        {'path': p, 'methods': sorted(list(m))}
        for p, m in sorted(out.items())
    ])
