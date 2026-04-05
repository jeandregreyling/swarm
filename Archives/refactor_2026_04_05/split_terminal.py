#!/usr/bin/env python3
"""
split_terminal.py — Extract terminal.py monolith into Flask blueprints.
═══════════════════════════════════════════════════════════════════════════════
Creates:
  - frontend/services.py               (shared state + cross-cutting helpers)
  - frontend/blueprints/__init__.py     (empty)
  - frontend/blueprints/{name}.py       (blueprint modules)
  - frontend/terminal_new.py            (slim app factory — review before swap)

Usage:
  cd /home/seven/swarm/frontend
  python3 split_terminal.py
  # Review generated files, then:
  # cp terminal.py terminal.py.monolith && cp terminal_new.py terminal.py
  # sudo systemctl restart swarm-terminal
═══════════════════════════════════════════════════════════════════════════════
"""
import re
import os
import sys
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════
BASE      = os.path.dirname(os.path.abspath(__file__))
SRC_PATH  = os.path.join(BASE, 'terminal.py')
SVC_PATH  = os.path.join(BASE, 'services.py')
BP_DIR    = os.path.join(BASE, 'blueprints')
NEW_TERM  = os.path.join(BASE, 'terminal_new.py')

# ═══════════════════════════════════════════════════════════════════════════════
# Read source
# ═══════════════════════════════════════════════════════════════════════════════
with open(SRC_PATH) as f:
    lines = f.readlines()

TOTAL = len(lines)
print(f'Read {TOTAL} lines from terminal.py')


def L(start, end):
    """Return lines[start-1:end] as string (1-indexed, inclusive)."""
    return ''.join(lines[start - 1:end])


# ═══════════════════════════════════════════════════════════════════════════════
# Parse all top-level function blocks
# ═══════════════════════════════════════════════════════════════════════════════
blocks = []
decorator_stack = []

i = 0
while i < TOTAL:
    line = lines[i]
    stripped = line.rstrip()

    # Collect decorators at column 0
    if stripped.startswith('@') and (not line[0].isspace()):
        decorator_stack.append(i)
        i += 1
        continue

    # Top-level function def at column 0
    if stripped.startswith('def ') and (not line[0].isspace()):
        func_start = decorator_stack[0] if decorator_stack else i  # 0-indexed
        m = re.match(r'def\s+(\w+)', stripped)
        func_name = m.group(1) if m else 'unknown'

        # Scan forward to find end of function body
        j = i + 1
        while j < TOTAL:
            nxt = lines[j]
            if not nxt.strip():       # blank
                j += 1
                continue
            if nxt[0] in (' ', '\t'):  # indented — inside function
                j += 1
                continue
            break  # non-indented, non-blank = end of function

        has_route = any('@app.route' in lines[d] for d in decorator_stack)
        route_path = None
        if has_route:
            for d in decorator_stack:
                rm = re.search(r"@app\.route\(['\"]([^'\"]+)", lines[d])
                if rm:
                    route_path = rm.group(1)
                    break

        blocks.append({
            'name':       func_name,
            'start':      func_start,       # 0-indexed line index
            'end':        j,                 # 0-indexed, exclusive
            'is_route':   has_route,
            'route_path': route_path,
        })
        decorator_stack = []
        i = j
        continue

    # Non-decorator, non-def — reset decorator stack (unless comment/blank)
    if stripped and not stripped.startswith('#'):
        decorator_stack = []
    i += 1

print(f'Parsed {len(blocks)} top-level function blocks')

# ═══════════════════════════════════════════════════════════════════════════════
# Blueprint assignment map
# ═══════════════════════════════════════════════════════════════════════════════
SVC = '_services_'

