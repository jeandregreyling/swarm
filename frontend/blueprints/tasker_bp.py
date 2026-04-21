"""tasker_bp.py — Scheduled tasks CRUD API for the Tasker UI.

Wraps the existing scheduler.py backend with REST endpoints.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request

tasker_bp = Blueprint('tasker', __name__)

# Valid action types
_VALID_ACTION_TYPES = {'SHELL', 'QUESTION', 'BRIEF', 'PYTHON'}


def _get_conn():
    from database import get_connection
    return get_connection()


@tasker_bp.route('/api/tasker/tasks')
def list_tasks():
    """List all scheduled tasks."""
    with _get_conn() as conn:
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
        return jsonify({'ok': False, 'error': 'Invalid schedule format. Use: daily HH:MM, weekly DAY HH:MM, monthly DD HH:MM, hourly, or interval NNm'}), 400

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    next_run = _compute_next_run(schedule)

    with _get_conn() as conn:
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

    with _get_conn() as conn:
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
    with _get_conn() as conn:
        row = conn.execute('SELECT id FROM scheduled_tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404
        conn.execute('DELETE FROM scheduled_tasks WHERE id=?', (task_id,))
    return jsonify({'ok': True})


@tasker_bp.route('/api/tasker/tasks/<int:task_id>/run', methods=['POST'])
def run_task_now(task_id):
    """Trigger a task to run immediately (resets next_run)."""
    import shlex
    import subprocess

    with _get_conn() as conn:
        row = conn.execute(
            'SELECT id, name, action_type, action_data, schedule FROM scheduled_tasks WHERE id=?',
            (task_id,)
        ).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404

        _, name, action_type, action_data, schedule = row
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            if action_type.upper() == 'PYTHON':
                from fridays.task_runner import run_task
                success, output = run_task(action_data.strip())
                if not success:
                    return jsonify({'ok': False, 'error': output}), 500
            elif action_type.upper() in ('SHELL', 'BRIEF'):
                subprocess.Popen(shlex.split(action_data))
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

        next_run = _compute_next_run(schedule)
        conn.execute(
            'UPDATE scheduled_tasks SET last_run=?, next_run=? WHERE id=?',
            (now, next_run, task_id)
        )

    return jsonify({'ok': True, 'fired': name})


@tasker_bp.route('/api/tasker/registered')
def list_registered_tasks():
    """List all registered Python tasks from the task runner."""
    from fridays.task_runner import list_registered
    return jsonify(list_registered())


@tasker_bp.route('/api/tasker/history')
def task_history():
    """Return recent task execution history."""
    limit = min(int(request.args.get('limit', 50)), 200)
    with _get_conn() as conn:
        rows = conn.execute(
            'SELECT id, task_name, status, output, run_at FROM task_run_log ORDER BY id DESC LIMIT ?',
            (limit,)
        ).fetchall()
    history = [
        {'id': r[0], 'task_name': r[1], 'status': r[2], 'output': r[3], 'run_at': r[4]}
        for r in rows
    ]
    return jsonify(history)


@tasker_bp.route('/api/tasker/bootstrap', methods=['POST'])
def bootstrap_tasks():
    """Register built-in PYTHON tasks into scheduled_tasks if missing.

    This creates sensible default schedules for housekeeping, knowledge sync,
    digest, etc. Safe to call multiple times — uses INSERT OR IGNORE.
    """
    from fridays.scheduler import add_task

    defaults = [
        ('housekeeping',    'weekly Sun 02:00',  'PYTHON', 'housekeeping'),
        ('dedup_memories',  'daily 03:00',       'PYTHON', 'dedup_memories'),
        ('sla_check',       'interval 60m',      'PYTHON', 'sla_check'),
        ('snoozed_check',   'interval 15m',      'PYTHON', 'snoozed_check'),
        ('proposals_check', 'interval 30m',      'PYTHON', 'proposals_check'),
        ('landscape_refresh','weekly Mon 04:00',  'PYTHON', 'landscape_refresh'),
        ('knowledge_seed',  'monthly 1 03:00',   'PYTHON', 'knowledge_seed'),
    ]
    added = 0
    for name, schedule, action_type, action_data in defaults:
        add_task(name, schedule, action_type, action_data, created_by='system')
        added += 1

    # Also ensure existing shell tasks get migrated to PYTHON where possible
    with _get_conn() as conn:
        # Update daily_digest if it's currently SHELL
        conn.execute(
            "UPDATE scheduled_tasks SET action_type='PYTHON', action_data='daily_digest' "
            "WHERE name='daily_digest' AND action_type='SHELL'"
        )
        conn.execute(
            "UPDATE scheduled_tasks SET action_type='PYTHON', action_data='daily_brief' "
            "WHERE name='daily_brief' AND action_type='SHELL'"
        )

    return jsonify({'ok': True, 'bootstrapped': added})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_schedule(schedule):
    """Validate schedule format: 'daily HH:MM', 'weekly DAY HH:MM', 'monthly DD HH:MM', 'hourly', 'interval NNm'."""
    s = schedule.lower().strip()
    if s.startswith('daily '):
        parts = s.split(None, 1)
        if len(parts) < 2:
            return False
        return _valid_hhmm(parts[1])
    if s.startswith('weekly '):
        parts = s.split(None, 2)
        if len(parts) < 2:
            return False
        valid_days = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}
        if parts[1][:3] not in valid_days:
            return False
        if len(parts) > 2:
            return _valid_hhmm(parts[2])
        return True
    if s.startswith('monthly '):
        parts = s.split(None, 2)
        if len(parts) < 2:
            return False
        try:
            day = int(parts[1])
            if not (1 <= day <= 28):
                return False
        except ValueError:
            return False
        if len(parts) > 2:
            return _valid_hhmm(parts[2])
        return True
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


def _valid_hhmm(hhmm):
    """Validate HH:MM format."""
    try:
        h, m = hhmm.split(':')
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except (ValueError, IndexError):
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
    elif s.startswith('weekly '):
        try:
            parts = s.split(None, 2)
            day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
            target_day = day_map.get(parts[1][:3], 0)
            hhmm = parts[2] if len(parts) > 2 else '09:00'
            h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            candidate += timedelta(days=days_ahead)
            return candidate.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    elif s.startswith('monthly '):
        try:
            parts = s.split(None, 2)
            day_of_month = int(parts[1])
            hhmm = parts[2] if len(parts) > 2 else '09:00'
            h, m = int(hhmm.split(':')[0]), int(hhmm.split(':')[1])
            candidate = now.replace(day=min(day_of_month, 28), hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                month = now.month + 1
                year = now.year
                if month > 12:
                    month = 1
                    year += 1
                candidate = candidate.replace(year=year, month=month)
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
