"""tasker_bp.py — Scheduled tasks CRUD API for the Tasker UI.

Wraps the existing scheduler.py backend with REST endpoints.
"""

import re
import shlex
from datetime import datetime

from flask import Blueprint, jsonify, request

tasker_bp = Blueprint('tasker', __name__)

# Valid action types
_VALID_ACTION_TYPES = {'SHELL', 'QUESTION', 'BRIEF', 'PYTHON'}


def _get_conn():
    try:
        from database import get_connection
    except ModuleNotFoundError:
        from utils.db._connection import get_connection
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
    with _get_conn() as conn:
        row = conn.execute(
            'SELECT id, name, action_type, action_data, schedule FROM scheduled_tasks WHERE id=?',
            (task_id,)
        ).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404

        _, name, action_type, action_data, schedule = row
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        success, output = _execute_task_action(action_type, action_data)
        if not success:
            return jsonify({'ok': False, 'error': output}), 500

        next_run = _compute_next_run(schedule)
        conn.execute(
            'UPDATE scheduled_tasks SET last_run=?, next_run=? WHERE id=?',
            (now, next_run, task_id)
        )

    return jsonify({'ok': True, 'fired': name, 'output': output})


@tasker_bp.route('/api/tasker/tasks/<int:task_id>/dry-run', methods=['POST'])
def dry_run_task(task_id):
    """Resolve a task to its concrete invocation WITHOUT executing it.

    S-A4249B4159 — lets the user inspect what a scheduled task will actually
    do (registered handler + parsed args + computed next_run) before firing
    it for real. Side-effect free: does not call _execute_task_action and
    does not touch last_run / next_run on the row.
    """
    with _get_conn() as conn:
        row = conn.execute(
            'SELECT id, name, action_type, action_data, schedule, last_run, next_run, enabled '
            'FROM scheduled_tasks WHERE id=?',
            (task_id,)
        ).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': 'Task not found'}), 404

    _id, name, action_type, action_data, schedule, last_run, next_run, enabled = row
    at = str(action_type or '').strip().upper()
    resolved = {
        'task_id': _id,
        'name': name,
        'action_type': at,
        'schedule': schedule,
        'enabled': bool(enabled),
        'last_run': last_run,
        'current_next_run': next_run,
        'projected_next_run': _compute_next_run(schedule),
    }

    if at == 'PYTHON':
        parts = shlex.split(str(action_data or '').strip())
        task_name = parts[0] if parts else ''
        task_args = parts[1:]
        try:
            from fridays.task_runner import list_registered
            registered = {t.get('name'): t for t in (list_registered() or [])}
        except Exception:
            registered = {}
        handler = registered.get(task_name) or {}
        resolved['handler'] = {
            'name': task_name,
            'registered': bool(handler),
            'callable': handler.get('callable') or handler.get('func') or None,
            'description': handler.get('description') or handler.get('doc') or '',
            'parsed_args': task_args,
        }
        resolved['would_execute'] = bool(handler)
        if not handler:
            resolved['warning'] = (
                f'Python task "{task_name}" is NOT registered with task_runner. '
                'Running this task would fail.'
            )
    elif at in ('SHELL', 'BRIEF'):
        try:
            argv = shlex.split(str(action_data or '').strip())
        except ValueError as exc:
            return jsonify({'ok': False, 'error': f'shlex parse error: {exc}'}), 400
        resolved['handler'] = {
            'argv': argv,
            'argv_count': len(argv),
            'binary': argv[0] if argv else None,
        }
        resolved['would_execute'] = bool(argv)
        if not argv:
            resolved['warning'] = 'Empty argv — nothing would be executed.'
    else:
        resolved['handler'] = {}
        resolved['would_execute'] = False
        resolved['warning'] = f'Unsupported action_type: {action_type!r}'

    return jsonify({'ok': True, 'dry_run': True, 'resolved': resolved})


@tasker_bp.route('/api/tasker/registered')
def list_registered_tasks():
    """List all registered Python tasks from the task runner."""
    from fridays.task_runner import list_registered
    return jsonify(list_registered())


