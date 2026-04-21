"""
services.alm — ALM governance gate + Vortex (time wizard) event helpers.

Extracted from services/__init__.py as part of Phase B.

Contains:
  - _safe_time_event / _safe_workflow_checkpoint  — Vortex telemetry wrappers
  - _is_time_wizard_active                        — ALM gate activation probe
  - _alm_gate_or_response                         — proposal approval enforcement
"""
import os

from flask import jsonify

from database import get_connection, log_activity


def _time_wizard():
    """Lazy accessor — time_wizard is loaded via importlib in services/__init__.py."""
    from . import time_wizard
    return time_wizard


def _safe_time_event(agent, action, event_type='workflow', target='', details=None):
    try:
        return _time_wizard().record_event(
            agent=agent,
            action=action,
            event_type=event_type,
            target=target,
            details=details or {}
        )
    except Exception as exc:
        log_activity('terminal', 'vortex_log_warning', f'{action}: {exc}')
        return None


def _safe_workflow_checkpoint(label, agent='terminal_ui', description=''):
    try:
        return _time_wizard().create_workflow_checkpoint(label=label, agent=agent, description=description)
    except Exception as exc:
        log_activity('terminal', 'vortex_checkpoint_warning', f'{label}: {exc}')
        return None


def _is_time_wizard_active():
    """Time Wizard is considered active when at least one session exists."""
    # ALM gate defaults to ON; set ALM_REQUIRE_APPROVALS=0 to disable explicitly.
    if os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1':
        return True
    try:
        sessions = _time_wizard().get_sessions(limit=1)
        return bool(sessions)
    except Exception:
        return False


def _ghost_agent_names_fallback():
    """Local copy of chat._get_ghost_agent_names to avoid circular import.
    Returns names of all enabled non-local agents (tier paid/free) from DB."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT name FROM agents WHERE tier IN ('paid','free') AND enabled=1"
        ).fetchall()
        conn.close()
        return {r['name'] for r in rows}
    except Exception:
        return {'nine', 'ten', 'eleven', 'twelve', 'thirteen'}


def _alm_gate_or_response(data, action_name):
    """
    Enforce proposal approval for mutating actions — ALWAYS enforced.
    Returns a Flask response tuple on failure, else None.

    A.1.2: Gate is now mandatory. No bypass for Time Wizard inactive state.
    """
    from .identity import _resolve_identity_or_response

    proposal_id = (data.get('proposal_id') or '').strip()
    if not proposal_id:
        return jsonify({
            'ok': False,
            'error': 'proposal_id required — all mutating actions need an approved proposal',
            'action': action_name,
            'required_status': ['approved', 'in_progress']
        }), 428

    # Ownership bypass for Ghost (human operator)
    identity, _ = _resolve_identity_or_response(data)
    conn = get_connection()
    try:
        prop = conn.execute("SELECT agent FROM work_proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if prop and prop['agent'].lower() == identity['effective_user'].lower() and identity['effective_user'] in _ghost_agent_names_fallback():
            return None  # Ghost bypass

        row = conn.execute(
            "SELECT proposal_id, status, agent, title FROM work_proposals WHERE proposal_id=?",
            (proposal_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({
            'ok': False,
            'error': f'proposal not found: {proposal_id}',
            'action': action_name
        }), 404

    if row['status'] not in ('approved', 'in_progress', 'executed'):
        return jsonify({
            'ok': False,
            'error': f'proposal status not permitted: {row["status"]}',
            'action': action_name,
            'proposal_id': proposal_id,
            'required_status': ['approved', 'in_progress']
        }), 403

    log_activity('terminal', 'alm_gate_pass', f'{action_name}:{proposal_id}')
    return None
