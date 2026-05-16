"""exec_bp.py — Ghost Exec routes"""
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

exec_bp = Blueprint('exec_bp', __name__)

# Ghost Layer exec
import re as _re
_SUDO_ALLOWED = _re.compile(
    r'^sudo\s+systemctl\s+(restart|start|stop|status)\s+swarm-[\w-]+$'
)

import os as _os
from pathlib import Path as _Path

_SWARM_ROOT = _os.environ.get('SWARM_ROOT',
              _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
_SWARM_ROOT_PATH = _Path(_SWARM_ROOT).resolve()

_SERVICE_REGISTRY = [
    {'id': 'swarm-terminal.service', 'label': 'PROD UI', 'env': 'PROD', 'kind': 'ui', 'port': 5050},
    {'id': 'swarm-terminal-dev.service', 'label': 'DEV UI', 'env': 'DEV', 'kind': 'ui', 'port': 5051},
    {'id': 'swarm-terminal-uat.service', 'label': 'UAT UI', 'env': 'UAT', 'kind': 'ui', 'port': 5053},
    {'id': 'swarm-fridays.service', 'label': 'Fridays Orchestrator', 'env': 'SHARED', 'kind': 'core'},
    {'id': 'swarm-monitor.service', 'label': 'System Monitor', 'env': 'SHARED', 'kind': 'core'},
    {'id': 'swarm-listener.service', 'label': 'Email Listener', 'env': 'SHARED', 'kind': 'io'},
    {'id': 'swarm-telegram.service', 'label': 'Telegram Bot', 'env': 'SHARED', 'kind': 'io'},
    {'id': 'swarm-discord.service', 'label': 'Discord Bot', 'env': 'SHARED', 'kind': 'io'},
    {'id': 'swarm-sniffer.service', 'label': 'Sniffer', 'env': 'SHARED', 'kind': 'io'},
    {'id': 'swarm-housekeeping.service', 'label': 'Housekeeping', 'env': 'SHARED', 'kind': 'maintenance'},
    {'id': 'swarm-prewarm.service', 'label': 'Model Prewarm', 'env': 'SHARED', 'kind': 'runtime'},
    {'id': 'ollama.service', 'label': 'Ollama Runtime', 'env': 'RUNTIME', 'kind': 'runtime'},
]


def _service_by_id(service_id):
    service_id = str(service_id or '').strip()
    for svc in _SERVICE_REGISTRY:
        if svc['id'] == service_id:
            return dict(svc)
    return None


def _run_systemctl(args, timeout=20):
    import subprocess as _sp
    cmd = ['sudo', 'systemctl'] + list(args)
    result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
    output = (result.stdout + result.stderr).strip() or '(done)'
    return result.returncode == 0, output


def _systemctl_is_enabled(unit):
    import subprocess as _sp
    try:
        r = _sp.run(['systemctl', 'is-enabled', unit], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() or r.stderr.strip() or 'unknown'
    except Exception:
        return 'unknown'


def _systemctl_is_active(unit):
    import subprocess as _sp
    try:
        r = _sp.run(['systemctl', 'is-active', unit], capture_output=True, text=True, timeout=3)
        status = r.stdout.strip() or r.stderr.strip() or 'unknown'
        return status == 'active', status
    except Exception:
        return False, 'error'


def _service_payload(svc):
    active, status = _systemctl_is_active(svc['id'])
    enabled = _systemctl_is_enabled(svc['id'])
    return {
        **svc,
        'active': active,
        'status': status,
        'enabled': enabled,
        'installed': status not in {'not-found', 'unknown'} or enabled not in {'not-found', 'unknown'},
        'can_restart': True,
        'can_hard_restart': True,
    }


def _ollama_runner_rows():
    import subprocess as _sp
    rows = []
    try:
        proc = _sp.run(
            ['pgrep', '-af', 'ollama runner'],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in (proc.stdout or '').splitlines():
            parts = line.strip().split(' ', 1)
            if not parts or not parts[0].isdigit():
                continue
            rows.append({'pid': int(parts[0]), 'cmd': parts[1] if len(parts) > 1 else ''})
    except Exception:
        pass
    return rows


def _log_watchdog_service_action(action, detail, status='ok'):
    try:
        from utils.db._connection import get_connection
        conn = get_connection()
        try:
            content = (
                'Watchdog service controls manage PROD/DEV/UAT UI units, shared swarm services, '
                'and Ollama hard-kill/restart actions from the bottom-right Services menu. '
                f'Last action: {action} status={status} detail={str(detail)[:500]}'
            )
            cur = conn.execute(
                """UPDATE swarm_knowledge
                   SET content=?, source_agent='watchdog', category='fact', importance=8, updated_at=datetime('now')
                   WHERE key='watchdog_service_controls_runtime_ops'""",
                (content,),
            )
            if cur.rowcount == 0:
                conn.execute(
                    """INSERT INTO swarm_knowledge
                       (key, content, source_agent, category, importance, created_at, updated_at)
                       VALUES ('watchdog_service_controls_runtime_ops', ?, 'watchdog', 'fact', 8, datetime('now'), datetime('now'))""",
                    (content,),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass



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
        import shlex
        try:
            result = _sp.run(
                shlex.split(cmd), capture_output=True, text=True, timeout=15
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
    """Restart a known service. Bypasses ALM; restricted to the service registry."""
    svc = _service_by_id(service_id)
    if not svc:
        return jsonify({'ok': False, 'error': 'Invalid service id'}), 400
    data = request.get_json(silent=True) or {}
    hard = str(data.get('mode') or '').strip().lower() in {'hard', 'kill', 'force'}
    try:
        if hard:
            kill_ok, kill_out = _run_systemctl(['kill', '-s', 'SIGKILL', svc['id']], timeout=12)
            start_ok, start_out = _run_systemctl(['start', svc['id']], timeout=20)
            ok = start_ok
            output = f'kill={kill_ok}: {kill_out}\nstart={start_ok}: {start_out}'
            action = 'service_hard_restart'
        else:
            ok, output = _run_systemctl(['restart', svc['id']], timeout=20)
            action = 'service_restart'
        from database import log_activity
        log_activity('terminal', action, svc['id'])
        _log_watchdog_service_action(action, f'{svc["id"]}: {output}', 'ok' if ok else 'error')
        return jsonify({'ok': ok, 'output': output, 'service': _service_payload(svc)})
    except Exception as e:
        return jsonify({'ok': False, 'output': str(e)})


@exec_bp.route('/api/services', methods=['GET'])
def api_services_status():
    """Return status for managed PROD/DEV/UAT/shared services plus Ollama runners."""
    result = [_service_payload(svc) for svc in _SERVICE_REGISTRY]
    result.append({
        'id': 'ollama-runners',
        'label': 'Ollama Runners',
        'env': 'RUNTIME',
        'kind': 'runtime',
        'active': bool(_ollama_runner_rows()),
        'status': f'{len(_ollama_runner_rows())} runner(s)',
        'enabled': 'runtime',
        'installed': True,
        'can_restart': False,
        'can_hard_restart': False,
        'can_kill': True,
        'runners': _ollama_runner_rows(),
    })
    return jsonify(result)


@exec_bp.route('/api/services/restart-all', methods=['POST'])
def api_services_restart_all():
    """Restart all known services for an environment group."""
    data = request.get_json(silent=True) or {}
    env = str(data.get('env') or 'PROD').strip().upper()
    hard = bool(data.get('hard'))
    if env not in {'PROD', 'DEV', 'UAT', 'SHARED', 'RUNTIME'}:
        return jsonify({'ok': False, 'error': 'Invalid env'}), 400
    targets = [svc for svc in _SERVICE_REGISTRY if svc['env'] == env]
    if env == 'RUNTIME':
        targets = [svc for svc in _SERVICE_REGISTRY if svc['id'] == 'ollama.service']
    results = []
    for svc in targets:
        try:
            if hard:
                kill_ok, kill_out = _run_systemctl(['kill', '-s', 'SIGKILL', svc['id']], timeout=12)
                start_ok, start_out = _run_systemctl(['start', svc['id']], timeout=20)
                results.append({'id': svc['id'], 'ok': start_ok, 'output': f'kill={kill_ok}: {kill_out}\nstart={start_ok}: {start_out}'})
            else:
                ok, output = _run_systemctl(['restart', svc['id']], timeout=20)
                results.append({'id': svc['id'], 'ok': ok, 'output': output})
        except Exception as exc:
            results.append({'id': svc['id'], 'ok': False, 'output': str(exc)})
    ok_all = all(item['ok'] for item in results)
    _log_watchdog_service_action('restart_all', f'env={env} hard={hard} results={results}', 'ok' if ok_all else 'error')
    return jsonify({'ok': ok_all, 'env': env, 'results': results})


@exec_bp.route('/api/services/ollama/kill-runners', methods=['POST'])
def api_ollama_kill_runners():
    """Hard kill runaway Ollama runner child processes without stopping the service."""
    import os
    import signal
    killed = []
    errors = []
    for row in _ollama_runner_rows():
        try:
            os.kill(int(row['pid']), signal.SIGKILL)
            killed.append(row)
        except Exception as exc:
            errors.append({'pid': row.get('pid'), 'error': str(exc)})
    ok = not errors
    _log_watchdog_service_action('ollama_kill_runners', f'killed={killed} errors={errors}', 'ok' if ok else 'error')
    return jsonify({'ok': ok, 'killed': killed, 'errors': errors, 'remaining': _ollama_runner_rows()})


@exec_bp.route('/api/exec/write', methods=['POST'])
def api_exec_write():
    """Write a file. Path must be inside the swarm root."""
    data    = request.get_json() or {}
    path    = (data.get('path') or '').strip()
    content = data.get('content', '')
    desc    = (data.get('description') or '').strip()

    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    if not path or not _Path(path).resolve().is_relative_to(_SWARM_ROOT_PATH):
        return jsonify({'error': 'Path must be within swarm root'}), 400
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
