"""blueprints/fan.py — CPU temperature + fan mode API.

GET  /api/fan/status        → {cpu_c, temps, helper_installed, mode, targets}
POST /api/fan/mode          {mode: 'auto'|'boost'}

Mode changes require the privileged `swarm-fanctl.service` helper to be
installed. Without it the endpoint returns a 503 with setup instructions.
"""
from __future__ import annotations

import os
import sys

from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core import fan_controller  # type: ignore  # noqa: E402

fan_bp = Blueprint('fan_bp', __name__)


@fan_bp.route('/api/fan/status', methods=['GET'])
def fan_status():
    return jsonify({'ok': True, **fan_controller.summary()})


@fan_bp.route('/api/fan/mode', methods=['POST'])
def fan_mode():
    data = request.get_json(silent=True) or {}
    mode = (data.get('mode') or '').strip().lower()
    resp = fan_controller.set_mode(mode)
    status = 200 if resp.get('ok') else (503 if resp.get('reason') == 'helper-not-installed' else 400)
    return jsonify(resp), status