FUNC_MAP = {
    # ── services (shared state + cross-cutting helpers) ──────────────────────
    'intake_internal':                      SVC,
    'update_proposal_status':               SVC,
    'get_queue_entries':                     SVC,
    '_patched_ask_agent':                   SVC,
    '_chat_now_iso':                        SVC,
    '_chat_eta_seconds':                    SVC,
    '_chat_runtime_class':                  SVC,
    '_normalize_chat_participant':          SVC,
    '_display_chat_participant':            SVC,
    '_chat_stage_for':                      SVC,
    '_chat_update_job':                     SVC,
    '_cleanup_chat_jobs_locked':            SVC,
    '_chat_find_running_job_for_agent_locked': SVC,
    '_chat_try_hard_kill_local_agent':      SVC,
    '_chat_job_public':                     SVC,
    '_duck_stats':                          SVC,
    '_log_proposal_duck_review':            SVC,
    '_run_proposal_duck_review':            SVC,
    '_safe_time_event':                     SVC,
    '_safe_workflow_checkpoint':            SVC,
    '_is_time_wizard_active':               SVC,
    '_alm_gate_or_response':                SVC,
    '_resolve_identity_or_response':        SVC,
    '_validate_agent_request':              SVC,
    '_agent_reachability_status':           SVC,
    '_get_duck_flags_today':                SVC,

    # ── system ───────────────────────────────────────────────────────────────
    'api_health':           'system',
    'index':                'system',
    'api_system_time':      'system',
    'api_system':           'system',
    'api_monitor_stats':    'system',
    'api_tailscale':        'system',
    'api_sandpits':         'system',
    'api_ghost_circle':     'system',
    'api_monitor':          'system',
    'api_alm_status':       'system',
    'api_activity':         'system',
    'api_activity_stream':  'system',
    'api_swarm_status':     'system',
    'api_swarm_globals_get':'system',
    'api_swarm_globals_put':'system',

    # ── conversations ────────────────────────────────────────────────────────
    '_recent_conversations':         'conversations',
    'api_conversations':             'conversations',
    'api_conversation_messages':     'conversations',
    'api_conversation_message_patch':'conversations',
    'api_conversation_message_delete':'conversations',
    'api_conversation_patch':        'conversations',
    'api_conversation_delete':       'conversations',

    # ── tickets ──────────────────────────────────────────────────────────────
    '_tickets':                 'tickets',
    'api_tickets':              'tickets',
    'api_ticket_detail':        'tickets',
    'api_ticket_patch':         'tickets',
    'add_ticket_note_endpoint': 'tickets',
    'delete_ticket_note_endpoint':'tickets',
    'add_snooze_endpoint':      'tickets',
    'resend_ticket':            'tickets',
    'assign_ticket':            'tickets',
    'force_close_ticket':       'tickets',
    'reopen_ticket_endpoint':   'tickets',
    'delete_ticket':            'tickets',

    # ── memory ───────────────────────────────────────────────────────────────
    '_collect_local_file_memories': 'memory',
    '_memory_search':               'memory',
    'api_memory':                   'memory',
    'api_studio':                   'memory',
    'delete_memory':                'memory',
    'update_memory':                'memory',
    'attach_memory':                'memory',
    'assign_memory':                'memory',

    # ── kb (knowledge base) ──────────────────────────────────────────────────
    '_ensure_project_doc_versions_schema': 'kb',
    '_next_project_doc_version':           'kb',
    '_record_project_doc_version':         'kb',
    'api_kb_list':      'kb',
    'api_kb_get':       'kb',
    'api_kb_versions':  'kb',
    'api_kb_restore':   'kb',
    'api_kb_create':    'kb',
    'api_kb_update':    'kb',
    'api_kb_delete':    'kb',

    # ── proposals ────────────────────────────────────────────────────────────
    'api_proposals_list':       'proposals',
    'api_proposals_approve':    'proposals',
    'api_proposals_reject':     'proposals',
    'api_queue_list':           'proposals',
    'api_queue_create_internal':'proposals',
    'api_queue_get':            'proposals',
    'api_queue_patch':          'proposals',
    'api_work_proposals_list':  'proposals',
    'api_work_proposals_patch': 'proposals',
    'api_work_proposals_delete':'proposals',
    'api_deferred_list':        'proposals',
    'api_deferred_create':      'proposals',
    'api_deferred_patch':       'proposals',
    'api_deferred_delete':      'proposals',

    # ── git ──────────────────────────────────────────────────────────────────
    '_git_repo_root':                    'git',
    '_git_rel_path':                     'git',
    '_run_git_command':                  'git',
    '_build_git_operation_description':  'git',
    '_parse_git_operation_from_proposal':'git',
    '_execute_git_operation':            'git',
    '_parse_git_status_porcelain':       'git',
    'api_git_status':   'git',
    'api_git_diff':     'git',
    'api_git_stage':    'git',
    'api_git_unstage':  'git',
    'api_git_commit':   'git',

    # ── workspace ────────────────────────────────────────────────────────────
    '_workspace_replace_candidates': 'workspace',
    'api_workspace_dir':             'workspace',
    'api_workspace_file':            'workspace',
    'api_workspace_file_save':       'workspace',
    'api_workspace_search':          'workspace',
    'api_workspace_replace_preview': 'workspace',
    'api_workspace_replace_apply':   'workspace',
    'api_code_ops_pytest':           'workspace',
    'api_code_ops_pylint':           'workspace',
    'api_code_ops_format':           'workspace',
    'api_code_ops_commit':           'workspace',

    # ── shell ────────────────────────────────────────────────────────────────
    'api_shell_execute':           'shell',
    'api_shell_stream':            'shell',
    'api_terminal_run':            'shell',
    'api_terminal_stream':         'shell',
    'api_shell_stream_stop':       'shell',
    'api_terminal_stream_stop':    'shell',
    'api_hands_run':               'shell',
    'api_terminal_shortcuts_get':  'shell',
    'api_terminal_shortcuts_post': 'shell',
    'api_terminal_shortcuts_put':  'shell',
    'api_terminal_shortcuts_delete':'shell',

    # ── auth ─────────────────────────────────────────────────────────────────
    '_get_sender_lists':            'auth',
    'api_senders':                  'auth',
    'add_sender':                   'auth',
    'remove_sender':                'auth',
    'api_manager_onboard':          'auth',
    'api_auth_profiles':            'auth',
    'api_auth_context':             'auth',
    'api_auth_profiles_create':     'auth',
    'api_auth_profiles_patch':      'auth',
    'api_skills_permissions':       'auth',
    'api_skills_permissions_update':'auth',
    'api_skills_run':               'auth',
    'api_skills':                   'auth',

    # ── agents ───────────────────────────────────────────────────────────────
    'api_agents':                   'agents',
    'api_agents_config_get':        'agents',
    'api_agents_config_put':        'agents',
    'api_agents_config_post':       'agents',
    'api_agents_key_put':           'agents',
    'api_agents_capability_matrix': 'agents',
    'api_agents_capabilities_update':'agents',
    'toggle_agent':                 'agents',
    'set_agent_temperature':        'agents',
    'api_agent_memory':             'agents',
    'api_agent_memory_write':       'agents',
    'api_agents_memories_query':    'agents',

    # ── agent_api (agent self-service) ───────────────────────────────────────
    'api_agent_create_ticket':       'agent_api',
    'api_agent_list_tickets':        'agent_api',
    'api_agent_list_proposals':      'agent_api',
    'api_agent_git_create_proposal': 'agent_api',
    'api_agent_git_list_proposals':  'agent_api',
    'api_agent_git_execute_proposal':'agent_api',
    'api_agent_capabilities':        'agent_api',
    'api_agent_push_think':          'agent_api',
    'api_agent_identity':            'agent_api',

    # ── chat ─────────────────────────────────────────────────────────────────
    '_fetch_chat_thread_rows':             'chat',
    '_chat_history_from_rows':             'chat',
    '_thread_transcript_from_rows':        'chat',
    '_conversation_reply_context_from_rows':'chat',
    '_build_chat_handoff_block':           'chat',
    '_infer_reply_target_from_text':       'chat',
    '_resolve_chat_reply_target':          'chat',
    '_parse_chat_skill_command':           'chat',
    '_is_execution_confirmation':          'chat',
    '_derive_proposal_from_text':          'chat',
    '_extract_skill_lines_from_text':      'chat',
    '_load_local_agent_memories':          'chat',
    '_build_local_memory_block':           'chat',
    '_build_local_agent_prompt':           'chat',
    '_should_attach_ticket_snapshot':       'chat',
    '_build_ticket_snapshot_block':         'chat',
    '_persist_local_agent_memory':          'chat',
    '_friendly_api_error':                  'chat',
    'api_chat':                             'chat',
    'api_chat_jobs_status':                 'chat',
    'api_chat_jobs_cancel':                 'chat',
    'api_chat_librarian_review':            'chat',

    # ── docs ─────────────────────────────────────────────────────────────────
    'api_docs':              'docs',
    'api_docs_text':         'docs',
    'serve_doc_html':        'docs',
    'download_doc_html':     'docs',
    'api_project_md':        'docs',
    'api_project_md_save':   'docs',
    'api_kb_seed_swarm_docs':'docs',
    'api_project_md_raw':    'docs',
    'api_testing_md':        'docs',
    'api_bugs_md':           'docs',
    'api_run_simulation':    'docs',

    # ── nine ─────────────────────────────────────────────────────────────────
    'api_nine_history':  'nine',
    'api_nine_actions':  'nine',
    'api_nine_chat':     'nine',
    'api_nine_stream':   'nine',

    # ── legacy (old pipeline + approval) ─────────────────────────────────────
    'chat':                      'legacy',
    'stream':                    'legacy',
    '_run_pending_for_trusted':  'legacy',
    'approval_action':           'legacy',

    # ── exec ─────────────────────────────────────────────────────────────────
    'api_exec':       'exec_bp',
    'api_exec_write': 'exec_bp',

    # ── debates ──────────────────────────────────────────────────────────────
    'api_debates_list':   'debates',
    'api_debates_create': 'debates',
    'api_debate_turns':   'debates',
    'api_debate_run':     'debates',
    'api_debate_quick':   'debates',

    # ── time_wizard ──────────────────────────────────────────────────────────
    'api_time_timeline':          'time_wizard_bp',
    'api_time_sessions':          'time_wizard_bp',
    'api_time_checkpoint':        'time_wizard_bp',
    'api_time_checkpoints':       'time_wizard_bp',
    'api_time_create_checkpoint': 'time_wizard_bp',
    'api_time_restore':           'time_wizard_bp',
    'api_time_stats':             'time_wizard_bp',
    'api_time_bootstrap':         'time_wizard_bp',
    'api_time_log_decision':      'time_wizard_bp',
    'api_time_decision_history':  'time_wizard_bp',

    # ── killswitch ───────────────────────────────────────────────────────────
    'api_killswitch_buttons':    'killswitch',
    'api_killswitch_emergency':  'killswitch',
    'api_killswitch_pause':      'killswitch',
    'api_killswitch_resume':     'killswitch',
    'api_killswitch_restart':    'killswitch',
    'api_killswitch_agent_reset':'killswitch',

    # ── brief ────────────────────────────────────────────────────────────────
    'api_brief_get':      'brief',
    'api_brief_generate': 'brief',
    'api_brief_history':  'brief',

    # ── decisions ────────────────────────────────────────────────────────────
    'api_decisions':          'decisions',
    'api_decision_detail':    'decisions',
    'api_decision_timeline':  'decisions',

    # ── ollama ───────────────────────────────────────────────────────────────
    'api_ollama_models': 'ollama',
    'api_ollama_load':   'ollama',
    'api_ollama_unload': 'ollama',
    'api_ollama_ps':     'ollama',
}

