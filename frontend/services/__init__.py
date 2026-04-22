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


# ── Queue wrappers (extracted to services.queue_wrappers) ────────────────────
from .queue_wrappers import intake_internal, update_proposal_status, get_queue_entries



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


# ── Chat relay / intent parsing helpers (extracted to services.chat_relay) ───
from .chat_relay import (
    _RELAY_LINE_PATTERNS,
    _RELAY_ROUTE_PATTERNS,
    _derive_proposal_from_text,
    _extract_skill_lines_from_text,
    _gate_relay_target,
    _infer_reply_target_from_text,
    _is_execution_confirmation,
    _parse_chat_skill_command,
    _resolve_chat_reply_target,
    _strip_relay_routing,
)


# ── Chat agent / model helpers (extracted to services.chat_agents) ───────────
# NOTE: _chat_try_hard_kill_local_agent is deliberately NOT here — the
# worker-pool variant from chat_jobs wins in the services namespace, and
# chat.py keeps its own CLI-based variant locally.
from .chat_agents import (
    _chat_agent_configured_model,
    _chat_model_aliases,
    _chat_running_ollama_models,
    _local_ollama_chat_agents,
)


# ── Chat thread/history helpers (extracted to services.chat_history) ─────────
from .chat_history import (
    _build_chat_handoff_block,
    _chat_history_from_rows,
    _conversation_reply_context_from_rows,
    _fetch_chat_thread_rows,
    _thread_transcript_from_rows,
)



# ── ALM governance + Vortex event helpers (extracted to services.alm) ───────
from .alm import (
    _safe_time_event,
    _safe_workflow_checkpoint,
    _is_time_wizard_active,
    _alm_gate_or_response,
)



# ── Identity / agent auth / reachability (extracted to services.identity) ────
from .identity import (
    _resolve_identity_or_response,
    _validate_agent_request,
    _agent_reachability_status,
)



from .duck_review import _get_duck_flags_today



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
    '_RELAY_LINE_PATTERNS',
    '_RELAY_ROUTE_PATTERNS',
    '_SHELL_STREAM_LOCK',
    '_SHELL_STREAM_PROCS',
    '_TAVILY_OK',
    '_agent_reachability_status',
    '_alm_gate_or_response',
    '_build_chat_handoff_block',
    '_chat_agent_configured_model',
    '_chat_eta_seconds',
    '_chat_find_running_job_for_agent_locked',
    '_chat_history_from_rows',
    '_chat_job_public',
    '_chat_model_aliases',
    '_chat_now_iso',
    '_chat_runtime_class',
    '_chat_running_ollama_models',
    '_chat_stage_for',
    '_chat_try_hard_kill_local_agent',
    '_chat_update_job',
    '_cleanup_chat_jobs_locked',
    '_conversation_reply_context_from_rows',
    '_derive_proposal_from_text',
    '_display_chat_participant',
    '_duck_stats',
    '_extract_skill_lines_from_text',
    '_fetch_chat_thread_rows',
    '_gate_relay_target',
    '_get_duck_flags_today',
    '_infer_reply_target_from_text',
    '_is_execution_confirmation',
    '_is_time_wizard_active',
    '_local_ollama_chat_agents',
    '_log_proposal_duck_review',
    '_normalize_chat_participant',
    '_original_ask_agent',
    '_parse_chat_skill_command',
    '_patched_ask_agent',
    '_resolve_chat_reply_target',
    '_resolve_identity_or_response',
    '_run_proposal_duck_review',
    '_safe_time_event',
    '_safe_workflow_checkpoint',
    '_streams',
    '_strip_relay_routing',
    '_tavily_search',
    '_thread_transcript_from_rows',
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
