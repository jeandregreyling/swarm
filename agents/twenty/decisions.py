"""Decisions — Agent 20's reasoning and decision-tracking matrix.

Records every council decision: what was decided, why, what the outcome was.
Tracks decision quality over time so the system learns from its own history.

Decision matrix dimensions:
  - Severity (how bad is the situation)
  - Confidence (how sure are we about the diagnosis)
  - Impact (what happens if we act vs. don't act)
  - History (have we seen this before, and what happened)

Output: action recommendation with full reasoning trail for audit.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from utils.db._connection import get_connection

logger = logging.getLogger('seven.agent20.decisions')

# ── Severity levels ───────────────────────────────────────────────────

SEVERITY_NONE = 0      # Nothing notable
SEVERITY_INFO = 1      # Worth knowing
SEVERITY_WARNING = 2   # Might need attention
SEVERITY_ERROR = 3     # Needs attention now
SEVERITY_CRITICAL = 4  # System integrity at risk

# ── Action types ──────────────────────────────────────────────────────

ACTION_OBSERVE = 'observe'     # Keep watching, no action
ACTION_SUGGEST = 'suggest'     # Surface to user/orb
ACTION_ESCALATE = 'escalate'   # High-urgency surface
ACTION_SUPPRESS = 'suppress'   # Already handled / duplicate

# ── Decision matrix ──────────────────────────────────────────────────

def _severity_from_signals(thought, signals):
    """Calculate severity from thought content and system signals."""
    sev = SEVERITY_NONE
    urgency = thought.get('urgency', 0)
    confidence = thought.get('confidence', 0.5)

    if urgency >= 2:
        sev = max(sev, SEVERITY_ERROR)
    elif urgency >= 1:
        sev = max(sev, SEVERITY_WARNING)

    # System pressure raises severity
    stats = signals.get('system_stats', {})
    cpu = stats.get('cpu_percent', 0)
    if cpu > 90:
        sev = max(sev, SEVERITY_ERROR)
    elif cpu > 70:
        sev = max(sev, SEVERITY_WARNING)

    # Error count raises severity
    errors = signals.get('agent_errors', [])
    if len(errors) >= 5:
        sev = max(sev, SEVERITY_ERROR)
    elif len(errors) >= 2:
        sev = max(sev, SEVERITY_WARNING)

    # Low confidence with high urgency = info (uncertain)
    if urgency >= 2 and confidence < 0.4:
        sev = max(sev, SEVERITY_INFO)

    return sev


def _check_history(thought, conn):
    """Check decision history for similar past decisions.

    Returns dict with: seen_before (bool), last_action, times_seen, last_outcome.
    """
    try:
        role = thought.get('orb_role', '')
        # Look for past decisions with same role and similar content
        rows = conn.execute(
            """SELECT decision, reasoning, test_status, created_at
               FROM decisions WHERE agent = 'twenty' AND component = ?
               ORDER BY created_at DESC LIMIT 5""",
            (role,),
        ).fetchall()
        if rows:
            return {
                'seen_before': True,
                'times_seen': len(rows),
                'last_action': rows[0]['decision'],
                'last_outcome': rows[0]['test_status'],
                'last_at': rows[0]['created_at'],
            }
    except Exception as exc:
        logger.debug("History check skipped: %s", exc)
    return {'seen_before': False, 'times_seen': 0, 'last_action': None, 'last_outcome': None}


def _decide_action(severity, confidence, history):
    """Core decision matrix — determines action from severity × confidence × history.

    Returns (action, reasoning_parts).
    """
    reasons = []

    # Already seen and recently acted on → suppress duplicate
    if history.get('seen_before') and history.get('times_seen', 0) >= 3:
        last_outcome = history.get('last_outcome', '')
        if last_outcome in ('ok', 'PASS', 'success'):
            reasons.append(f"Seen {history['times_seen']}x, last outcome was OK")
            return ACTION_OBSERVE, reasons

    # Critical always escalates (honesty rule: never suppress bad news)
    if severity >= SEVERITY_CRITICAL:
        reasons.append(f"Severity CRITICAL ({severity})")
        return ACTION_ESCALATE, reasons

    # Error with good confidence → escalate
    if severity >= SEVERITY_ERROR and confidence >= 0.5:
        reasons.append(f"Severity ERROR, confidence {confidence:.2f}")
        return ACTION_ESCALATE, reasons

    # Error but low confidence → still suggest (honesty: don't hide it)
    if severity >= SEVERITY_ERROR and confidence < 0.5:
        reasons.append(f"Severity ERROR but confidence only {confidence:.2f} — suggest, don't suppress")
        return ACTION_SUGGEST, reasons

    # Warning → suggest
    if severity >= SEVERITY_WARNING:
        reasons.append(f"Severity WARNING ({severity})")
        return ACTION_SUGGEST, reasons

    # Info → observe
    if severity >= SEVERITY_INFO:
        reasons.append(f"Severity INFO — observe only")
        return ACTION_OBSERVE, reasons

    # Nothing notable → observe
    reasons.append("No notable signals")
    return ACTION_OBSERVE, reasons


def evaluate_thought(thought, signals, conn=None):
    """Run decision matrix on a single thought.

    Returns dict with: action, severity, reasoning, history.
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        severity = _severity_from_signals(thought, signals)
        confidence = thought.get('confidence', 0.5)
        history = _check_history(thought, conn)
        action, reasons = _decide_action(severity, confidence, history)

        return {
            'action': action,
            'severity': severity,
            'confidence': confidence,
            'reasoning': reasons,
            'history': history,
            'orb_role': thought.get('orb_role', ''),
            'thought_text': thought.get('thought', ''),
        }
    finally:
        if close:
            conn.close()


