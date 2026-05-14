"""
fridays/task_runner.py — Python task runner registry for the Tasker.

Added scheduling note and improved watchdog_stall_detection task.
"""

# ... existing code ...

@register('watchdog_stall_detection', 'Auto-detect stuck processing tasks, auto-pause them, and create watchdog repair lessons. Run this every 5-10 minutes.', 'monitoring')
def _task_watchdog_stall_detection(**kwargs):
    """
    Periodic stall detector with recovery.
    
    Recommended schedule: Every 5-10 minutes via Tasker scheduler.
    
    Args (optional):
      max_age_minutes=15
      limit=20
      auto_recover=true
    """
    import shlex
    from utils.db.watchdog_lessons import detect_and_record_stalls

    opts = {'max_age_minutes': '15', 'limit': '20', 'auto_recover': 'true'}
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
    auto_recover = opts.get('auto_recover', 'true').lower() in ('true', '1', 'yes')

    lessons = detect_and_record_stalls(max_age_minutes=max_age, limit=lim, auto_recover=auto_recover)
    count = len(lessons)
    if count == 0:
        return f'No stalled tasks detected (>{max_age} min)'
    return f'Created {count} repair lessons + attempted recovery for stalled tasks (>{max_age} min)'

# ... rest of file ...