# ═══════════════════════════════════════════════════════════════════════════════
# Group blocks
# ═══════════════════════════════════════════════════════════════════════════════
grouped = defaultdict(list)
unmapped = []

for block in blocks:
    bp_name = FUNC_MAP.get(block['name'])
    if bp_name is None:
        unmapped.append(block['name'])
        bp_name = SVC
    grouped[bp_name].append(block)

if unmapped:
    print(f'WARNING: {len(unmapped)} unmapped functions → services: {unmapped}')


def get_block_code(block):
    """Get source code for a block (0-indexed start/end)."""
    return ''.join(lines[block['start']:block['end']])


def route_rewrite(code, bp_var='bp'):
    """Replace @app.route with @bp.route."""
    return code.replace('@app.route(', f'@{bp_var}.route(')


# ═══════════════════════════════════════════════════════════════════════════════
# Generate services.py
# ═══════════════════════════════════════════════════════════════════════════════
svc = []

svc.append('''\
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
"""

''')

# Imports (lines 13-64) — sys, pathlib, flask, stdlib, database, ticket, queue_manager
svc.append(L(13, 64))
svc.append('\n')

# queue_intake, estimate_wait_minutes, mark_processing are module-level aliases
# (these are on lines 62-64, already included)

# External module imports (lines 143-150)
svc.append(L(143, 150))
svc.append('\n')

