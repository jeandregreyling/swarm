"""
fridays/task_runner.py — Python task runner registry for the Tasker.

... (previous content preserved, only adding the new task at the end of built-in tasks)
"""

# ... (all previous code remains unchanged) ...

@register('watchdog_stall_detection', 'Auto-detect stuck processing tasks and create watchdog repair lessons (P-00221285D1)', 'monitoring')
def _task_watchdog_stall_detection(**kwargs):
    """
    Periodic stall detector.
    Scans for tasks stuck in 'processing' and auto-creates repair lessons
    so the watchdog + agents can act.
    
    Args (optional):
      max_age_minutes=15
      limit=20
    """
    import shlex
    from utils.db.watchdog_lessons import detect_and_record_stalls

    opts = {'max_age_minutes': '15', 'limit': '20'}
    for tok in shlex.split(kwargs.get('args') or ''):
        if '=' in tok:
            k, v = tok.split('=', 1)
            if k.strip().lower() in opts:
                opts[k.strip().lower()] = v.strip()

    try:
        max_age = max(5, min(int(opts['max_age_minutes']), 120))
    except Exception:
        max_age = 15
    try:
        lim = max(5, min(int(opts['limit']), 50))
    except Exception:
        lim = 20

    lessons = detect_and_record_stalls(max_age_minutes=max_age, limit=lim)
    count = len(lessons)
    if count == 0:
        return f'No stalled tasks detected (>{max_age} min)'
    return f'Created {count} repair lessons for stalled tasks (>{max_age} min)'

# ... (rest of file unchanged) ...