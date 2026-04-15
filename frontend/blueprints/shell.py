"""shell.py — Shell & Terminal routes"""
import os as _os
from pathlib import Path as _Path
from flask import Blueprint, request, Response, jsonify, send_file
from services import *

_SWARM_ROOT = _os.environ.get('SWARM_ROOT',
              str(_Path(__file__).resolve().parent.parent.parent))

shell_bp = Blueprint('shell', __name__)

@shell_bp.route('/api/shell/execute', methods=['POST'])
def api_shell_execute():
    """Execute a whitelisted shell command via shell_agent."""
    from fridays.shell_agent import run as shell_run
    data = request.get_json() or {}
    command = data.get('command', '').strip()

    gate = _alm_gate_or_response(data, 'shell_execute')
    if gate:
        return gate
    
    if not command:
        return jsonify({'ok': False, 'output': 'No command provided', 'message': 'Command is required'}), 400
    
    try:
        success, output = shell_run(command, agent='terminal_ui', notify_ghost=True)
        return jsonify({
            'ok': success,
            'output': output,
            'command': command,
        })
    except Exception as e:
        return jsonify({
            'ok': False,
            'output': f'Error executing command: {str(e)}',
            'command': command,
        }), 500



@shell_bp.route('/api/shell/stream', methods=['POST'])
def api_shell_stream():
    """Execute a whitelisted shell command and stream output via SSE."""
    from fridays import shell_agent as _shell

    data = request.get_json() or {}
    command = str(data.get('command') or '').strip()

    gate = _alm_gate_or_response(data, 'shell_execute')
    if gate:
        return gate

    if not command:
        return jsonify({'ok': False, 'error': 'Command is required'}), 400

    match = _shell._match_whitelist(command)
    if match is None:
        return jsonify({'ok': False, 'error': f'Command not on whitelist: {command[:100]}'}), 403

    max_output = int(getattr(_shell, 'MAX_OUTPUT', 4000))
    timeout_sec = int(getattr(_shell, 'TIMEOUT_SEC', 30))

    def _emit(payload):
        return f"data: {json.dumps(payload)}\n\n"

    def _generate():
        import subprocess
        started = time.time()
        total = 0
        proc = None
        truncated = False
        command_id = uuid.uuid4().hex

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=_SWARM_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            with _SHELL_STREAM_LOCK:
                _SHELL_STREAM_PROCS[command_id] = proc

            yield _emit({'type': 'start', 'command': command, 'command_id': command_id})

            while True:
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if line == '' and proc.poll() is not None:
                    break

                if line:
                    total += len(line)
                    if total > max_output:
                        allowed = max(0, max_output - (total - len(line)))
                        clipped = line[:allowed]
                        if clipped:
                            yield _emit({'type': 'chunk', 'text': clipped})
                        truncated = True
                        proc.kill()
                        break
                    yield _emit({'type': 'chunk', 'text': line})

                if time.time() - started > timeout_sec:
                    proc.kill()
                    yield _emit({'type': 'error', 'error': 'command timed out'})
                    return

            returncode = proc.wait(timeout=1) if proc else 1
            elapsed_ms = int((time.time() - started) * 1000)
            yield _emit({
                'type': 'done',
                'ok': returncode == 0 and not truncated,
                'returncode': returncode,
                'truncated': truncated,
                'elapsed_ms': elapsed_ms,
                'command_id': command_id,
            })
        except Exception as e:
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            yield _emit({'type': 'error', 'error': str(e), 'command_id': command_id})
        finally:
            with _SHELL_STREAM_LOCK:
                _SHELL_STREAM_PROCS.pop(command_id, None)

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )



@shell_bp.route('/api/terminal/run', methods=['POST'])
def api_terminal_run():
    """Alias for /api/shell/execute for backward compatibility."""
    return api_shell_execute()



@shell_bp.route('/api/terminal/stream', methods=['POST'])
def api_terminal_stream():
    """Alias for /api/shell/stream for backward compatibility."""
    return api_shell_stream()