# Time machine loading (lines 152-160)
svc.append(L(152, 160))
svc.append('\n')

# kill_switch (line 160 already included above)

# Shared state variables — skip app = Flask (line 162)
# Lines 179-209: DISABLED_AGENTS, _original_ask_agent, _streams, chat jobs, executors
svc.append(L(179, 182))  # DISABLED_AGENTS, _original_ask_agent

# The _patched_ask_agent function is a parsed block — it will be added with other service funcs
# But the orchestrator.ask_agent assignment is on line 189 — module-level
# Include lines 189 as a post-function fixup (handled below)

svc.append('\n')
svc.append(L(191, 209))  # _streams, shell streams, chat jobs, executors
svc.append('\n')

# Agent metadata dicts (lines 211-296)
svc.append(L(211, 296))
svc.append('\n')

# _AGENT_TABLES dict (line 654 onwards — find exact end)
# Find end of _AGENT_TABLES
idx = 654 - 1  # 0-indexed
while idx < TOTAL and not (lines[idx].strip() and not lines[idx][0].isspace() and idx > 654):
    idx += 1
    if idx < TOTAL and lines[idx].strip().startswith('}'):
        idx += 1
        break
svc.append(L(654, idx))
svc.append('\n')

# _AGENT_ROSTER list (line 6306 onwards)
idx = 6306 - 1
bracket_depth = 0
for j in range(idx, min(idx + 80, TOTAL)):
    bracket_depth += lines[j].count('[') - lines[j].count(']')
    if bracket_depth <= 0 and j > idx:
        idx = j + 1
        break
