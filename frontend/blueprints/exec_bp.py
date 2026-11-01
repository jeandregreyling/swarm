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
    {'id': 'swarm-vortex-backup.timer', 'label': 'Vortex Memory Backup (daily)', 'env': 'SHARED',
     'kind': 'maintenance', 'scope': 'user'},
    {'id': 'ollama.service', 'label': 'Ollama Runtime (unused)', 'env': 'RUNTIME', 'kind': 'runtime'},
]

# Units that run inside this process; restarting them must not block the request.
_SELF_UNITS = {'swarm-terminal.service'}
_SYSTEMCTL = '/usr/bin/systemctl'
_SUDO_HINT = (
    'passwordless restart is not set up for system services. '
    'Run once in a terminal: sudo scripts/install_service_sudoers.sh'
)


def _service_by_id(service_id):
    service_id = str(service_id or '').strip()
    for svc in _SERVICE_REGISTRY:
        if svc['id'] == service_id:
            return dict(svc)
    return None


def _user_bus_env():
    env = dict(_os.environ)
    runtime_dir = env.get('XDG_RUNTIME_DIR') or f'/run/user/{_os.getuid()}'
    env['XDG_RUNTIME_DIR'] = runtime_dir
    env.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path={runtime_dir}/bus')
    return env


def _run_systemctl(args, timeout=20, scope='system'):
    """Run systemctl for a registry unit. System units go through `sudo -n` so a
    missing sudoers rule fails immediately instead of waiting for a password."""
    import subprocess as _sp
    if scope == 'user':
        cmd, env = [_SYSTEMCTL, '--user'] + list(args), _user_bus_env()
    else:
        cmd, env = ['sudo', '-n', _SYSTEMCTL] + list(args), None
    result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    output = (result.stdout + result.stderr).strip() or '(done)'
    if result.returncode != 0 and scope != 'user' and 'password is required' in output:
        output = _SUDO_HINT
    return result.returncode == 0, output


def _unit_state(unit, scope='system'):
    import subprocess as _sp
    cmd = [_SYSTEMCTL] + (['--user'] if scope == 'user' else []) + [
        'show', unit, '-p', 'LoadState,ActiveState,SubState,UnitFileState']
    try:
        r = _sp.run(cmd, capture_output=True, text=True, timeout=4,
                    env=_user_bus_env() if scope == 'user' else None)
        props = dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)
    except Exception:
        props = {}
    return props


def _service_payload(svc):
    scope = svc.get('scope', 'system')
    props = _unit_state(svc['id'], scope)
    installed = props.get('LoadState') == 'loaded'
    active_state = props.get('ActiveState') or 'unknown'
    status = active_state if installed else 'not installed'
    if installed and props.get('SubState') and props['SubState'] not in {active_state, 'running', 'dead'}:
        status = f"{active_state} ({props['SubState']})"
    return {
        'scope': scope,
        **svc,
        'active': installed and active_state == 'active',
        'status': status,
        'enabled': props.get('UnitFileState') or ('not-found' if not installed else 'static'),
        'installed': installed,
        'can_restart': installed,
        'can_hard_restart': installed and svc['id'].endswith('.service'),
    }


def _restart_unit(svc, hard=False):
    """Returns (ok, output, action)."""
    scope = svc.get('scope', 'system')
    unit = svc['id']
    if unit in _SELF_UNITS:
        # This process is inside the unit: queue the job and answer before systemd kills us.
        ok, out = _run_systemctl(['restart', '--no-block', unit], timeout=10, scope=scope)
        return ok, out, 'service_self_restart'
    if hard:
        kill_ok, kill_out = _run_systemctl(['kill', '-s', 'SIGKILL', unit], timeout=12, scope=scope)
        start_ok, start_out = _run_systemctl(['start', unit], timeout=20, scope=scope)
        return start_ok, f'kill={kill_ok}: {kill_out}\nstart={start_ok}: {start_out}', 'service_hard_restart'
    ok, out = _run_systemctl(['restart', unit], timeout=20, scope=scope)
    return ok, out, 'service_restart'


def _llama_resident_rows():
    try:
        from core.seven_llm import llama_server
        rows = []
        for item in llama_server.resident_models():
            rows.append({k: item.get(k) for k in ('model', 'port', 'pid', 'gpu', 'ram_gb', 'idle_seconds')})
        return rows
    except Exception:
        return []


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
    if not _service_payload(svc)['installed']:
        return jsonify({'ok': False, 'output': f"{svc['id']} is not installed on this machine"}), 404
    try:
        ok, output, action = _restart_unit(svc, hard)
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
    residents = _llama_resident_rows()
    result.append({
        'id': 'llama-server',
        'label': 'Local models (llama-server)',
        'env': 'RUNTIME',
        'kind': 'runtime',
        'scope': 'user',
        'active': True,
        'status': f'{len(residents)} loaded',
        'enabled': 'on demand',
        'installed': True,
        'can_restart': False,
        'can_hard_restart': False,
        'can_stop_models': True,
        'models': residents,
    })
    runners = _ollama_runner_rows()
    if runners:
        result.append({
            'id': 'ollama-runners',
            'label': 'Ollama Runners',
            'env': 'RUNTIME',
            'kind': 'runtime',
            'active': True,
            'status': f'{len(runners)} runner(s)',
            'enabled': 'runtime',
            'installed': True,
            'can_restart': False,
            'can_hard_restart': False,
            'can_kill': True,
            'runners': runners,
        })
    return jsonify(result)


@exec_bp.route('/api/services/llama/stop', methods=['POST'])
def api_llama_stop():
    """Unload one llama-server model (or all when no model is given)."""
    data = request.get_json(silent=True) or {}
    model = str(data.get('model') or '').strip() or None
    try:
        from core.seven_llm import llama_server
        if model:
            stopped = llama_server.stop(model)
        else:
            stopped = sum(llama_server.stop(row['model']) for row in llama_server.resident_models())
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    _log_watchdog_service_action('llama_stop', f'model={model or "all"} stopped={stopped}')
    return jsonify({'ok': True, 'stopped': stopped, 'remaining': _llama_resident_rows()})


@exec_bp.route('/api/services/restart-all', methods=['POST'])
def api_services_restart_all():
    """Restart all known services for an environment group."""
    data = request.get_json(silent=True) or {}
    env = str(data.get('env') or 'PROD').strip().upper()
    hard = bool(data.get('hard'))
    if env not in {'PROD', 'DEV', 'UAT', 'SHARED', 'RUNTIME'}:
        return jsonify({'ok': False, 'error': 'Invalid env'}), 400
    targets = [svc for svc in _SERVICE_REGISTRY if svc['env'] == env and _service_payload(svc)['installed']]
    # Restart ourselves last so the other results are collected first.
    targets.sort(key=lambda svc: svc['id'] in _SELF_UNITS)
    results = []
    for svc in targets:
        try:
            ok, output, _action = _restart_unit(svc, hard)
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
