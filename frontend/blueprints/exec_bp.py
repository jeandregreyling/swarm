"""exec_bp.py — Ghost Exec routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

exec_bp = Blueprint('exec_bp', __name__)

# Ghost Layer exec
import re as _re
_SUDO_ALLOWED = _re.compile(
    r'^sudo\s+systemctl\s+(restart|start|stop|status)\s+swarm-\w+$'
)

import os as _os

_SWARM_ROOT = '/home/seven/swarm'



@exec_bp.route('/api/exec', methods=['POST'])
def api_exec():
    import subprocess as _sp
    data = request.get_json() or {}
    cmd  = (data.get('command') or '').strip()

    gate = _alm_gate_or_response(data, 'exec')
    if gate:
        return gate

    if not cmd:
        return jsonify({'output': '', 'ok': True})

    from database import log_activity

    if _SUDO_ALLOWED.match(cmd):
        try:
            result = _sp.run(
                cmd.split(), capture_output=True, text=True, timeout=15
            )
            output = (result.stdout + result.stderr).strip() or '(done)'
            ok     = result.returncode == 0
            log_activity('terminal', 'ghost_exec_sudo', cmd[:80])
            return jsonify({'output': output, 'ok': ok})
        except Exception as e:
            return jsonify({'output': f'Error: {e}', 'ok': False})

    # Fallback: shell_agent whitelist
    from fridays.skills import call as skill_call
    ok, output = skill_call('shell', args=cmd, agent='ghost')
    log_activity('terminal', 'ghost_exec', cmd[:80])
    return jsonify({'output': output, 'ok': ok})



@exec_bp.route('/api/services/<service_id>/restart', methods=['POST'])
def api_service_restart(service_id):
    """Restart a swarm-* service. Bypasses ALM — restricted to swarm-* pattern only."""
    import subprocess as _sp
    import re
    if not re.match(r'^swarm-[a-z\-]+$', service_id):
        return jsonify({'ok': False, 'error': 'Invalid service id'}), 400
    try:
        result = _sp.run(
            ['sudo', 'systemctl', 'restart', service_id],
            capture_output=True, text=True, timeout=15
        )
        output = (result.stdout + result.stderr).strip() or '(done)'
        ok = result.returncode == 0
        from database import log_activity
        log_activity('terminal', 'service_restart', service_id)
        return jsonify({'ok': ok, 'output': output})
    except Exception as e:
        return jsonify({'ok': False, 'output': str(e)})


@exec_bp.route('/api/services', methods=['GET'])
def api_services_status():
    """Return status for all swarm-* systemd services."""
    import subprocess as _sp
    services = [
        {'id': 'swarm-terminal-prod', 'label': 'Terminal'},
        {'id': 'swarm-listener',    'label': 'Listener'},
        {'id': 'swarm-telegram',    'label': 'Telegram'},
        {'id': 'swarm-discord',     'label': 'Discord'},
        {'id': 'swarm-fridays',     'label': 'Fridays'},
        {'id': 'swarm-sniffer',     'label': 'Sniffer'},
        {'id': 'swarm-monitor',     'label': 'Monitor'},
        {'id': 'swarm-housekeeping','label': 'Housekeeping'},
    ]
    result = []
    for svc in services:
        try:
            r = _sp.run(
                ['systemctl', 'is-active', svc['id']],
                capture_output=True, text=True, timeout=3
            )
            active = r.stdout.strip() == 'active'
            status = r.stdout.strip()
        except Exception as e:
            active = False
            status = 'error'
        result.append({**svc, 'active': active, 'status': status})
    return jsonify(result)


@exec_bp.route('/api/exec/write', methods=['POST'])
def api_exec_write():
    """Write a file. Path must be inside /home/seven/swarm."""
    data    = request.get_json() or {}
    path    = (data.get('path') or '').strip()
    content = data.get('content', '')
    desc    = (data.get('description') or '').strip()

    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    if not path or not path.startswith(_SWARM_ROOT):
        return jsonify({'error': 'Path must be within /home/seven/swarm'}), 400
    if '..' in path:
        return jsonify({'error': 'Invalid path'}), 400

    try:
        # Read previous content for audit trail
        try:
            with open(path, 'r') as f:
                previous = f.read()
        except FileNotFoundError:
            previous = ''

        # Ensure parent dir exists
        _os.makedirs(_os.path.dirname(path), exist_ok=True)

        with open(path, 'w') as f:
            f.write(content)

        conn = get_connection()
        conn.execute(
            "INSERT INTO file_writes (path, description, previous_content, new_content, applied_by) VALUES (?,?,?,?,?)",
            (path, desc, previous[:2000], content[:4000], 'ghost')
        )
        conn.commit()
        conn.close()

        from database import log_activity
        log_activity('terminal', 'file_write', f'{path} — {desc[:60]}')

        lines_old = len(previous.splitlines())
        lines_new = len(content.splitlines())
        return jsonify({'ok': True, 'output': f'Written: {path}\n{lines_old} → {lines_new} lines'})
    except Exception as e:
        return jsonify({'error': str(e), 'ok': False}), 500