svc.append(L(6306, idx))
svc.append('\n')

# Service functions (parsed blocks assigned to SVC)
# Sort by original line number to maintain order
svc_blocks = sorted(grouped.get(SVC, []), key=lambda b: b['start'])
for block in svc_blocks:
    code = get_block_code(block)
    svc.append('\n')
    svc.append(code)

# Add the orchestrator monkey-patch line AFTER _patched_ask_agent
svc.append('\norchestrator.ask_agent = _patched_ask_agent\n')

# __all__ — export everything (including underscore names) for `from services import *`
all_names = []
# Module-level variables
for name in [
    'SWARM_ROOT', 'DISABLED_AGENTS', '_original_ask_agent', '_patched_ask_agent',
    '_streams', '_SHELL_STREAM_LOCK', '_SHELL_STREAM_PROCS',
    '_CHAT_JOB_LOCK', '_CHAT_JOBS', '_CHAT_JOB_TTL_SECONDS',
    '_CHAT_DISPATCH_EXECUTOR', '_CHAT_WORKER_EXECUTOR',
    '_CHAT_AGENT_ETA_SECONDS', '_CHAT_AGENT_RUNTIME_CLASS',
    '_CHAT_SINGLE_TASK_LOCAL_AGENTS', '_CHAT_PARTICIPANT_ALIASES',
    '_AGENT_TABLES', '_AGENT_ROSTER',
    'THEME_SYNC_REMINDER',
    # External modules
    'orchestrator', 'time_wizard', 'kill_switch',
    '_TAVILY_OK', '_tavily_search',
    # queue manager
    'queue_intake', 'estimate_wait_minutes', 'mark_processing',
    # database re-exports
    'get_connection', 'new_conversation', 'log_message',
    'use_approval_token', 'add_trusted_sender', 'remove_trusted_sender',
    'add_notification_sender', 'remove_notification_sender',
    'get_pending_emails', 'mark_pending_processed', 'log_activity',
    'list_user_profiles', 'get_user_profile', 'upsert_user_profile',
    'list_user_skill_permissions', 'set_user_skill_permission',
    'can_user_invoke_skill', 'initialise_database',
    'get_agent_memory', 'save_agent_memory', 'agent_has_capability',
    'grant_agent_capability', 'revoke_agent_capability',
    'get_agent_capabilities', 'AGENT_CAPABILITY_REGISTRY',
    'persist_chat_job', 'update_chat_job_db',
    'get_chat_jobs_by_ids', 'mark_orphaned_chat_jobs',
    # ticket
    'ticket_create', 'librarian_close',
    # theme
    'get_themed_html',
    # monitor/sandpits/clock
    'get_system_status', 'get_sandpit_stats', 'sandpit_log',
    'get_timestamp', 'get_timestamp_iso', 'get_full_time_string',
    # stdlib re-exports commonly used in blueprints
    'json', 'queue', 'threading', 'os', 'time', 'uuid', 're', 'socket',
    'datetime', 'timezone', 'ThreadPoolExecutor', 'FuturesTimeoutError',
    'Flask', 'request', 'Response', 'jsonify',
    'Path',
]  + [b['name'] for b in svc_blocks]:
    all_names.append(name)