@shell_bp.route('/api/shell/stream/stop', methods=['POST'])
def api_shell_stream_stop():
    """Stop a running shell stream command by command_id."""
    data = request.get_json() or {}
    command_id = str(data.get('command_id') or '').strip()
    if not command_id:
        return jsonify({'ok': False, 'error': 'command_id required'}), 400

    stopped = False
    with _SHELL_STREAM_LOCK:
        proc = _SHELL_STREAM_PROCS.get(command_id)
    if proc and proc.poll() is None:
        try:
            proc.kill()
            stopped = True
        except Exception:
            stopped = False

    return jsonify({'ok': True, 'command_id': command_id, 'stopped': stopped})



@shell_bp.route('/api/terminal/stream/stop', methods=['POST'])
def api_terminal_stream_stop():
    """Alias for /api/shell/stream/stop."""
    return api_shell_stream_stop()



@shell_bp.route('/api/shell/agent-commands', methods=['GET'])
def api_shell_agent_commands():
    """Return running and recently-finished agent shell commands for the terminal tile."""
    from fridays.shell_agent import get_running_commands
    cmds = get_running_commands()
    # Strip internal _proc reference before serialising
    safe = []
    for c in cmds:
        safe.append({k: v for k, v in c.items() if not k.startswith('_')})
    return jsonify({'ok': True, 'commands': safe})


@shell_bp.route('/api/shell/agent-kill', methods=['POST'])
def api_shell_agent_kill():
    """Kill a running agent shell command by cmd_id."""
    from fridays.shell_agent import kill_command
    data = request.get_json() or {}
    cmd_id = str(data.get('cmd_id') or '').strip()
    if not cmd_id:
        return jsonify({'ok': False, 'error': 'cmd_id required'}), 400
    killed = kill_command(cmd_id)
    return jsonify({'ok': True, 'killed': killed, 'cmd_id': cmd_id})


@shell_bp.route('/api/hands/run', methods=['POST'])
def api_hands_run():
    """Alias for /api/shell/execute - named for Ghost/terminal metaphor."""
    return api_shell_execute()



@shell_bp.route('/api/terminal/shortcuts', methods=['GET'])
def api_terminal_shortcuts_get():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, icon, label, cmd, sort_order FROM terminal_shortcuts ORDER BY sort_order ASC, id ASC"
    ).fetchall()
    conn.close()
    return jsonify([{'id': r[0], 'icon': r[1], 'label': r[2], 'cmd': r[3], 'sort_order': r[4]} for r in rows])



@shell_bp.route('/api/terminal/shortcuts', methods=['POST'])
def api_terminal_shortcuts_post():
    data = request.get_json() or {}
    icon  = (data.get('icon')  or '⚡').strip()[:4]
    label = (data.get('label') or '').strip()
    cmd   = (data.get('cmd')   or '').strip()
    sort_order = int(data.get('sort_order') or 0)
    if not label or not cmd:
        return jsonify({'error': 'label and cmd required'}), 400
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO terminal_shortcuts (icon, label, cmd, sort_order) VALUES (?, ?, ?, ?)",
        (icon, label, cmd, sort_order)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'ok': True, 'id': new_id})



@shell_bp.route('/api/terminal/shortcuts/<int:shortcut_id>', methods=['PUT'])
def api_terminal_shortcuts_put(shortcut_id):
    data = request.get_json() or {}
    icon  = (data.get('icon')  or '⚡').strip()[:4]
    label = (data.get('label') or '').strip()
    cmd   = (data.get('cmd')   or '').strip()
    sort_order = int(data.get('sort_order') or 0)
    if not label or not cmd:
        return jsonify({'error': 'label and cmd required'}), 400
    conn = get_connection()
    conn.execute(
        "UPDATE terminal_shortcuts SET icon=?, label=?, cmd=?, sort_order=? WHERE id=?",
        (icon, label, cmd, sort_order, shortcut_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})