@tasker_bp.route('/api/tasker/history')
def task_history():
    """Return recent task execution history.

    2026-05-02 (S-C75D565260) — supports filters:
        ?task=name           filter by task_name (exact match)
        ?status=ok|error     filter by status
        ?since=ISO8601       only rows with run_at >= since
        ?limit=N             cap rows (max 200)
    """
    limit = min(int(request.args.get('limit', 50)), 200)
    task_filter = (request.args.get('task') or '').strip()
    status_filter = (request.args.get('status') or '').strip()
    since_filter = (request.args.get('since') or '').strip()
    where, vals = [], []
    if task_filter:
        where.append('task_name = ?')
        vals.append(task_filter)
    if status_filter and status_filter in ('ok', 'error'):
        where.append('status = ?')
        vals.append(status_filter)
    if since_filter:
        where.append('run_at >= ?')
        vals.append(since_filter)
    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''
    with _get_conn() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(task_run_log)").fetchall()}
        select_cols = 'id, task_name, status, output, run_at'
        if 'duration_ms' in cols:
            select_cols += ', duration_ms'
        if 'details_json' in cols:
            select_cols += ', details_json'
        rows = conn.execute(
            f'SELECT {select_cols} FROM task_run_log{where_sql} '
            f'ORDER BY id DESC LIMIT ?',
            (*vals, limit)
        ).fetchall()
    history = []
    for r in rows:
        item = {'id': r[0], 'task_name': r[1], 'status': r[2],
                'output': r[3], 'run_at': r[4]}
        idx = 5
        if 'duration_ms' in cols:
            item['duration_ms'] = r[idx] or 0
            idx += 1
        if 'details_json' in cols:
            item['details_json'] = r[idx] or ''
        history.append(item)
    return jsonify(history)


@tasker_bp.route('/api/tasker/health')
def tasker_health():
    """2026-05-02 (S-F8A20353D0) — health metrics including duplicate task names.

    Duplicates can silently steal each other's runs because schedulers may
    fire either copy depending on iteration order. This endpoint exposes
    them so they're visible in the UI."""
    with _get_conn() as conn:
        dup_rows = conn.execute(
            "SELECT name, COUNT(*) c FROM scheduled_tasks "
            "WHERE name != '' GROUP BY name HAVING c > 1 ORDER BY c DESC"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM scheduled_tasks").fetchone()[0]
        enabled = conn.execute("SELECT COUNT(*) FROM scheduled_tasks WHERE enabled=1").fetchone()[0]
        recent_failures = conn.execute(
            "SELECT COUNT(*) FROM task_run_log "
            "WHERE status != 'ok' AND run_at > datetime('now','-24 hours')"
        ).fetchone()[0]
    return jsonify({
        'ok': True,
        'total_tasks': total,
        'enabled_tasks': enabled,
        'duplicate_count': len(dup_rows),
        'duplicates': [{'name': r[0], 'count': r[1]} for r in dup_rows],
        'failures_24h': recent_failures,
    })


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
        ('documentation_governance_sweep', 'weekly Mon 03:40', 'PYTHON', 'documentation_governance_sweep'),
        ('relay_recovery_sweep', 'interval 10m', 'PYTHON', 'relay_recovery_sweep limit=1 run_agents=1 force=1'),
        ('money_hub_daily_newsletter', 'daily 07:20', 'PYTHON', 'money_hub_daily_newsletter'),
    ]
    defaults.extend(_default_watched_topic_tasks())
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


