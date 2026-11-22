"""Calm swarm (JD 21 Nov 2026: "it's still a swarm system and it doesn't need to freak out every time we make a change that is going
to help it"). One place for what counts as a routine interruption, so HB treats it as a pause, not a failure:

  interrupted(stage)   a turn cut short because the worker or HB restarted mid-turn - not the model's attempt, not "stuck"
  INTERRUPTED_SQL      the same test in SQL, on hb_peer_work.stage
  restart_pending()    an announced restart is on its way (Maintenance notice on): no new turn starts until it is done
"""
INTERRUPTED_PREFIXES = ('Worker disconnected during a turn', 'Worker restarted during a turn', 'Worker interrupted')
INTERRUPTED_SQL = '(' + ' OR '.join(f"stage LIKE '{p}%'" for p in INTERRUPTED_PREFIXES) + ')'


def interrupted(stage):
    return str(stage or '').startswith(INTERRUPTED_PREFIXES)


def restart_queued(conn, now=None):
    """Practice 242 (21 Nov): a restart in hb_restart_queue past its quiet minute. HB used to start the next APEX turn within seconds,
    so restart_tick (which waits for no running turn) almost never found its gap and fixes sat unloaded. Now no new turn starts
    while such a restart waits: the running turn finishes, HB restarts, work resumes."""
    import time
    try:
        from core.hb_plan_workflow import RESTART_QUIET_S
        oldest = conn.execute('SELECT MAX(at) FROM hb_restart_queue').fetchone()[0]
    except Exception:
        return False
    return bool(oldest) and (time.time() if now is None else now) - oldest >= RESTART_QUIET_S


def restart_pending():
    try:
        from core.hb_maintenance import state
        return bool(state().get('on'))
    except Exception:
        return False