svc.append('\n\n__all__ = [\n')
for name in sorted(set(all_names)):
    svc.append(f"    '{name}',\n")
svc.append(']\n')

with open(SVC_PATH, 'w') as f:
    f.write(''.join(svc))
print(f'Created {SVC_PATH} ({sum(1 for c in "".join(svc) if c == chr(10))} lines)')

# ═══════════════════════════════════════════════════════════════════════════════
# Generate blueprint files
# ═══════════════════════════════════════════════════════════════════════════════
os.makedirs(BP_DIR, exist_ok=True)

# __init__.py
init_path = os.path.join(BP_DIR, '__init__.py')
if not os.path.exists(init_path):
    with open(init_path, 'w') as f:
        f.write('# Blueprint package\n')
    print(f'Created {init_path}')

# Blueprint metadata: name → (variable_name, human_label)
BP_META = {
    'system':         ('system_bp',         'System & Monitoring'),
    'conversations':  ('conversations_bp',  'Conversations'),
    'tickets':        ('tickets_bp',        'Tickets'),
    'memory':         ('memory_bp',         'Memory'),
    'kb':             ('kb_bp',             'Knowledge Base'),
    'proposals':      ('proposals_bp',      'Proposals & Queue'),
    'git':            ('git_bp',            'Git Operations'),
    'workspace':      ('workspace_bp',      'Workspace & Code Ops'),
    'shell':          ('shell_bp',          'Shell & Terminal'),
    'auth':           ('auth_bp',           'Auth & Senders'),
    'agents':         ('agents_bp',         'Agents Config'),
    'agent_api':      ('agent_api_bp',      'Agent Self-Service API'),
    'chat':           ('chat_bp',           'Chat Engine'),
    'docs':           ('docs_bp',           'Docs & Project Files'),
    'nine':           ('nine_bp',           'Agent Nine'),
    'legacy':         ('legacy_bp',         'Legacy Pipeline & Approval'),
    'exec_bp':        ('exec_bp',           'Ghost Exec'),
    'debates':        ('debates_bp',        'Debates'),
    'time_wizard_bp': ('time_wizard_bp',    'Time Wizard'),
    'killswitch':     ('killswitch_bp',     'Kill Switches'),
    'brief':          ('brief_bp',          'Ghost Brief'),
    'decisions':      ('decisions_bp',      'Decisions & Timeline'),
    'ollama':         ('ollama_bp',         'Ollama Models'),
}

# Extra module-level code to prepend to specific blueprints
EXTRA_MODULE_CODE = {
    'memory': '# Agent memory table mapping\n' + L(654, 672) + '\n',
    'docs': (
        '# Docs directory setup\n'
        + L(3310, 3327) + '\n'
    ),
    'exec_bp': (
        '# Ghost Layer exec\n'
        + L(7190, 7193) + '\n'
        + L(7231, 7234) + '\n'
    ),
}

