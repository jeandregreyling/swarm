"""tasker_bp.py — Scheduled tasks CRUD API for the Tasker UI.

Wraps the existing scheduler.py backend with REST endpoints.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request

from database import get_connection

tasker_bp = Blueprint('tasker', __name__)

# Valid action types
_VALID_ACTION_TYPES = {'SHELL', 'QUESTION', 'BRIEF'}


@tasker_bp.route('/api/tasker/tasks')
def list_tasks():
    """List all scheduled tasks."""
    with get_connection() as conn:
        rows = conn.execute(
            '''SELECT id, name, schedule, action_type, action_data,
                      enabled, created_by, last_run, next_run, created_at
               FROM scheduled_tasks ORDER BY id'''
        ).fetchall()
    tasks = []
    for r in rows:
        tasks.append({
            'id': r[0], 'name': r[1], 'schedule': r[2],
            'action_type': r[3], 'action_data': r[4],
            'enabled': bool(r[5]), 'created_by': r[6],
            'last_run': r[7], 'next_run': r[8], 'created_at': r[9],
        })
    return jsonify(tasks)


@tasker_bp.route('/api/tasker/tasks', methods=['POST'])
def create_task():
    """Create a new scheduled task."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    schedule = (data.get('schedule') or '').strip()
    action_type = (data.get('action_type') or '').strip().upper()
    action_data = (data.get('action_data') or '').strip()

    if not name:
        return jsonify({'ok': False, 'error': 'name is required'}), 400
    if not schedule:
        return jsonify({'ok': False, 'error': 'schedule is required'}), 400
    if action_type not in _VALID_ACTION_TYPES:
        return jsonify({'ok': False, 'error': f'action_type must be one of: {", ".join(sorted(_VALID_ACTION_TYPES))}'}), 400
    if not action_data:
        return jsonify({'ok': False, 'error': 'action_data is required'}), 400

    # Validate schedule format
    if not _validate_schedule(schedule):
        return jsonify({'ok': False, 'error': 'Invalid schedule format. Use: daily HH:MM, hourly, or interval NNm'}), 400

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    next_run = _compute_next_run(schedule)

    with get_connection() as conn:
        existing = conn.execute('SELECT id FROM scheduled_tasks WHERE name=?', (name,)).fetchone()
        if existing:
            return jsonify({'ok': False, 'error': f'Task "{name}" already exists'}), 409

        conn.execute(
            '''INSERT INTO scheduled_tasks (name, schedule, action_type, action_data, enabled, created_by, created_at, next_run)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?)''',
            (name, schedule, action_type, action_data, data.get('created_by', 'ghost'), now, next_run)
        )
        task_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    return jsonify({'ok': True, 'id': task_id, 'name': name})


@tasker_bp.route('/api/tasker/tasks/<int:task_id>', methods=['PATCH'])
def update_task(task_id):
    """Update a scheduled task (enable/disable, change schedule, etc.)."""
    data = request.get_json(silent=True) or {}

    with get_connection() as conn:
        row = conn.execute('SELECT id FROM scheduled_tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404

        updates = []
        params = []

        if 'enabled' in data:
            updates.append('enabled=?')
            params.append(1 if data['enabled'] else 0)

        if 'name' in data:
            name = (data['name'] or '').strip()
            if name:
                updates.append('name=?')
                params.append(name)

        if 'schedule' in data:
            schedule = (data['schedule'] or '').strip()
            if schedule and _validate_schedule(schedule):
                updates.append('schedule=?')
                params.append(schedule)
                updates.append('next_run=?')
                params.append(_compute_next_run(schedule))

        if 'action_type' in data:
            at = (data['action_type'] or '').strip().upper()
            if at in _VALID_ACTION_TYPES:
                updates.append('action_type=?')
                params.append(at)

        if 'action_data' in data:
            ad = (data['action_data'] or '').strip()
            if ad:
                updates.append('action_data=?')
                params.append(ad)

        if not updates:
            return jsonify({'ok': True, 'changed': False})

        params.append(task_id)
        conn.execute(f'UPDATE scheduled_tasks SET {", ".join(updates)} WHERE id=?', params)

    return jsonify({'ok': True, 'changed': True})


@tasker_bp.route('/api/tasker/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Delete a scheduled task."""
    with get_connection() as conn:
        row = conn.execute('SELECT id FROM scheduled_tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404
        conn.execute('DELETE FROM scheduled_tasks WHERE id=?', (task_id,))
    return jsonify({'ok': True})


@tasker_bp.route('/api/tasker/tasks/<int:task_id>/run', methods=['POST'])
def run_task_now(task_id):
    """Trigger a task to run immediately (resets next_run)."""
    import subprocess

    with get_connection() as conn:
        row = conn.execute(
            'SELECT id, name, action_type, action_data, schedule FROM scheduled_tasks WHERE id=?',
            (task_id,)
        ).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404

        _, name, action_type, action_data, schedule = row
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            if action_type.upper() == 'SHELL':
                subprocess.Popen(action_data, shell=True)
            elif action_type.upper() == 'BRIEF':
                subprocess.Popen(action_data, shell=True)
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

        next_run = _compute_next_run(schedule)
        conn.execute(
            'UPDATE scheduled_tasks SET last_run=?, next_run=? WHERE id=?',
            (now, next_run, task_id)
        )

    return jsonify({'ok': True, 'fired': name})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_schedule(schedule):
    """Validate schedule format: 'daily HH:MM', 'hourly', 'interval NNm'."""
    s = schedule.lower().strip()
    if s.startswith('daily '):
        parts = s.split(None, 1)
        if len(parts) < 2:
            return False
        hhmm = parts[1]
        try:
            h, m = hhmm.split(':')
            return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except (ValueError, IndexError):
            return False
    if s == 'hourly':
        return True
    if s.startswith('interval '):
        parts = s.split(None, 1)
        if len(parts) < 2:
            return False
        val = parts[1].rstrip('m')
        try:
            return int(val) > 0
        except ValueError:
            return False
    return False


def _compute_next_run(schedule):
    """Compute the next run time from a schedule string."""
    from datetime import timedelta
    s = schedule.lower().strip()
    now = datetime.now()

    if s.startswith('daily '):
        try:
            hhmm = s.split(None, 1)[1]
            h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    elif s == 'hourly':
        candidate = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return candidate.strftime('%Y-%m-%d %H:%M:%S')
    elif s.startswith('interval '):
        try:
            val = int(s.split(None, 1)[1].rstrip('m'))
            candidate = now + timedelta(minutes=val)
            return candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

    return (now + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