def record_decision(thought, action, severity, reasoning, signals, conn=None):
    """Persist a decision for audit trail and future history lookups."""
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        conn.execute(
            """INSERT INTO decisions
               (agent, component, decision, reasoning, test_status, created_at)
               VALUES ('twenty', ?, ?, ?, 'PENDING', datetime('now'))""",
            (
                thought.get('orb_role', ''),
                f"{action}: {thought.get('thought', '')[:100]}",
                json.dumps({
                    'severity': severity,
                    'reasons': reasoning,
                    'signals_at': signals.get('collected_at', ''),
                    'pfv': {
                        'p': thought.get('pfv_p'),
                        'f': thought.get('pfv_f'),
                        'v': thought.get('pfv_v'),
                    },
                }),
            ),
        )
        conn.commit()
    finally:
        if close:
            conn.close()


def apply_decisions(thoughts, signals, conn=None):
    """Run decision matrix on all thoughts from a council cycle.

    Filters and annotates thoughts:
    - ESCALATE → urgency boosted, surfaced
    - SUGGEST → surfaced as-is
    - OBSERVE → logged but not surfaced
    - SUPPRESS → dropped

    Returns list of thoughts that should be written to council_output.
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        surfaced = []
        for thought in thoughts:
            result = evaluate_thought(thought, signals, conn=conn)
            action = result['action']
            severity = result['severity']
            reasoning = result['reasoning']

            # Record every decision for audit
            record_decision(thought, action, severity, reasoning, signals, conn=conn)

            if action == ACTION_ESCALATE:
                thought['urgency'] = max(thought.get('urgency', 0), 2)
                thought['detail'] = (thought.get('detail', '') +
                                     f' [decision: escalated, severity={severity}]')
                surfaced.append(thought)
            elif action == ACTION_SUGGEST:
                surfaced.append(thought)
            elif action == ACTION_OBSERVE:
                logger.debug("Decision: observe-only for %s: %s",
                             thought.get('orb_role'), thought.get('thought', '')[:60])
            # SUPPRESS: don't add to surfaced

        logger.info("Decision matrix: %d in → %d surfaced (%d observed/suppressed)",
                     len(thoughts), len(surfaced), len(thoughts) - len(surfaced))
        return surfaced
    finally:
        if close:
            conn.close()