for bp_key, (bp_var, bp_label) in BP_META.items():
    bp_blocks = sorted(grouped.get(bp_key, []), key=lambda b: b['start'])
    if not bp_blocks and bp_key not in EXTRA_MODULE_CODE:
        continue

    parts = []
    # File header
    parts.append(f'"""{bp_key}.py — {bp_label} routes"""\n')
    parts.append(f'from flask import Blueprint, request, Response, jsonify, send_file\n')
    parts.append(f'from services import *\n\n')

    # Blueprint creation
    # Use the key as the blueprint name to avoid clashes
    parts.append(f"{bp_var} = Blueprint('{bp_key}', __name__)\n\n")

    # Extra module-level code
    if bp_key in EXTRA_MODULE_CODE:
        parts.append(EXTRA_MODULE_CODE[bp_key])
        parts.append('\n')

    # Function blocks
    for block in bp_blocks:
        code = get_block_code(block)
        if block['is_route']:
            code = route_rewrite(code, bp_var)
        parts.append(code)
        parts.append('\n')

    # Write file
    fp = os.path.join(BP_DIR, f'{bp_key}.py')
    with open(fp, 'w') as f:
        f.write(''.join(parts))
    route_count = sum(1 for b in bp_blocks if b['is_route'])
    helper_count = sum(1 for b in bp_blocks if not b['is_route'])
    total_lines = sum(1 for c in ''.join(parts) if c == '\n')
    print(f'Created {fp} ({total_lines} lines, {route_count} routes, {helper_count} helpers)')


# ═══════════════════════════════════════════════════════════════════════════════
# Generate terminal_new.py (slim app factory)
# ═══════════════════════════════════════════════════════════════════════════════

# Collect all blueprint imports
bp_imports = []
bp_registers = []
for bp_key, (bp_var, bp_label) in sorted(BP_META.items()):
    bp_imports.append(f'from blueprints.{bp_key} import {bp_var}')
    bp_registers.append(f'    app.register_blueprint({bp_var})')

new_terminal = f'''\
"""
terminal.py — Fridays / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Slim app factory. All routes live in blueprints/.
Shared state and helpers live in services.py.

python3 terminal.py
═══════════════════════════════════════════════════════════════════════════════
"""
import sys
import os
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

# Ensure services module is importable (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import (
    Flask, initialise_database, mark_orphaned_chat_jobs,
    SWARM_ROOT, time_wizard, orchestrator,
)

# ── Blueprint imports ────────────────────────────────────────────────────────
from vs_tools import vs_bp
{chr(10).join(bp_imports)}


def create_app():
    app = Flask(__name__)

    # Ensure schema/migrations are present before serving APIs.
    try:
        initialise_database()
    except Exception as exc:
        print(f'[Terminal] database bootstrap warning: {{exc}}')

    # Mark orphaned chat jobs from previous process.
    try:
        mark_orphaned_chat_jobs()
    except Exception as exc:
        print(f'[Terminal] chat job orphan cleanup warning: {{exc}}')

    # Register blueprints
    app.register_blueprint(vs_bp)
{chr(10).join(bp_registers)}

    return app


# ── Server startup ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Bootstrap Time Wizard session
    try:
        session_id = time_wizard.bootstrap_session()
        if session_id:
            print(f'[Time Wizard] Session started: {{session_id}}')
    except Exception as e:
        print(f'[Time Wizard] Bootstrap warning: {{e}}')

    app = create_app()

    class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    try:
        server = make_server('::', 5050, app, server_class=_ThreadingWSGIServer)
        addr_family = 'IPv6+IPv4'
    except OSError:
        server = make_server('0.0.0.0', 5050, app, server_class=_ThreadingWSGIServer)
        addr_family = 'IPv4'

    print(f'[Terminal] Serving on port 5050 ({{addr_family}})')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\\n[Terminal] Shutting down.')
        server.shutdown()
'''

with open(NEW_TERM, 'w') as f:
    f.write(new_terminal)
print(f'Created {NEW_TERM}')

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
print('\n' + '═' * 72)
print('EXTRACTION COMPLETE')
print('═' * 72)
print(f'  services.py          — shared state + {len(grouped.get(SVC, []))} helpers')
print(f'  terminal_new.py      — slim app factory')
print(f'  blueprints/          — {len(BP_META)} blueprint modules')
total_routes = sum(1 for b in blocks if b['is_route'])
total_helpers = sum(1 for b in blocks if not b['is_route'])
print(f'  Total:  {total_routes} routes + {total_helpers} helpers = {len(blocks)} functions')
print()
print('Next steps:')
print('  1. Review generated files')
print('  2. cp terminal.py terminal.py.monolith')
print('  3. cp terminal_new.py terminal.py')
print('  4. sudo systemctl restart swarm-terminal')
print('  5. curl localhost:5050/api/health')
