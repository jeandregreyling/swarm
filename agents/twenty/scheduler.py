"""Scheduler — daemon thread that runs the Agent 20 observe→council→write cycle.

No APScheduler — follows the existing daemon thread pattern (like _stuck_job_sweeper).
Registers with Flask app context so DB connections work.
"""

import json
import logging
import threading
import time

from agents.twenty import AGENT20_ENABLED, CYCLE_INTERVAL

logger = logging.getLogger('seven.agent20.scheduler')

_thread = None
_stop_event = threading.Event()


def _run_cycle(app):
    """Single observe → council → decide → learn → write cycle inside Flask app context."""
    from agents.twenty.observer import collect_signals
    from agents.twenty.council import run_council
    from agents.twenty.decisions import apply_decisions
    from agents.twenty.memory import learn_from_cycle
    from agents.twenty.mapper import build_health_digest
    from utils.db._connection import get_connection

    with app.app_context():
        try:
            signals = collect_signals()
            thoughts = run_council(signals)

            if not thoughts:
                logger.debug("Council cycle produced 0 gated thoughts — nothing to write.")
                # Still learn from signals (absence of thoughts is data too)
                learn_from_cycle(signals, [])
                return

            # Decision matrix filters and annotates
            surfaced = apply_decisions(thoughts, signals)

            conn = get_connection()
            try:
                for t in surfaced:
                    conn.execute(
                        """INSERT INTO council_output
                           (orb_role, thought, detail, urgency, confidence,
                            pfv_p, pfv_f, pfv_v, source_refs, context_json,
                            expires_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            t['orb_role'],
                            t['thought'],
                            t.get('detail', ''),
                            t.get('urgency', 0),
                            t.get('confidence', 0.5),
                            t.get('pfv_p'),
                            t.get('pfv_f'),
                            t.get('pfv_v'),
                            json.dumps(t.get('source_refs', [])),
                            t.get('context_json', '{}'),
                            t['expires_at'],
                        ),
                    )
                conn.commit()
                logger.info("Council wrote %d thoughts to council_output.", len(surfaced))

                # Learn from this cycle
                learn_from_cycle(signals, surfaced, conn=conn)
            finally:
                conn.close()

        except Exception:
            logger.exception("Agent 20 cycle failed")


def _loop(app):
    """Daemon loop — runs _run_cycle every CYCLE_INTERVAL seconds."""
    logger.info(
        "Agent 20 scheduler started (cycle=%ds, enabled=%s)",
        CYCLE_INTERVAL, AGENT20_ENABLED,
    )
    while not _stop_event.is_set():
        if AGENT20_ENABLED:
            _run_cycle(app)
        _stop_event.wait(CYCLE_INTERVAL)
    logger.info("Agent 20 scheduler stopped.")


def start(app):
    """Start the Agent 20 daemon thread.  Safe to call multiple times."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return  # already running

    if not AGENT20_ENABLED:
        logger.info("Agent 20 disabled (AGENT20_ENABLED=false) — scheduler not started.")
        return

    _stop_event.clear()
    _thread = threading.Thread(
        target=_loop,
        args=(app,),
        daemon=True,
        name='agent20-council',
    )
    _thread.start()


def stop():
    """Signal the scheduler to stop.  Non-blocking."""
    _stop_event.set()