@tasker_bp.route('/api/tasker/watch-topic', methods=['POST'])
def create_watched_topic_task():
    """Create/update a saved interest and its scheduled watched-topic task."""
    data = request.get_json(silent=True) or {}
    topic = str(data.get('topic') or '').strip()
    if not topic:
        return jsonify({'ok': False, 'error': 'topic is required'}), 400

    schedule = str(data.get('schedule') or 'daily 06:30').strip()
    if not _validate_schedule(schedule):
        return jsonify({'ok': False, 'error': 'Invalid schedule format. Use: daily HH:MM, weekly DAY HH:MM, monthly DD HH:MM, hourly, or interval NNm'}), 400

    depth = str(data.get('depth') or 'standard').strip().lower()
    if depth not in {'quick', 'standard', 'deep'}:
        return jsonify({'ok': False, 'error': 'depth must be quick, standard, or deep'}), 400

    agent = str(data.get('agent') or 'eight').strip().lower() or 'eight'
    email = str(data.get('email') or 'ghost').strip() or 'ghost'
    category = str(data.get('category') or 'watched_research').strip() or 'watched_research'
    created_by = str(data.get('created_by') or 'ghost').strip() or 'ghost'
    try:
        score = max(0.0, min(float(data.get('score') or 8.0), 10.0))
        min_quality = _bounded_float(data.get('min_quality'), 0.45, 0.0, 1.0)
        min_novelty = _bounded_float(data.get('min_novelty'), 0.35, 0.0, 1.0)
        min_score = _bounded_float(data.get('min_score'), 0.50, 0.0, 1.0)
        max_items = max(1, min(int(data.get('max_items') or 10), 25))
        historical_years = max(1, min(int(data.get('historical_years') or 5), 50))
    except Exception:
        return jsonify({'ok': False, 'error': 'score, thresholds, max items, and historical years must be numeric'}), 400

    explicit_name = str(data.get('name') or '').strip()
    task_name = explicit_name or f'{_slug_topic(topic)}_watch'
    action_data = _watched_topic_action_data(
        topic=topic,
        depth=depth,
        agent=agent,
        email=email,
        min_quality=min_quality,
        min_novelty=min_novelty,
        min_score=min_score,
        max_items=max_items,
        historical_years=historical_years,
    )
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    next_run = _compute_next_run(schedule)

    with _get_conn() as conn:
        interest = conn.execute(
            'SELECT id FROM user_interests WHERE username=? AND topic=?',
            ('ghost', topic),
        ).fetchone()
        if interest:
            interest_id = interest[0]
            conn.execute(
                """UPDATE user_interests
                   SET category=?, source='user', source_agent=?, score=?,
                       active=1, updated_at=datetime('now')
                   WHERE id=?""",
                (category, agent, score, interest_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO user_interests
                   (username, topic, category, source, source_agent, score, active)
                   VALUES ('ghost', ?, ?, 'user', ?, ?, 1)""",
                (topic, category, agent, score),
            )
            interest_id = cur.lastrowid

        task = None
        if not explicit_name:
            task = _find_existing_watched_topic_task(conn, topic)
            if task:
                task_name = task[1]
        if not task:
            task = conn.execute('SELECT id, name FROM scheduled_tasks WHERE name=?', (task_name,)).fetchone()
        if task:
            task_id = task[0]
            conn.execute(
                """UPDATE scheduled_tasks
                   SET schedule=?, action_type='PYTHON', action_data=?,
                       enabled=1, created_by=?, next_run=COALESCE(?, next_run)
                   WHERE id=?""",
                (schedule, action_data, created_by, next_run, task_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO scheduled_tasks
                   (name, schedule, action_type, action_data, enabled,
                    created_by, created_at, next_run)
                   VALUES (?, ?, 'PYTHON', ?, 1, ?, ?, ?)""",
                (task_name, schedule, action_data, created_by, now, next_run),
            )
            task_id = cur.lastrowid
        conn.commit()

    return jsonify({
        'ok': True,
        'interest_id': interest_id,
        'task_id': task_id,
        'name': task_name,
        'schedule': schedule,
        'action_data': action_data,
    })


@tasker_bp.route('/api/tasker/watch-topic/run-now', methods=['POST'])
def run_watched_topic_now():
    """Run an existing watched-topic task immediately and return fresh evidence."""
    data = request.get_json(silent=True) or {}
    topic = str(data.get('topic') or '').strip()
    if not topic:
        return jsonify({'ok': False, 'error': 'topic is required'}), 400

    with _get_conn() as conn:
        task = _find_existing_watched_topic_task(conn, topic)
        if not task:
            return jsonify({'ok': False, 'error': 'No watched-topic task exists for this topic'}), 404
        task_id = task[0]
        row = conn.execute(
            'SELECT id, name, action_type, action_data, schedule FROM scheduled_tasks WHERE id=?',
            (task_id,),
        ).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Watched-topic task not found'}), 404

    success, output = _execute_task_action(row['action_type'], row['action_data'])
    if not success:
        return jsonify({'ok': False, 'error': output, 'task_id': row['id'], 'name': row['name']}), 500

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _get_conn() as conn:
        _ensure_watched_topic_evidence_schema(conn)
        conn.execute(
            'UPDATE scheduled_tasks SET last_run=?, next_run=? WHERE id=?',
            (now, _compute_next_run(row['schedule']), row['id']),
        )
        evidence_rows = conn.execute(
            """SELECT id, topic, source_url, title, snippet, quality_score,
                      novelty_score, combined_score, qualified, notified,
                      review_status, review_note, evidence_date, recency_score,
                      recency_label, is_historical, reason, session_id,
                      created_at, updated_at
               FROM watched_topic_evidence
               WHERE topic_key=?
               ORDER BY updated_at DESC, id DESC
               LIMIT 25""",
            (_watched_topic_key(topic),),
        ).fetchall()
        conn.commit()

    return jsonify({
        'ok': True,
        'task_id': row['id'],
        'name': row['name'],
        'topic': topic,
        'output': output,
        'evidence': [_watched_evidence_row(item) for item in evidence_rows],
    })


@tasker_bp.route('/api/tasker/watch-topic/evidence')
def list_watched_topic_evidence():
    """List scored watched-topic evidence for Studio review."""
    topic = str(request.args.get('topic') or '').strip()
    status = str(request.args.get('status') or 'all').strip().lower()
    if status not in {'all', 'qualified', 'filtered', 'historical', 'notified', 'unnotified'}:
        return jsonify({'ok': False, 'error': 'status must be all, qualified, filtered, historical, notified, or unnotified'}), 400
    try:
        limit = max(1, min(int(request.args.get('limit') or 25), 100))
    except Exception:
        limit = 25

    clauses = []
    params = []
    if topic:
        clauses.append('topic_key=?')
        params.append(_watched_topic_key(topic))
    if status == 'qualified':
        clauses.append('qualified=1')
    elif status == 'filtered':
        clauses.append('qualified=0 AND is_historical=0')
    elif status == 'historical':
        clauses.append('is_historical=1')
    elif status == 'notified':
        clauses.append('notified=1')
    elif status == 'unnotified':
        clauses.append('notified=0')

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    with _get_conn() as conn:
        _ensure_watched_topic_evidence_schema(conn)
        rows = conn.execute(
            f"""SELECT id, topic, source_url, title, snippet, quality_score,
                       novelty_score, combined_score, qualified, notified,
                       review_status, review_note, evidence_date, recency_score,
                       recency_label, is_historical, reason, session_id,
                       created_at, updated_at
                FROM watched_topic_evidence
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?""",
            params + [limit],
        ).fetchall()
        topic_rows = conn.execute(
            """SELECT topic, topic_key, COUNT(*) AS total,
                      SUM(CASE WHEN qualified=1 THEN 1 ELSE 0 END) AS qualified_count,
                      SUM(CASE WHEN notified=1 THEN 1 ELSE 0 END) AS notified_count,
                      SUM(CASE WHEN is_historical=1 THEN 1 ELSE 0 END) AS historical_count,
                      MAX(updated_at) AS last_seen
               FROM watched_topic_evidence
               GROUP BY topic_key, topic
               ORDER BY last_seen DESC
               LIMIT 25"""
        ).fetchall()

    evidence = [_watched_evidence_row(row) for row in rows]
    topics = [
        {
            'topic': row['topic'],
            'topic_key': row['topic_key'],
            'total': int(row['total'] or 0),
            'qualified_count': int(row['qualified_count'] or 0),
            'notified_count': int(row['notified_count'] or 0),
            'historical_count': int(row['historical_count'] or 0),
            'last_seen': row['last_seen'],
        }
        for row in topic_rows
    ]
    return jsonify({'ok': True, 'evidence': evidence, 'topics': topics})


@tasker_bp.route('/api/tasker/watch-topic/evidence/<int:evidence_id>', methods=['PATCH'])
def update_watched_topic_evidence(evidence_id):
    """Operator review controls for watched-topic evidence rows."""
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').strip().lower()
    note = str(data.get('note') or '').strip()[:500]
    if action not in {'promote', 'ignore', 'reset', 'mark_notified', 'mark_unnotified'}:
        return jsonify({'ok': False, 'error': 'action must be promote, ignore, reset, mark_notified, or mark_unnotified'}), 400

    with _get_conn() as conn:
        _ensure_watched_topic_evidence_schema(conn)
        row = conn.execute(
            "SELECT id FROM watched_topic_evidence WHERE id=?",
            (evidence_id,),
        ).fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Evidence row not found'}), 404

        if action == 'promote':
            conn.execute(
                """UPDATE watched_topic_evidence
                   SET qualified=1, review_status='promoted',
                       review_note=?, reason=?, updated_at=datetime('now')
                   WHERE id=?""",
                (note, note or 'promoted by operator review', evidence_id),
            )
        elif action == 'ignore':
            conn.execute(
                """UPDATE watched_topic_evidence
                   SET qualified=0, review_status='ignored',
                       review_note=?, reason=?, updated_at=datetime('now')
                   WHERE id=?""",
                (note, note or 'ignored by operator review', evidence_id),
            )
        elif action == 'reset':
            conn.execute(
                """UPDATE watched_topic_evidence
                   SET review_status='', review_note='', updated_at=datetime('now')
                   WHERE id=?""",
                (evidence_id,),
            )
        elif action == 'mark_notified':
            conn.execute(
                """UPDATE watched_topic_evidence
                   SET notified=1, review_status='notified',
                       review_note=COALESCE(NULLIF(?, ''), review_note),
                       updated_at=datetime('now')
                   WHERE id=?""",
                (note, evidence_id),
            )
        elif action == 'mark_unnotified':
            conn.execute(
                """UPDATE watched_topic_evidence
                   SET notified=0, review_status='unnotified',
                       review_note=COALESCE(NULLIF(?, ''), review_note),
                       updated_at=datetime('now')
                   WHERE id=?""",
                (note, evidence_id),
            )
        conn.commit()
        updated = conn.execute(
            """SELECT id, topic, source_url, title, snippet, quality_score,
                      novelty_score, combined_score, qualified, notified,
                      review_status, review_note, evidence_date, recency_score,
                      recency_label, is_historical, reason, session_id,
                      created_at, updated_at
               FROM watched_topic_evidence
               WHERE id=?""",
            (evidence_id,),
        ).fetchone()

    return jsonify({'ok': True, 'evidence': _watched_evidence_row(updated)})


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


def _execute_task_action(action_type, action_data):
    import subprocess

    try:
        at = str(action_type or '').strip().upper()
        if at == 'PYTHON':
            parts = shlex.split(str(action_data or '').strip())
            task_name = parts[0] if parts else ''
            task_args = ' '.join(shlex.quote(p) for p in parts[1:])
            from fridays.task_runner import run_task
            return run_task(task_name, args=task_args)
        if at in ('SHELL', 'BRIEF'):
            subprocess.Popen(shlex.split(str(action_data or '').strip()))
            return True, 'Process started.'
        return False, f'Unsupported action_type: {action_type}'
    except Exception as e:
        return False, str(e)


def _bounded_float(value, default, low, high):
    raw = default if value in (None, '') else value
    return max(low, min(float(raw), high))


def _slug_topic(topic):
    slug = re.sub(r'[^a-z0-9]+', '_', str(topic or '').lower()).strip('_')
    return slug[:64] or 'watched_topic'


def _watched_topic_action_data(
    *,
    topic,
    depth,
    agent,
    email,
    min_quality,
    min_novelty,
    min_score,
    max_items,
    historical_years=5,
):
    parts = [
        'interest_research_update',
        shlex.quote(f'topic={topic}'),
        shlex.quote(f'depth={depth}'),
        shlex.quote(f'agent={agent}'),
        shlex.quote(f'email={email}'),
        shlex.quote(f'min_quality={float(min_quality):.2f}'),
        shlex.quote(f'min_novelty={float(min_novelty):.2f}'),
        shlex.quote(f'min_score={float(min_score):.2f}'),
        shlex.quote(f'max_items={int(max_items)}'),
        shlex.quote(f'historical_years={int(historical_years)}'),
    ]
    return ' '.join(parts)


def _default_watched_topic_tasks():
    """Default watched-research coverage for SAP payroll and SuccessFactors."""
    specs = [
        ('sap_payroll_au_watch', 'SAP payroll Australia', 'daily 06:30'),
        ('successfactors_employee_central_au_watch', 'SuccessFactors Employee Central Australia', 'daily 06:45'),
        ('successfactors_ecp_au_watch', 'SuccessFactors Employee Central Payroll Australia', 'daily 07:00'),
        ('successfactors_onboarding_2_0_au_watch', 'SuccessFactors Onboarding 2.0 Australia', 'daily 07:15'),
        ('successfactors_new_home_page_watch', 'SAP SuccessFactors new home page', 'daily 07:30'),
    ]
    tasks = []
    for name, topic, schedule in specs:
        tasks.append((
            name,
            schedule,
            'PYTHON',
            _watched_topic_action_data(
                topic=topic,
                depth='standard',
                agent='eight',
                email='ghost',
                min_quality=0.45,
                min_novelty=0.35,
                min_score=0.50,
                max_items=10,
                historical_years=5,
            ),
        ))
    return tasks


def _watched_topic_key(topic):
    return re.sub(r'\s+', ' ', str(topic or '').strip().lower())


def _ensure_watched_topic_evidence_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watched_topic_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            session_id INTEGER DEFAULT 0,
            source_url TEXT DEFAULT '',
            title TEXT DEFAULT '',
            snippet TEXT DEFAULT '',
            quality_score REAL DEFAULT 0,
            novelty_score REAL DEFAULT 0,
            combined_score REAL DEFAULT 0,
            qualified INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0,
            review_status TEXT DEFAULT '',
            review_note TEXT DEFAULT '',
            evidence_date TEXT DEFAULT '',
            recency_score REAL DEFAULT 0,
            recency_label TEXT DEFAULT '',
            is_historical INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(topic_key, evidence_fingerprint)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watched_topic_evidence_topic ON watched_topic_evidence(topic_key, updated_at)"
    )
    for col_ddl in [
        "ALTER TABLE watched_topic_evidence ADD COLUMN review_status TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN review_note TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN evidence_date TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN recency_score REAL DEFAULT 0",
        "ALTER TABLE watched_topic_evidence ADD COLUMN recency_label TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN is_historical INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(col_ddl)
        except Exception:
            pass
    conn.commit()


def _watched_evidence_row(row):
    return {
        'id': row['id'],
        'topic': row['topic'],
        'source_url': row['source_url'],
        'title': row['title'],
        'snippet': row['snippet'],
        'quality_score': float(row['quality_score'] or 0),
        'novelty_score': float(row['novelty_score'] or 0),
        'combined_score': float(row['combined_score'] or 0),
        'qualified': bool(row['qualified']),
        'notified': bool(row['notified']),
        'review_status': row['review_status'],
        'review_note': row['review_note'],
        'evidence_date': row['evidence_date'],
        'recency_score': float(row['recency_score'] or 0),
        'recency_label': row['recency_label'],
        'is_historical': bool(row['is_historical']),
        'reason': row['reason'],
        'session_id': row['session_id'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def _find_existing_watched_topic_task(conn, topic):
    patterns = [
        f'%topic="{topic}"%',
        f"%topic='{topic}'%",
        f'%topic={topic}%',
    ]
    for pattern in patterns:
        row = conn.execute(
            """SELECT id, name FROM scheduled_tasks
               WHERE action_type='PYTHON'
                 AND action_data LIKE '%interest_research_update%'
                 AND action_data LIKE ?
               ORDER BY id ASC
               LIMIT 1""",
            (pattern,),
        ).fetchone()
        if row:
            return row
    return None
