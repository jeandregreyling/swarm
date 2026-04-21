"""
services.py — Shared state, imports, and cross-cutting helpers
═══════════════════════════════════════════════════════════════════════════════
All blueprint modules import from here for shared access to:
  - Database connections, logging, message persistence
  - Queue manager wrappers (intake_internal, update_proposal_status)
  - Agent metadata, roster, and reachability
  - Kill switch state and patched orchestrator
  - Chat job tracking (locks, pools, TTL)
  - Time wizard and ALM governance helpers
  - Identity resolution and agent request validation
═══════════════════════════════════════════════════════════════════════════════
LINKED TO:
  utils/db/_schema.py       — _AGENT_ROSTER must stay in sync with the agent
                              roster seeded there. Adding an agent requires
                              updates in both files.
  frontend/blueprints/chat.py — _get_ghost_agent_names() queries the DB for
                              tier='paid'|'free' agents. _AGENT_ROSTER drives
                              what the UI shows; chat.py drives what executes.
  utils/config.py           — *_SYSTEM_PROMPT constants feed into the DB via
                              _schema.py; model strings here should match.
  ops/seed_agent_permissions.py — AGENT_ROLE_MAP keys must match names in
                              _AGENT_ROSTER.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import importlib.util
from pathlib import Path

# frontend/services/__init__.py → parents[2] = swarm root
SWARM_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SWARM_ROOT))
sys.path.insert(0, str(SWARM_ROOT / 'utils'))
sys.path.insert(0, str(SWARM_ROOT / 'core' / 'pipeline'))
sys.path.insert(0, str(SWARM_ROOT / 'lib' / 'system'))
sys.path.insert(0, str(SWARM_ROOT / 'lib' / 'search'))
sys.path.insert(0, str(SWARM_ROOT / 'frontend'))
sys.path.insert(0, str(SWARM_ROOT / 'core'))  # must precede lib/system to avoid shadow time_machine

try:
    from internet_tavily import search as _tavily_search
    _TAVILY_OK = True
except Exception as _e_tav:
    _TAVILY_OK = False
    _tavily_search = None

from flask import Flask, render_template, request, Response, jsonify
from functools import wraps
import json
import queue
import threading
import os

# Load .env.agents into environment so AGENT_API_KEY is available to agent auth middleware
_ENV_AGENTS = Path(__file__).resolve().parents[2] / '.env.agents'
if _ENV_AGENTS.exists() and not os.environ.get('AGENT_API_KEY'):
    for _line in _ENV_AGENTS.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _, _v = _line.partition('=')
            os.environ.setdefault(_k.strip(), _v.strip())
import time
import uuid
import re
import socket
from socketserver import ThreadingMixIn
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from wsgiref.simple_server import WSGIServer, make_server

from database import (get_connection, new_conversation, log_message,
                       use_approval_token, add_trusted_sender, remove_trusted_sender,
                       add_notification_sender, remove_notification_sender,
                       get_pending_emails, mark_pending_processed, log_activity,
                       list_user_profiles, get_user_profile, upsert_user_profile,
                       list_user_skill_permissions, set_user_skill_permission,
                       can_user_invoke_skill, initialise_database,
                       get_agent_memory, save_agent_memory, agent_has_capability,
                       grant_agent_capability, revoke_agent_capability,
                       get_agent_capabilities, AGENT_CAPABILITY_REGISTRY,
                       persist_chat_job, update_chat_job_db,
                       get_chat_jobs_by_ids, mark_orphaned_chat_jobs,
                       sweep_stuck_jobs)
from ticket import create as ticket_create, librarian_close
import queue_manager as _queue_manager

queue_intake = _queue_manager.intake
estimate_wait_minutes = _queue_manager.estimate_wait_minutes
mark_processing = _queue_manager.mark_processing

import orchestrator
from monitor import get_system_status
from sandpits import get_sandpit_stats, get_recent_log as sandpit_log
from system_clock import get_timestamp, get_timestamp_iso, get_full_time_string
from theme_engine import get_themed_html

# ALM reminder: UI/API changes that affect visibility must be mirrored in theme_engine + templates.
THEME_SYNC_REMINDER = 'ALM REMINDER: Mirror UI/API visibility changes in theme layer (theme_engine + templates).'

# Time Machine & Kill Switches
_tm_spec = importlib.util.spec_from_file_location('time_machine', str(SWARM_ROOT / 'core' / 'time_machine.py'))
_tm_mod = importlib.util.module_from_spec(_tm_spec)
assert _tm_spec and _tm_spec.loader
_tm_spec.loader.exec_module(_tm_mod)
# Ensure any downstream `from time_machine import ...` resolves to core implementation.
sys.modules['time_machine'] = _tm_mod
time_wizard = _tm_mod.time_wizard
from kill_switch import kill_switch

DISABLED_AGENTS = set()

_original_ask_agent = orchestrator.ask_agent


# ── Active SSE streams  ────────────────────────────────────────────────────────
# ticket_number → queue.Queue of event dicts. None = stream closed.
_streams = {}

# ── Active terminal shell streams (for stop support) ─────────────────────────
_SHELL_STREAM_LOCK = threading.Lock()
_SHELL_STREAM_PROCS = {}

# ── Persistent chat jobs + dispatch pools (extracted to services.chat_jobs) ──
from .chat_jobs import (
    _CHAT_JOB_LOCK,
    _CHAT_JOBS,
    _CHAT_JOB_TTL_SECONDS,
    _CHAT_DISPATCH_EXECUTOR,
    _CHAT_WORKER_EXECUTOR,
)

# ── Agent metadata — read from DB registry (single source of truth) ───────────
from utils.db.registry import (
    get_agent_roster      as _reg_roster,
    get_agent_aliases     as _reg_aliases,
    get_agent_tables      as _reg_tables,
    get_agent_etas        as _reg_etas,
    get_agent_runtime_classes as _reg_runtime,
    get_single_task_locals as _reg_single_task,
    get_display_labels    as _reg_display,
    get_api_key_map       as _reg_api_keys,
    get_agent_models      as _reg_models,
)

# Legacy names removed — use _reg_etas(), _reg_runtime(), _reg_single_task() directly

# ── Authentication helpers (extracted to services.auth) ──────────────────────
from .auth import get_current_user, require_auth, require_owner

# ── Chat job helpers (extracted to services.chat_jobs) ───────────────────────
from .chat_jobs import (
    _chat_now_iso,
    _chat_eta_seconds,
    _chat_runtime_class,
    _normalize_chat_participant,
)


# Legacy names removed — use _reg_tables(), _reg_roster() directly


def intake_internal(agent, title, description, priority=5):
    fn = getattr(_queue_manager, 'intake_internal', None)
    if callable(fn):
        return fn(agent, title, description, priority=priority)

    # Compatibility fallback for older queue_manager modules in some worktrees.
    snapshot = 'system snapshot unavailable'
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO queue (from_addr, subject, question, tags, system_snapshot, status, priority, source_type, agent)
               VALUES (?, ?, ?, ?, ?, 'queued', ?, 'internal', ?)""",
            (f'agent:{agent}', title, description[:500], agent, snapshot, priority, agent)
        )
        queue_id = cursor.lastrowid
        proposal_id = f'INTERNAL-{agent.upper()}-{queue_id:04d}'
        conn.execute(
            """INSERT OR IGNORE INTO work_proposals (proposal_id, agent, title, description, status, queue_id)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (proposal_id, agent, title[:200], description[:500], queue_id)
        )
        conn.commit()
    finally:
        conn.close()

    _safe_time_event(
        agent=agent,
        action='proposal_created',
        event_type='proposal',
        target=proposal_id,
        details={'queue_id': queue_id, 'title': title[:200], 'priority': priority}
    )

    return queue_id, proposal_id



def update_proposal_status(proposal_id, status, ticket_number=''):
    fn = getattr(_queue_manager, 'update_proposal_status', None)
    if callable(fn):
        return fn(proposal_id, status, ticket_number=ticket_number)

    # Fallback: route through governance
    from utils.governance import transition_proposal, GovernanceError
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT agent FROM work_proposals WHERE proposal_id=?', (proposal_id,)
        ).fetchone()
        agent = (row['agent'] if row else 'unknown')

        try:
            transition_proposal(proposal_id, status, agent,
                                actor='services', note='services.update_proposal_status',
                                conn=conn)
        except GovernanceError as exc:
            log_activity('terminal', 'governance_blocked', f'{proposal_id}:{status} — {exc}')
            return

        if ticket_number:
            conn.execute(
                "UPDATE work_proposals SET ticket_number=? WHERE proposal_id=?",
                (ticket_number, proposal_id)
            )
        conn.commit()

        # ALM routing fix — ensure every status change is Vortex-logged for Studio visibility
        try:
            _safe_time_event('terminal_ui', 'proposal_status_updated_via_skill', 'proposal', f'{proposal_id}:{status}')
        except Exception:
            pass
    finally:
        conn.close()



def get_queue_entries(source_type=None, status=None, limit=50):
    fn = getattr(_queue_manager, 'get_queue_entries', None)
    if callable(fn):
        return fn(source_type=source_type, status=status, limit=limit)

    clauses, params = [], []
    if source_type:
        clauses.append('source_type=?')
        params.append(source_type)
    if status:
        clauses.append('status=?')
        params.append(status)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    conn = get_connection()
    try:
        rows = conn.execute(
            f'SELECT * FROM queue {where} ORDER BY created_at DESC LIMIT ?',
            tuple(params + [limit])
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

def _patched_ask_agent(agent_name, prompt):
    if agent_name in DISABLED_AGENTS:
        print(f'[Terminal] {agent_name} offline — kill switch active')
        return f'[{agent_name} is currently offline]'
    return _original_ask_agent(agent_name, prompt)



def _display_chat_participant(name):
    canonical = _normalize_chat_participant(name)
    labels = _reg_display()
    if canonical in labels:
        return labels[canonical]
    return str(name or 'AGENT').strip().upper() or 'AGENT'


# ── Chat job lifecycle helpers (extracted to services.chat_jobs) ─────────────
from .chat_jobs import (
    _chat_stage_for,
    _chat_update_job,
    _cleanup_chat_jobs_locked,
    _chat_find_running_job_for_agent_locked,
    _chat_try_hard_kill_local_agent,
    _chat_job_public,
)


# ── Duck (quality gate) helpers (extracted to services.duck_review) ──────────
from .duck_review import (
    _duck_stats,
    _log_proposal_duck_review,
    _run_proposal_duck_review,
)



def _safe_time_event(agent, action, event_type='workflow', target='', details=None):
    try:
        return time_wizard.record_event(
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
        return time_wizard.create_workflow_checkpoint(label=label, agent=agent, description=description)
    except Exception as exc:
        log_activity('terminal', 'vortex_checkpoint_warning', f'{label}: {exc}')
        return None



def _is_time_wizard_active():
    """Time Wizard is considered active when at least one session exists."""
    # ALM gate defaults to ON; set ALM_REQUIRE_APPROVALS=0 to disable explicitly.
    if os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1':
        return True
    try:
        sessions = time_wizard.get_sessions(limit=1)
        return bool(sessions)
    except Exception:
        return False



def _alm_gate_or_response(data, action_name):
    """
    Enforce proposal approval for mutating actions — ALWAYS enforced.
    Returns a Flask response tuple on failure, else None.
    
    A.1.2: Gate is now mandatory. No bypass for Time Wizard inactive state.
    """
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
        if prop and prop['agent'].lower() == identity['effective_user'].lower() and identity['effective_user'] in _get_ghost_agent_names():
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



def _resolve_identity_or_response(data):
    """
    Resolve caller identity and optional proxy context.
    Returns (identity_dict, None) or (None, flask_response).
    """
    payload = data or {}
    acting = (payload.get('acting_user') or payload.get('user') or 'ghost').strip().lower()
    proxy_as = (payload.get('proxy_as') or '').strip().lower()

    actor_profile = get_user_profile(acting)
    if not actor_profile:
        return None, (jsonify({'ok': False, 'error': f'unknown acting_user: {acting}'}), 404)
    if not bool(actor_profile.get('is_active')):
        return None, (jsonify({'ok': False, 'error': f'user is inactive: {acting}'}), 403)

    effective_profile = actor_profile
    if proxy_as and proxy_as != acting:
        if not bool(actor_profile.get('can_proxy')):
            return None, (jsonify({'ok': False, 'error': f'user cannot proxy: {acting}'}), 403)
        target_profile = get_user_profile(proxy_as)
        if not target_profile:
            return None, (jsonify({'ok': False, 'error': f'unknown proxy target: {proxy_as}'}), 404)
        if not bool(target_profile.get('is_active')):
            return None, (jsonify({'ok': False, 'error': f'proxy target is inactive: {proxy_as}'}), 403)
        effective_profile = target_profile

    identity = {
        'acting_user': actor_profile['username'],
        'proxy_as': proxy_as or '',
        'effective_user': effective_profile['username'],
        'can_proxy': bool(actor_profile.get('can_proxy')),
        'actor': actor_profile,
        'effective': effective_profile,
    }
    return identity, None



def _validate_agent_request():
    """
    Validate that request is from a local agent with valid AGENT_API_KEY.
    Returns (agent_id, error_response) tuple.
    - On success: (agent_id_string, None)
    - On failure: (None, Flask error response tuple)
    """
    agent_key = request.headers.get('X-Agent-Key', '').strip()
    agent_id = request.headers.get('X-Agent-Id', '').strip()
    
    if not agent_key or not agent_id:
        return None, (jsonify({'ok': False, 'error': 'X-Agent-Key and X-Agent-Id headers required'}), 401)
    
    expected_key = os.environ.get('AGENT_API_KEY', '').strip()
    if not expected_key:
        return None, (jsonify({'ok': False, 'error': 'agent API not enabled (AGENT_API_KEY not set)'}), 503)
    
    if agent_key != expected_key:
        log_activity('terminal', 'agent_auth_failed', f'invalid key attempt from agent {agent_id}')
        return None, (jsonify({'ok': False, 'error': 'invalid agent API key'}), 403)
    
    # Valid agent_id should match known local agents
    valid_agents = {a['name'].lower() for a in _reg_roster()}
    if agent_id.lower() not in valid_agents:
        log_activity('terminal', 'agent_auth_unknown', f'unknown agent_id: {agent_id}')
        # Still allow it; agents can register themselves
    
    return agent_id, None



from .duck_review import _get_duck_flags_today



def _agent_reachability_status(agent_name):
    """Return 'online', 'degraded', or 'offline' based on real API key / service availability."""
    name = (agent_name or '').strip().lower()
    if name in DISABLED_AGENTS:
        return 'offline'
    # Determine tier from registry
    rt = _reg_runtime()
    tier = rt.get(name, '')
    # Local Ollama agents — assume online if not disabled
    if tier == 'local' or name == 'ghost':
        return 'online'
    # API-backed agents — check key presence via env var from registry
    import os
    api_keys = _reg_api_keys()
    env_var = api_keys.get(name) or ''
    if not env_var:
        return 'online'  # unknown agent or no key configured
    return 'online' if os.environ.get(env_var, '') else 'offline'



orchestrator.ask_agent = _patched_ask_agent


__all__ = [
    'AGENT_CAPABILITY_REGISTRY',
    'DISABLED_AGENTS',
    'Flask',
    'FuturesTimeoutError',
    'Path',
    'Response',
    'SWARM_ROOT',
    'THEME_SYNC_REMINDER',
    'ThreadPoolExecutor',
    '_reg_roster', '_reg_aliases', '_reg_tables', '_reg_etas', '_reg_runtime',
    '_reg_single_task', '_reg_display', '_reg_api_keys', '_reg_models',
    '_CHAT_DISPATCH_EXECUTOR',
    '_CHAT_JOBS',
    '_CHAT_JOB_LOCK',
    '_CHAT_JOB_TTL_SECONDS',
    '_CHAT_WORKER_EXECUTOR',
    '_SHELL_STREAM_LOCK',
    '_SHELL_STREAM_PROCS',
    '_TAVILY_OK',
    '_agent_reachability_status',
    '_alm_gate_or_response',
    '_chat_eta_seconds',
    '_chat_find_running_job_for_agent_locked',
    '_chat_job_public',
    '_chat_now_iso',
    '_chat_runtime_class',
    '_chat_stage_for',
    '_chat_try_hard_kill_local_agent',
    '_chat_update_job',
    '_cleanup_chat_jobs_locked',
    '_display_chat_participant',
    '_duck_stats',
    '_get_duck_flags_today',
    '_is_time_wizard_active',
    '_log_proposal_duck_review',
    '_normalize_chat_participant',
    '_original_ask_agent',
    '_patched_ask_agent',
    '_resolve_identity_or_response',
    '_run_proposal_duck_review',
    '_safe_time_event',
    '_safe_workflow_checkpoint',
    '_streams',
    '_tavily_search',
    '_validate_agent_request',
    'add_notification_sender',
    'add_trusted_sender',
    'agent_has_capability',
    'can_user_invoke_skill',
    'datetime',
    'estimate_wait_minutes',
    'get_agent_capabilities',
    'get_agent_memory',
    'get_chat_jobs_by_ids',
    'get_connection',
    'get_current_user',
    'get_full_time_string',
    'get_pending_emails',
    'get_queue_entries',
    'get_sandpit_stats',
    'get_system_status',
    'get_themed_html',
    'get_timestamp',
    'get_timestamp_iso',
    'get_user_profile',
    'require_auth',
    'require_owner',
    'grant_agent_capability',
    'initialise_database',
    'intake_internal',
    'json',
    'jsonify',
    'kill_switch',
    'librarian_close',
    'list_user_profiles',
    'list_user_skill_permissions',
    'log_activity',
    'log_message',
    'mark_orphaned_chat_jobs',
    'mark_pending_processed',
    'mark_processing',
    'new_conversation',
    'orchestrator',
    'os',
    'persist_chat_job',
    'sweep_stuck_jobs',
    'queue',
    'queue_intake',
    're',
    'remove_notification_sender',
    'remove_trusted_sender',
    'request',
    'revoke_agent_capability',
    'sandpit_log',
    'save_agent_memory',
    'set_user_skill_permission',
    'socket',
    'threading',
    'ticket_create',
    'time',
    'time_wizard',
    'timezone',
    'update_chat_job_db',
    'update_proposal_status',
    'upsert_user_profile',
    'use_approval_token',
    'uuid',
]