@shell_bp.route('/api/terminal/shortcuts/<int:shortcut_id>', methods=['DELETE'])
def api_terminal_shortcuts_delete(shortcut_id):
    conn = get_connection()
    conn.execute("DELETE FROM terminal_shortcuts WHERE id=?", (shortcut_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@shell_bp.route('/api/terminal/sudo-whitelist', methods=['GET'])
def api_terminal_sudo_whitelist_get():
    from fridays.shell_agent import get_effective_whitelist

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, command, note, added_by, created_at FROM sudo_command_whitelist ORDER BY created_at ASC, id ASC"
    ).fetchall()
    conn.close()

    custom = [
        {
            'id': row['id'],
            'command': row['command'],
            'note': row['note'],
            'added_by': row['added_by'],
            'created_at': row['created_at'],
            'source': 'custom',
            'match_type': 'exact',
            'trust_level': 4,
            'description': row['note'] or 'custom sudo whitelist entry',
            'is_custom': True,
            'is_removable': True,
        }
        for row in rows
    ]

    built_in = [item for item in get_effective_whitelist() if not item.get('is_custom')]

    return jsonify({
        'built_in': built_in,
        'custom': custom,
        'all': built_in + custom,
    })


@shell_bp.route('/api/terminal/sudo-whitelist', methods=['POST'])
def api_terminal_sudo_whitelist_post():
    data = request.get_json() or {}
    command = str(data.get('command') or '').strip()
    note = str(data.get('note') or '').strip()[:200]
    added_by = str(data.get('added_by') or 'ghost').strip()[:80] or 'ghost'

    if not command:
        return jsonify({'ok': False, 'error': 'command required'}), 400
    if any(token in command for token in ['&&', '||', ';', '`', '$(']):
        return jsonify({'ok': False, 'error': 'Command chaining and shell substitution are not allowed'}), 400

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM sudo_command_whitelist WHERE command=?",
        (command,)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'ok': False, 'error': 'Command already exists on whitelist'}), 409

    cur = conn.execute(
        "INSERT INTO sudo_command_whitelist (command, note, added_by) VALUES (?, ?, ?)",
        (command, note, added_by)
    )
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute(
        "SELECT id, command, note, added_by, created_at FROM sudo_command_whitelist WHERE id=?",
        (new_id,)
    ).fetchone()
    conn.close()

    return jsonify({
        'ok': True,
        'item': {
            'id': row['id'],
            'command': row['command'],
            'note': row['note'],
            'added_by': row['added_by'],
            'created_at': row['created_at'],
            'source': 'custom',
            'match_type': 'exact',
            'trust_level': 4,
            'description': row['note'] or 'custom sudo whitelist entry',
            'is_custom': True,
            'is_removable': True,
        }
    })


@shell_bp.route('/api/terminal/sudo-whitelist/<int:item_id>', methods=['DELETE'])
def api_terminal_sudo_whitelist_delete(item_id):
    conn = get_connection()
    conn.execute("DELETE FROM sudo_command_whitelist WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'id': item_id})


@shell_bp.route('/api/shell/approve/<token>', methods=['GET', 'POST'])
def api_shell_approve(token):
    """
    Approve a pending sudo shell command via approval token.
    GET shows the command details; POST executes it.
    """
    from database import use_approval_token
    from fridays.shell_agent import run as shell_run

    if request.method == 'GET':
        # Show what the token would do without consuming it
        conn = get_connection()
        row = conn.execute(
            "SELECT action, target_email, status, created_by, created_at "
            "FROM approval_tokens WHERE token=?", (token,)
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({'ok': False, 'error': 'Token not found'}), 404
        if row['status'] != 'pending':
            return jsonify({'ok': False, 'error': f'Token already {row["status"]}'}), 410
        return jsonify({
            'ok': True,
            'action': row['action'],
            'command': row['target_email'],
            'requested_by': row['created_by'],
            'requested_at': row['created_at'],
            'status': 'pending',
            'message': 'POST to this URL to approve and execute.',
        })

    # POST — consume token and execute
    result = use_approval_token(token)
    if not result:
        return jsonify({'ok': False, 'error': 'Invalid, expired, or already-used token'}), 410

    command = result['target_email']
    success, output = shell_run(command, agent='ghost', notify_ghost=True)
    return jsonify({
        'ok': success,
        'command': command,
        'output': output,
        'approved': True,
    })
