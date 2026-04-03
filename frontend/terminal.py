"""
terminal.py — Fridays / Seven's Swarm
═══════════════════════════════════════════════════════════════════════════════
Swarm terminal web UI. Port 5050. Tailscale only.

Three agent panels, SSE streaming, kill switches, memory browser, ticket log.
Bypasses email. Creates real tickets. Duck still runs. Memory still writes.

python3 terminal.py
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import importlib.util
from pathlib import Path

SWARM_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWARM_ROOT))
sys.path.insert(0, str(SWARM_ROOT / 'utils'))
sys.path.insert(0, str(SWARM_ROOT / 'core' / 'pipeline'))
sys.path.insert(0, str(SWARM_ROOT / 'lib' / 'system'))
sys.path.insert(0, str(SWARM_ROOT / 'frontend'))
sys.path.insert(0, str(SWARM_ROOT / 'core'))  # must precede lib/system to avoid shadow time_machine

from flask import Flask, render_template, request, Response, jsonify
import json
import queue
import threading
import os
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
                       get_agent_capabilities, AGENT_CAPABILITY_REGISTRY)
from ticket import create as ticket_create, librarian_close
import queue_manager as _queue_manager

queue_intake = _queue_manager.intake
estimate_wait_minutes = _queue_manager.estimate_wait_minutes
mark_processing = _queue_manager.mark_processing


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

    conn = get_connection()
    try:
        conn.execute(
            """UPDATE work_proposals SET status=?, ticket_number=?, updated_at=datetime('now')
               WHERE proposal_id=?""",
            (status, ticket_number, proposal_id)
        )
        conn.commit()
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

app = Flask(__name__)

# Ensure schema/migrations are present before serving APIs.
try:
    initialise_database()
except Exception as exc:
    print(f'[Terminal] database bootstrap warning: {exc}')

# ── Kill switches ──────────────────────────────────────────────────────────────
# Any agent name in this set is skipped by the pipeline.
DISABLED_AGENTS = set()

_original_ask_agent = orchestrator.ask_agent

def _patched_ask_agent(agent_name, prompt):
    if agent_name in DISABLED_AGENTS:
        print(f'[Terminal] {agent_name} offline — kill switch active')
        return f'[{agent_name} is currently offline]'
    return _original_ask_agent(agent_name, prompt)

orchestrator.ask_agent = _patched_ask_agent

# ── Active SSE streams  ────────────────────────────────────────────────────────
# ticket_number → queue.Queue of event dicts. None = stream closed.
_streams = {}

# ── Active terminal shell streams (for stop support) ─────────────────────────
_SHELL_STREAM_LOCK = threading.Lock()
_SHELL_STREAM_PROCS = {}

# ── Persistent chat jobs (timeout-safe) ───────────────────────────────────────
_CHAT_JOB_LOCK = threading.Lock()
_CHAT_JOBS = {}
_CHAT_JOB_TTL_SECONDS = 2 * 60 * 60

_CHAT_AGENT_ETA_SECONDS = {
    'gemma': 85,
    'llama': 70,
    'qwen': 120,
    'librarian': 50,
    'duck': 35,
    'sniffles': 160,
    'nine': 8,
    'ten': 8,
    'eleven': 10,
    'twelve': 10,
}

_CHAT_AGENT_RUNTIME_CLASS = {
    'gemma': 'local',
    'llama': 'local',
    'qwen': 'local',
    'eight': 'local',
    'librarian': 'local',
    'duck': 'local',
    'sniffles': 'local',
    'nine': 'paid',
    'ten': 'paid',
    'eleven': 'paid',
    'twelve': 'paid',
}


def _chat_now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _chat_eta_seconds(agent):
    return int(_CHAT_AGENT_ETA_SECONDS.get((agent or '').lower(), 60))


def _chat_runtime_class(agent):
    return _CHAT_AGENT_RUNTIME_CLASS.get((agent or '').lower(), 'unknown')


_CHAT_PARTICIPANT_ALIASES = {
    'user': 'user',
    'ghost': 'user',
    'gemma': 'gemma',
    'llama': 'llama',
    'qwen': 'qwen',
    'eight': 'eight',
    'librarian': 'librarian',
    'duck': 'duck',
    'sniffles': 'sniffles',
    'nine': 'nine',
    'claude': 'nine',
    'ten': 'ten',
    'copilot': 'ten',
    'eleven': 'eleven',
    'grok': 'eleven',
    'twelve': 'twelve',
    'timewizard': 'twelve',
    'timewizardagent': 'twelve',
    'fridays': 'fridays',
}


def _normalize_chat_participant(name):
    raw = str(name or '').strip().lower()
    if not raw:
        return ''
    squashed = re.sub(r'[^a-z0-9]+', '', raw)
    return _CHAT_PARTICIPANT_ALIASES.get(squashed, _CHAT_PARTICIPANT_ALIASES.get(raw, raw))


def _display_chat_participant(name):
    canonical = _normalize_chat_participant(name)
    labels = {
        'user': 'USER',
        'gemma': 'GEMMA',
        'llama': 'LLAMA',
        'qwen': 'QWEN',
        'eight': 'EIGHT',
        'librarian': 'LIBRARIAN',
        'duck': 'DUCK',
        'sniffles': 'SNIFFLES',
        'nine': 'NINE (CLAUDE SONNET 4.6)',
        'ten': 'TEN (GPT-5.3-CODEX)',
        'eleven': 'ELEVEN (GROK API)',
        'twelve': 'TWELVE (CLAUDE HAIKU)',
        'fridays': 'FRIDAYS',
    }
    if canonical in labels:
        return labels[canonical]
    return str(name or 'AGENT').strip().upper() or 'AGENT'


def _fetch_chat_thread_rows(conv_id, limit=20):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT from_agent, to_agent, content
               FROM messages
               WHERE conversation_id=?
                 AND LOWER(from_agent) != 'fridays'
               ORDER BY id DESC
               LIMIT ?""",
            (conv_id, limit)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in reversed(rows)]


def _chat_history_from_rows(rows):
    history = []
    for row in rows:
        sender = _normalize_chat_participant(row.get('from_agent'))
        target = _normalize_chat_participant(row.get('to_agent'))
        role = 'user' if sender == 'user' else 'assistant'
        route = _display_chat_participant(sender or row.get('from_agent'))
        if target:
            route += f' -> {_display_chat_participant(target)}'
        content = str(row.get('content') or '').strip()
        history.append({'role': role, 'content': f'{route}: {content}'})
    return history


def _thread_transcript_from_rows(rows):
    if not rows:
        return ''
    lines = []
    for row in rows:
        sender = _normalize_chat_participant(row.get('from_agent'))
        target = _normalize_chat_participant(row.get('to_agent'))
        route = _display_chat_participant(sender or row.get('from_agent'))
        if target:
            route += f' -> {_display_chat_participant(target)}'
        text = str(row.get('content') or '').strip()
        lines.append(f'{route}: {text[:500]}')
    return '\n'.join(lines)


def _conversation_reply_context_from_rows(rows, selected_agent):
    selected = _normalize_chat_participant(selected_agent)
    latest_sender = 'user'
    previous_participant = ''
    prior_agent = ''

    if rows:
        latest_sender = _normalize_chat_participant(rows[-1].get('from_agent')) or 'user'
        for row in reversed(rows[:-1]):
            sender = _normalize_chat_participant(row.get('from_agent'))
            if sender and sender != selected:
                previous_participant = sender
                break
        for row in reversed(rows[:-1]):
            sender = _normalize_chat_participant(row.get('from_agent'))
            if sender and sender not in {'user', selected}:
                prior_agent = sender
                break

    default_reply_target = latest_sender or 'user'
    if default_reply_target == selected:
        default_reply_target = previous_participant or 'user'

    return {
        'latest_sender': latest_sender or 'user',
        'previous_participant': previous_participant,
        'prior_agent': prior_agent,
        'default_reply_target': default_reply_target or 'user',
    }


def _build_chat_handoff_block(selected_agent, reply_context):
    latest_sender = _display_chat_participant(reply_context.get('latest_sender') or 'user')
    previous_participant = reply_context.get('previous_participant') or ''
    prior_agent = reply_context.get('prior_agent') or ''
    default_target = _display_chat_participant(reply_context.get('default_reply_target') or 'user')

    lines = [
        '=== Thread routing ===',
        f'You are {selected_agent.upper()}.',
        f'Latest visible sender: {latest_sender}',
        f'Default reply target: {default_target}',
    ]
    if previous_participant:
        lines.append(f'Previous participant before that: {_display_chat_participant(previous_participant)}')
    if prior_agent:
        lines.append(f'Active collaborator already in thread: {_display_chat_participant(prior_agent)}')
    lines.extend([
        'If you are addressing another agent directly, open with their name followed by a comma.',
        'If the user is looping you into an existing agent discussion, you may reply to that agent directly.',
        'Otherwise, answer the latest visible sender.',
        '',
    ])
    return '\n'.join(lines)


def _infer_reply_target_from_text(response_text):
    text = str(response_text or '').strip()
    if not text:
        return ''
    first_line = text.splitlines()[0].strip()
    match = re.match(r'^(?:@)?([A-Za-z][A-Za-z0-9_ /-]{0,30})\s*[:,]\s+', first_line)
    if not match:
        return ''
    return _normalize_chat_participant(match.group(1))


def _resolve_chat_reply_target(selected_agent, response_text, reply_context):
    explicit = _infer_reply_target_from_text(response_text)
    selected = _normalize_chat_participant(selected_agent)
    if explicit and explicit != selected and explicit != 'fridays':
        return explicit

    fallback = _normalize_chat_participant(reply_context.get('default_reply_target')) or 'user'
    if fallback == selected:
        fallback = _normalize_chat_participant(reply_context.get('previous_participant')) or 'user'
    if fallback == 'ghost':
        return 'user'
    return fallback or 'user'


def _chat_stage_for(agent, elapsed_ms):
    elapsed = max(0, int(elapsed_ms or 0))
    if agent == 'gemma':
        if elapsed < 8000:
            return 'assembling context'
        if elapsed < 22000:
            return 'reasoning/debating'
        if elapsed < 45000:
            return 'synthesizing response'
        return 'finalizing answer'
    if agent in {'duck', 'sniffles'}:
        if elapsed < 4000:
            return 'assembling audit context'
        if elapsed < 16000:
            return 'reviewing evidence'
        return 'writing findings'
    if agent in {'llama', 'qwen', 'eight', 'librarian'}:
        if elapsed < 4000:
            return 'loading local memory'
        if elapsed < 16000:
            return 'processing thread hand-off'
        return 'drafting response'
    if elapsed < 6000:
        return 'loading context'
    if elapsed < 18000:
        return 'reasoning'
    return 'finalizing answer'


def _chat_update_job(job_id, *, stage=None, status=None, eta_seconds=None, error=None):
    if not job_id:
        return
    with _CHAT_JOB_LOCK:
        job = _CHAT_JOBS.get(job_id)
        if not job:
            return
        now_ts = time.time()
        now_iso = _chat_now_iso()
        if stage is not None:
            job['stage'] = str(stage)
        if status is not None:
            job['status'] = str(status)
        if eta_seconds is not None:
            try:
                job['eta_seconds'] = max(0, int(eta_seconds))
            except Exception:
                pass
        if error is not None:
            job['error'] = str(error)
        job['updated_ts'] = now_ts
        job['updated_at'] = now_iso


def _cleanup_chat_jobs_locked():
    now = time.time()
    stale = []
    for jid, job in _CHAT_JOBS.items():
        finished = job.get('status') in {'completed', 'failed', 'cancelled'}
        updated = float(job.get('updated_ts') or job.get('started_ts') or now)
        if finished and (now - updated) > _CHAT_JOB_TTL_SECONDS:
            stale.append(jid)
    for jid in stale:
        _CHAT_JOBS.pop(jid, None)


def _chat_job_public(job):
    elapsed_ms = int((time.time() - float(job.get('started_ts') or time.time())) * 1000)
    eta_seconds = int(job.get('eta_seconds') or _chat_eta_seconds(job.get('agent')))
    elapsed_seconds = max(0, int(elapsed_ms / 1000))
    status = job.get('status', 'running')
    if status in {'completed', 'failed', 'cancelled'}:
        eta_remaining_seconds = 0
    else:
        eta_remaining_seconds = max(0, eta_seconds - elapsed_seconds)
    return {
        'job_id': job.get('job_id'),
        'conversation_id': job.get('conversation_id'),
        'agent': job.get('agent'),
        'status': status,
        'runtime_class': job.get('runtime_class') or _chat_runtime_class(job.get('agent')),
        'stage': job.get('stage') or _chat_stage_for(job.get('agent'), elapsed_ms),
        'eta_seconds': eta_seconds,
        'eta_remaining_seconds': eta_remaining_seconds,
        'started_at': job.get('started_at'),
        'updated_at': job.get('updated_at'),
        'elapsed_ms': elapsed_ms,
        'error': job.get('error', ''),
    }

from vs_tools import vs_bp
app.register_blueprint(vs_bp)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _recent_conversations(limit=40):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, source, created_at FROM conversations ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    # Alias created_at to timestamp for frontend compatibility
    return [dict(r, timestamp=r['created_at']) for r in rows]


def _tickets(limit=100, status=None):
    conn = get_connection()
    if status in ('open', 'closed'):
        where = "WHERE t.status = ?"
        params = (status, limit)
    else:
        where = ""
        params = (limit,)
    rows = conn.execute(
        f"""SELECT t.ticket_number, t.status, t.duck_result, t.gemma_routing,
                  t.created_at, t.closed_at, t.sender_email, t.question,
                  COALESCE(q.priority, 5) AS priority,
                  COUNT(DISTINCT tn.id) AS note_count,
                  COUNT(DISTINCT CASE WHEN s.fired=0 THEN s.id END) AS snooze_count
           FROM tickets t
           LEFT JOIN queue q ON q.id = t.queue_id
           LEFT JOIN ticket_notes tn ON tn.ticket_id = t.id
           LEFT JOIN snoozed_tickets s ON s.ticket_number = t.ticket_number
           {where}
           GROUP BY t.id
           ORDER BY t.id DESC LIMIT ?""",
        params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


_AGENT_TABLES = {
    'llama':    'memory_llama',
    'qwen':     'memory_qwen',
    'gemma':    'memory_gemma',
    'eight':    'memory_eight',
    'nine':     'memory_nine',
    'ten':      'memory_ten',
    'eleven':   'memory_grok',
    'grok':     'memory_grok',
    'twelve':   'memory_twelve',
    'scholar':  'memory',
    'seeker':   'memory',
    'librarian':'memory',
    'duck':     'memory',
    'sniffles': 'memory',
}


def _collect_local_file_memories(query='', agent='', limit=120):
    """Collect local file-based memories from sandpits for UI visibility."""
    sandpit_root = Path('/home/seven/swarm/sandpits')
    if not sandpit_root.exists():
        return []

    query_l = str(query or '').strip().lower()
    agent_l = str(agent or '').strip().lower()
    rows = []

    # Keep this tight so Memory tile stays readable and fast.
    file_priority = (
        'WHO_AM_I.md',
        'DISPATCHED_WORK.md',
        'THINK.md',
        'MEMORY.md',
        'NOTES.md',
        'notes.md',
    )
    shared_files = ('COORDINATION.md', 'CURRENT_FOCUS.md', 'STALE_PROPOSALS.md')

    def _match_and_add(path: Path, owner_agent: str, importance: int):
        if not path.exists() or not path.is_file():
            return
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return

        subject = path.name
        searchable = f"{subject}\n{content}".lower()
        if query_l and query_l not in searchable:
            return

        # Stable synthetic id for read-only UI cards.
        synthetic_id = int(uuid.uuid5(uuid.NAMESPACE_URL, str(path)).int % 2_000_000_000)
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')

        rows.append({
            'id': synthetic_id,
            'source_table': 'local_file',
            'agent': owner_agent,
            'subject': subject,
            'content': content[:4000],
            'tags': 'local_file,sandpit',
            'importance': importance,
            'created_at': mtime,
            'source': str(path),
        })

    for child in sandpit_root.iterdir():
        if not child.is_dir():
            continue
        name_l = child.name.lower()
        if agent_l and agent_l not in (name_l,):
            continue

        if name_l == 'shared':
            for fname in shared_files:
                _match_and_add(child / fname, 'shared', 6)
            continue

        for fname in file_priority:
            imp = 8 if fname == 'WHO_AM_I.md' else 5
            _match_and_add(child / fname, name_l, imp)

    rows.sort(key=lambda r: (r.get('created_at') or ''), reverse=True)
    return rows[:max(1, int(limit or 120))]

def _memory_search(query='', min_importance=3, agent='', limit=50):
    conn = get_connection()
    like = f'%{query}%'

    agent_key = agent.lower() if agent else ''
    if agent_key in ('llama', 'qwen', 'gemma', 'eight', 'nine', 'ten', 'grok', 'eleven'):
        tbl = _AGENT_TABLES[agent_key]
        archived_clause = "AND archived = 0"
        rows = conn.execute(
            f"""SELECT id, '{tbl}' AS source_table, agent, subject, content, tags, importance, created_at
               FROM {tbl}
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? {archived_clause}
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, limit)
        ).fetchall()
    elif agent_key == 'twelve':
        rows = conn.execute(
            """SELECT id, 'memory_twelve' AS source_table, agent, '' AS subject, content, tags, importance, created_at
               FROM memory_twelve
               WHERE (content LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, limit)
        ).fetchall()
    elif agent_key:
        rows = conn.execute(
            """SELECT id, 'memory' AS source_table, agent, subject AS title, content, tags, importance, created_at
               FROM memory
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
                 AND agent LIKE ?
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance, f'%{agent}%', limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, 'memory' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_llama' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_llama
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_qwen' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_qwen
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_gemma' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_gemma
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_eight' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_eight
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_nine' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_nine
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_ten' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_ten
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_grok' AS source_table, agent, subject, content, tags, importance, created_at
               FROM memory_grok
               WHERE (subject LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               UNION ALL
               SELECT id, 'memory_twelve' AS source_table, agent, '' AS subject, content, tags, importance, created_at
               FROM memory_twelve
               WHERE (content LIKE ? OR content LIKE ? OR tags LIKE ?)
                 AND importance >= ? AND archived = 0
               ORDER BY created_at DESC, importance DESC LIMIT ?""",
            (like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             like, like, like, min_importance,
             limit)
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def _duck_stats():
    conn = get_connection()
    total  = conn.execute("SELECT COUNT(*) FROM duck_log").fetchone()[0]
    passed = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'").fetchone()[0]
    conn.close()
    return {'total': total, 'passed': passed, 'failed': failed}


def _log_proposal_duck_review(proposal_id, title, review_text, result, reason):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO duck_log (ticket_number, question, answer, result, reason)
               VALUES (?, ?, ?, ?, ?)""",
            (proposal_id, title[:100], review_text[:500], result, reason[:500])
        )
        conn.commit()
    finally:
        conn.close()


def _run_proposal_duck_review(row):
    title = (row['title'] or '').strip()
    description = (row['description'] or '').strip()
    review_text = f'{title}\n{description}'.strip()
    lowered = review_text.lower()

    if len(title) < 8:
        return {'result': 'NO', 'reason': 'proposal title is too short for meaningful review'}
    if len(description) < 24:
        return {'result': 'NO', 'reason': 'proposal description is too short for queue-visible approval'}
    if any(marker in lowered for marker in ('tbd', 'todo', '[pending]', 'placeholder', 'fix later')):
        return {'result': 'NO', 'reason': 'proposal still contains placeholder or unresolved review language'}
    if '.history' in lowered and 'ghost-layer' not in lowered and 'ghost layer' not in lowered:
        return {'result': 'NO', 'reason': '.history references must stay explicitly ghost-layer scoped'}

    return {'result': 'YES', 'reason': 'proposal passed Duck first-pass review'}


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
    Enforce proposal approval for mutating actions while Time Wizard is active.
    Returns a Flask response tuple on failure, else None.
    """
    if not _is_time_wizard_active():
        return None

    proposal_id = (data.get('proposal_id') or '').strip()
    if not proposal_id:
        return jsonify({
            'ok': False,
            'error': 'proposal_id required while Time Wizard is active',
            'action': action_name,
            'required_status': ['approved', 'executed']
        }), 428

    conn = get_connection()
    row = conn.execute(
        "SELECT proposal_id, status, agent, title FROM work_proposals WHERE proposal_id=?",
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({
            'ok': False,
            'error': f'proposal not found: {proposal_id}',
            'action': action_name
        }), 404

    if row['status'] not in ('approved', 'executed'):
        return jsonify({
            'ok': False,
            'error': f'proposal status not permitted: {row["status"]}',
            'action': action_name,
            'proposal_id': proposal_id,
            'required_status': ['approved', 'executed']
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
    valid_agents = {a['name'].lower() for a in _AGENT_ROSTER}
    if agent_id.lower() not in valid_agents:
        log_activity('terminal', 'agent_auth_unknown', f'unknown agent_id: {agent_id}')
        # Still allow it; agents can register themselves
    
    return agent_id, None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/api/health')
def api_health():
    """Lightweight health check endpoint. Returns 200 if server is up."""
    return jsonify({'ok': True, 'status': 'up', 'service': 'swarm-terminal'})


# ── Agent Self-Service APIs (Local Agents Create & Query Tickets) ──────────────

@app.route('/api/agent/tickets', methods=['POST'])
def api_agent_create_ticket():
    """
    Allow a local agent to create a ticket/proposal directly via API.
    
    Requires headers:
    - X-Agent-Key: AGENT_API_KEY environment variable
    - X-Agent-Id: agent name (gemma, qwen, llama, etc.)
    
    JSON payload:
    - title: proposal title (required)
    - description: proposal description (proposed work)
    - priority: 1-10 (default 5, lower = more urgent)
    - tags: comma-separated tags (optional)
    
    Returns: {ok, queue_id, proposal_id, created_at}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)
    
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    
    # Use intake_internal which already handles queue + proposal creation
    queue_id, proposal_id = intake_internal(agent_id, title, description, priority=priority)
    
    created_at = datetime.now(timezone.utc).isoformat()
    log_activity(
        'terminal',
        'agent_ticket_created',
        f'agent={agent_id} proposal_id={proposal_id}'
    )
    
    return jsonify({
        'ok': True,
        'queue_id': queue_id,
        'proposal_id': proposal_id,
        'created_at': created_at
    }), 201


@app.route('/api/agent/tickets', methods=['GET'])
def api_agent_list_tickets():
    """
    Agent queries: what tickets have I created?
    
    Requires: X-Agent-Key, X-Agent-Id headers
    
    Query params:
    - status: filter by status (queued, processing, completed, failed)
    - limit: max results (default 50)
    
    Returns: {ok, tickets: [{queue_id, proposal_id, title, status, created_at, ...}]}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    status = request.args.get('status', '').strip()
    limit = int(request.args.get('limit', 50) or 50)
    
    conn = get_connection()
    try:
        query = "SELECT * FROM queue WHERE agent=?"
        params = [agent_id]
        
        if status:
            query += " AND status=?"
            params.append(status)
        
        query += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
        
        # Also fetch linked proposals
        tickets = []
        for row in rows:
            ticket_dict = dict(row)
            proposal = conn.execute(
                "SELECT proposal_id, status AS proposal_status FROM work_proposals WHERE queue_id=? LIMIT 1",
                (ticket_dict['id'],)
            ).fetchone()
            if proposal:
                ticket_dict['proposal_id'] = proposal['proposal_id']
                ticket_dict['proposal_status'] = proposal['proposal_status']
            tickets.append(ticket_dict)
        
        return jsonify({'ok': True, 'agent_id': agent_id, 'tickets': tickets})
    finally:
        conn.close()


@app.route('/api/agent/proposals', methods=['GET'])
def api_agent_list_proposals():
    """
    List pending proposals (for agent coordination).
    Used by Fridays orchestrator to see what work needs doing.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    
    Query params:
    - status: filter (pending, approved, rejected, executed)
    - agent: filter by target agent (optional)
    - limit: max results (default 50)
    
    Returns: {ok, proposals: [{proposal_id, agent, title, status, ticket_link, ...}]}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    status = request.args.get('status', 'pending').strip()  # Default to pending
    filter_agent = request.args.get('agent', '').strip()
    limit = int(request.args.get('limit', 50) or 50)
    
    conn = get_connection()
    try:
        query = "SELECT proposal_id, agent, title, description, status, queue_id, created_at, updated_at FROM work_proposals WHERE 1=1"
        params = []
        
        if status:
            query += " AND status=?"
            params.append(status)
        
        if filter_agent:
            query += " AND agent=?"
            params.append(filter_agent)
        
        query += f" ORDER BY created_at DESC LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
        
        proposals = [dict(row) for row in rows]
        
        return jsonify({'ok': True, 'proposals': proposals})
    finally:
        conn.close()


@app.route('/api/agent/git/proposals', methods=['POST'])
def api_agent_git_create_proposal():
    """
    Agent creates a Git ALM proposal (stage, unstage, or commit).

    Requires: X-Agent-Key, X-Agent-Id headers
    JSON:
      - action: stage | unstage | commit
      - paths: ["file1", ...] or path: "file1" (for stage/unstage)
      - message: commit message (for commit)
      - priority: optional 1..10
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response

    try:
        if not agent_has_capability(agent_id, 'git_propose'):
            return jsonify({'ok': False, 'error': f'agent {agent_id} lacks git_propose capability'}), 403
    except Exception:
        pass

    data = request.get_json() or {}
    action = str(data.get('action') or '').strip().lower()
    priority = int(data.get('priority', 4) or 4)

    if action not in ('stage', 'unstage', 'commit'):
        return jsonify({'ok': False, 'error': 'action must be stage, unstage, or commit'}), 400

    raw_paths = data.get('paths') or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not raw_paths and data.get('path'):
        raw_paths = [data.get('path')]
    message = str(data.get('message') or '').strip()

    try:
        rel_paths = [_git_rel_path(item) for item in raw_paths if str(item or '').strip()]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    if action in ('stage', 'unstage') and not rel_paths:
        return jsonify({'ok': False, 'error': 'paths required for stage/unstage'}), 400
    if action == 'commit' and not message:
        return jsonify({'ok': False, 'error': 'message required for commit'}), 400

    title = {
        'stage': 'Git stage file',
        'unstage': 'Git unstage file',
        'commit': 'Git commit staged changes',
    }[action]
    description = _build_git_operation_description(action, rel_paths, message)

    queue_id, proposal_id = intake_internal(agent_id, title, description, priority=priority)
    log_activity('terminal', 'agent_git_proposal_created', f'agent={agent_id} proposal_id={proposal_id} action={action}')
    return jsonify({
        'ok': True,
        'agent_id': agent_id,
        'queue_id': queue_id,
        'proposal_id': proposal_id,
        'action': action,
        'paths': rel_paths,
        'message': message,
    }), 201


@app.route('/api/agent/git/proposals', methods=['GET'])
def api_agent_git_list_proposals():
    """List git proposals for current agent (or all agents when all_agents=1)."""
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response

    status = request.args.get('status', '').strip().lower()
    include_all_agents = request.args.get('all_agents', '0') == '1'
    limit = int(request.args.get('limit', 50) or 50)

    conn = get_connection()
    try:
        query = (
            "SELECT proposal_id, agent, title, description, status, queue_id, created_at, updated_at "
            "FROM work_proposals WHERE (lower(title) LIKE 'git %' OR lower(description) LIKE '%git panel:%')"
        )
        params = []
        if status:
            query += ' AND lower(status)=?'
            params.append(status)
        if not include_all_agents:
            query += ' AND lower(agent)=?'
            params.append(agent_id.lower())
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        rows = conn.execute(query, tuple(params)).fetchall()
        return jsonify({'ok': True, 'agent_id': agent_id, 'proposals': [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route('/api/agent/git/proposals/<proposal_id>/execute', methods=['POST'])
def api_agent_git_execute_proposal(proposal_id):
    """Execute an approved git proposal created by the same agent."""
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response

    try:
        if not agent_has_capability(agent_id, 'git_execute'):
            return jsonify({'ok': False, 'error': f'agent {agent_id} lacks git_execute capability'}), 403
    except Exception:
        pass

    conn = get_connection()
    row = conn.execute(
        'SELECT proposal_id, agent, title, description, status FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': f'proposal not found: {proposal_id}'}), 404

    if str(row['agent'] or '').lower() != agent_id.lower():
        return jsonify({'ok': False, 'error': 'agent can only execute its own proposals'}), 403

    gate = _alm_gate_or_response({'proposal_id': proposal_id}, 'agent_git_execute')
    if gate:
        return gate

    operation = _parse_git_operation_from_proposal(row['title'], row['description'])
    if not operation:
        return jsonify({'ok': False, 'error': 'unable to parse git operation from proposal'}), 400

    try:
        result = _execute_git_operation(operation, proposal_id=proposal_id)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if str(row['status'] or '').lower() != 'executed':
        update_proposal_status(proposal_id, 'executed')

    log_activity('terminal', 'agent_git_proposal_executed', f'agent={agent_id} proposal_id={proposal_id}')
    return jsonify({'ok': True, 'proposal_id': proposal_id, 'operation': operation, 'result': result})


@app.route('/api/agent/capabilities', methods=['GET'])
def api_agent_capabilities():
    """
    Tell an agent what capabilities it has been granted.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    Returns: {ok, agent_id, capabilities: [{capability, desc, granted}]}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    try:
        from database import get_agent_capabilities, AGENT_CAPABILITY_REGISTRY
        caps = get_agent_capabilities(agent_id)
        
        # Enrich with descriptions
        enriched = []
        for cap in caps:
            meta = AGENT_CAPABILITY_REGISTRY.get(cap['capability'], {})
            enriched.append({
                'capability': cap['capability'],
                'description': meta.get('desc', ''),
                'trust_level': cap['trust_level'],
                'granted': bool(cap['granted']),
                'granted_by': cap['granted_by'],
                'granted_at': cap['granted_at'],
            })
        
        return jsonify({'ok': True, 'agent_id': agent_id, 'capabilities': enriched})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/agent/think', methods=['POST'])
def api_agent_push_think():
    """
    Agent pushes a self-proposed work item via API (alternative to THINK.md file).
    Fridays orchestrator processes these on the next heartbeat.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    JSON: {title, description, priority}
    Returns: {ok, proposal_id, queue_id}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    # Check agent has propose_work capability
    try:
        from database import agent_has_capability
        if not agent_has_capability(agent_id, 'propose_work'):
            return jsonify({'ok': False, 'error': f'agent {agent_id} does not have propose_work capability'}), 403
    except Exception:
        pass  # If DB check fails, still allow (graceful degradation)
    
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)
    
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400
    
    queue_id, proposal_id = intake_internal(agent_id, title, description, priority=priority)
    log_activity('terminal', 'agent_self_proposed', f'agent={agent_id} proposal_id={proposal_id}')
    
    return jsonify({
        'ok': True,
        'proposal_id': proposal_id,
        'queue_id': queue_id,
        'via': 'think_api'
    }), 201


@app.route('/api/agent/identity', methods=['GET'])
def api_agent_identity():
    """
    Return an agent's identity card from its sandpit WHO_AM_I.md.
    Agents call this on startup to remember who they are.
    
    Requires: X-Agent-Key, X-Agent-Id headers
    Returns: {ok, agent_id, identity_md, capabilities_count, sandpit_path}
    """
    agent_id, error_response = _validate_agent_request()
    if error_response:
        return error_response
    
    sandpit = Path('/home/seven/swarm/sandpits') / agent_id
    identity_file = sandpit / 'WHO_AM_I.md'
    
    identity_md = identity_file.read_text() if identity_file.exists() else None
    
    try:
        from database import get_agent_capabilities
        caps = [c for c in get_agent_capabilities(agent_id) if c.get('granted')]
        caps_count = len(caps)
        cap_names = [c['capability'] for c in caps]
    except Exception:
        caps_count = 0
        cap_names = []
    
    return jsonify({
        'ok': True,
        'agent_id': agent_id,
        'identity_md': identity_md,
        'capabilities_count': caps_count,
        'capabilities': cap_names,
        'sandpit_path': str(sandpit),
        'shared_path': '/home/seven/swarm/sandpits/shared',
    })


@app.route('/')
def index():
    """Render themed terminal. Theme engine handles CSS injection."""
    html = get_themed_html()
    return Response(html, mimetype='text/html')



@app.route('/api/conversations')
def api_conversations():
    return jsonify(_recent_conversations())


@app.route('/api/system/time')
def api_system_time():
    """Return current system time in multiple formats for UI clock"""
    return jsonify({
        'timestamp': get_timestamp(),           # "2026-03-26 14:45:33"
        'iso': get_timestamp_iso(),             # ISO 8601 with timezone
        'full_string': get_full_time_string(),  # "Wed, March 26 • 2:45:33 PM UTC"
        'unix': int(__import__('time').time())  # Unix timestamp for JS
    })


@app.route('/api/system')
def api_system():
    """Return full system status for System tab"""
    return jsonify(get_system_status())


@app.route('/api/conversations/<int:conv_id>/messages')
def api_conversation_messages(conv_id):
    conn = get_connection()
    # Conversation metadata
    conv = conn.execute(
        "SELECT id, title, source, created_at FROM conversations WHERE id=?",
        (conv_id,)
    ).fetchone()
    if not conv:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    # All messages for this conversation, ordered chronologically
    rows = conn.execute(
        """SELECT id, from_agent AS sender, content, to_agent, message_type, tokens_used, created_at
           FROM messages WHERE conversation_id=? ORDER BY id ASC""",
        (conv_id,)
    ).fetchall()
    conn.close()
    return jsonify({
        'conv': dict(conv),
        'messages': [dict(r) for r in rows]
    })


@app.route('/api/conversations/<int:conv_id>/messages/<int:msg_id>', methods=['PATCH'])
def api_conversation_message_patch(conv_id, msg_id):
    """Edit a single user-authored prompt message inside a conversation."""
    data = request.get_json() or {}
    new_content = str(data.get('content') or '').strip()
    if not new_content:
        return jsonify({'ok': False, 'error': 'content required'}), 400

    conn = get_connection()
    row = conn.execute(
        "SELECT id, from_agent FROM messages WHERE id=? AND conversation_id=?",
        (msg_id, conv_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'message not found'}), 404

    if str(row['from_agent'] or '').strip().lower() != 'user':
        conn.close()
        return jsonify({'ok': False, 'error': 'only user prompts are editable'}), 403

    conn.execute(
        "UPDATE messages SET content=? WHERE id=? AND conversation_id=?",
        (new_content, msg_id, conv_id)
    )
    conn.commit()
    updated = conn.execute(
        "SELECT id, from_agent AS sender, content, to_agent, message_type, created_at FROM messages WHERE id=?",
        (msg_id,)
    ).fetchone()
    conn.close()

    log_activity('terminal', 'conversation_message_updated', f'conv_id={conv_id} msg_id={msg_id}')
    return jsonify({'ok': True, 'message': dict(updated) if updated else None})


@app.route('/api/conversations/<int:conv_id>/messages/<int:msg_id>', methods=['DELETE'])
def api_conversation_message_delete(conv_id, msg_id):
    """Delete a single message inside a conversation."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, from_agent, to_agent FROM messages WHERE id=? AND conversation_id=?",
        (msg_id, conv_id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'message not found'}), 404

    conn.execute("DELETE FROM messages WHERE id=? AND conversation_id=?", (msg_id, conv_id))
    conn.commit()
    conn.close()

    log_activity('terminal', 'conversation_message_deleted', f'conv_id={conv_id} msg_id={msg_id}')
    return jsonify({'ok': True, 'deleted': msg_id})


@app.route('/api/conversations/<int:conv_id>', methods=['PATCH'])
def api_conversation_patch(conv_id):
    """Update editable conversation fields (currently: title)."""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'ok': False, 'error': 'title required'}), 400

    conn = get_connection()
    row = conn.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'conversation not found'}), 404

    conn.execute("UPDATE conversations SET title=? WHERE id=?", (title[:200], conv_id))
    conn.commit()
    updated = conn.execute(
        "SELECT id, title, source, created_at FROM conversations WHERE id=?",
        (conv_id,)
    ).fetchone()
    conn.close()

    log_activity('terminal', 'conversation_updated', f'conv_id={conv_id}')
    return jsonify({'ok': True, 'conversation': dict(updated)})


@app.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
def api_conversation_delete(conv_id):
    """Delete a conversation and all linked messages."""
    conn = get_connection()
    row = conn.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'conversation not found'}), 404

    conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
    conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
    conn.commit()
    conn.close()

    log_activity('terminal', 'conversation_deleted', f'conv_id={conv_id}')
    return jsonify({'ok': True, 'deleted': conv_id})


@app.route('/api/tickets')
def api_tickets():
    status = request.args.get('status')
    return jsonify(_tickets(status=status))


@app.route('/api/tickets/<ticket_number>')
def api_ticket_detail(ticket_number):
    conn = get_connection()

    ticket = conn.execute(
        """SELECT ticket_number, status, duck_result, gemma_routing, question,
                  tags, sender_email, created_at, closed_at, final_answer,
                  sniffles_result, sniffles_checked, duck_visited
           FROM tickets WHERE ticket_number=?""",
        (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    # Pull messages via conversation id (TICKET-N → N)
    messages = []
    try:
        conv_id = int(ticket_number.split('-')[-1])
        rows = conn.execute(
            """SELECT from_agent AS sender, content, to_agent, message_type, created_at
               FROM messages WHERE conversation_id=? ORDER BY id ASC""",
            (conv_id,)
        ).fetchall()
        messages = [dict(r) for r in rows]
    except Exception:
        pass

    # Duck log entry for this ticket
    duck = conn.execute(
        """SELECT question, answer, result, reason, created_at
           FROM duck_log WHERE ticket_number=? ORDER BY id DESC LIMIT 1""",
        (ticket_number,)
    ).fetchone()

    # Ticket notes (ghost notes + agent notes)
    try:
        ticket_row = conn.execute(
            "SELECT id FROM tickets WHERE ticket_number=?", (ticket_number,)
        ).fetchone()
        notes = [dict(r) for r in conn.execute(
            "SELECT id, agent, note_type, content, created_at FROM ticket_notes "
            "WHERE ticket_id=? ORDER BY id ASC",
            (ticket_row['id'],)
        ).fetchall()] if ticket_row else []
    except Exception:
        notes = []

    # Active snoozes for this ticket
    try:
        snoozes = [dict(r) for r in conn.execute(
            "SELECT id, wake_at, note, created_at, fired FROM snoozed_tickets "
            "WHERE ticket_number=? ORDER BY wake_at ASC",
            (ticket_number,)
        ).fetchall()]
    except Exception:
        snoozes = []

    conn.close()
    return jsonify({
        'ticket':   dict(ticket),
        'messages': messages,
        'duck':     dict(duck) if duck else None,
        'notes':    notes,
        'snoozes':  snoozes,
    })


@app.route('/api/memory')
def api_memory():
    q     = request.args.get('q', '')
    mn    = int(request.args.get('min', 3))
    agent = request.args.get('agent', '')
    limit = max(1, min(int(request.args.get('limit', 120) or 120), 500))
    include_local = request.args.get('include_local', '1') != '0'
    
    rows = _memory_search(q, mn, agent, limit=limit)
    if include_local:
        local_rows = _collect_local_file_memories(query=q, agent=agent, limit=limit)
        rows = list(rows) + local_rows
        rows.sort(key=lambda r: (r.get('created_at') or ''), reverse=True)
        rows = rows[:limit]
    
    # Group results by agent for frontend
    grouped = {}
    for row in rows:
        agent_name = row.get('agent', 'unknown')
        if agent_name not in grouped:
            grouped[agent_name] = []
        grouped[agent_name].append(row)
    
    return jsonify({'results': grouped, 'limit': limit})


@app.route('/api/studio')
def api_studio():
    """Studio cockpit data — agents, queue, config status."""
    status = get_system_status()
    conn = get_connection()
    
    # Get queue length
    queue_info = conn.execute('SELECT COUNT(*) as count FROM queue').fetchone()
    conn.close()
    
    return jsonify({
        'queue_length': queue_info['count'] if queue_info else 0,
        'system_load': status.get('cpu_percent', 0),
        'memory_usage': status.get('ram_percent', 0),
        'active_model': status.get('active_model', 'none'),
    })


@app.route('/api/memory/<int:row_id>', methods=['DELETE'])
def delete_memory(row_id):
    _ALLOWED_TABLES = {'memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight',
                        'memory_nine', 'memory_ten', 'memory_grok', 'memory_twelve'}
    table = request.args.get('table', 'memory')
    if table not in _ALLOWED_TABLES:
        return jsonify({'error': 'invalid table'}), 400
    conn = get_connection()
    try:
        conn.execute(f'DELETE FROM {table} WHERE id=?', (row_id,))
        conn.commit()
    finally:
        conn.close()
    print(f'[Terminal] Deleted memory row {row_id} from {table}')
    return jsonify({'deleted': row_id, 'table': table})


@app.route('/api/memory/<int:row_id>', methods=['PATCH'])
def update_memory(row_id):
    _ALLOWED_TABLES = {
        'memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight',
        'memory_nine', 'memory_ten', 'memory_grok', 'memory_twelve'
    }
    data = request.get_json() or {}
    table = (data.get('table') or request.args.get('table') or 'memory').strip()
    if table not in _ALLOWED_TABLES:
        return jsonify({'error': 'invalid table'}), 400

    conn = get_connection()
    try:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
        if not row:
            return jsonify({'error': 'memory row not found'}), 404

        updates = []
        params = []

        if 'subject' in data and 'subject' in cols:
            updates.append('subject=?')
            params.append(str(data.get('subject') or '').strip()[:300])

        if 'content' in data and 'content' in cols:
            updates.append('content=?')
            params.append(str(data.get('content') or ''))

        append_text = str(data.get('append') or '').strip()
        if append_text and 'content' in cols:
            current = str(row['content'] or '')
            merged = current + ('\n\n' if current else '') + append_text
            updates.append('content=?')
            params.append(merged)

        if 'tags' in data and 'tags' in cols:
            updates.append('tags=?')
            params.append(str(data.get('tags') or '').strip()[:400])

        if 'importance' in data and 'importance' in cols:
            try:
                imp = int(data.get('importance'))
            except Exception:
                return jsonify({'error': 'importance must be an integer'}), 400
            if imp < 1 or imp > 10:
                return jsonify({'error': 'importance must be 1-10'}), 400
            updates.append('importance=?')
            params.append(imp)

        if not updates:
            return jsonify({'error': 'no updatable fields provided'}), 400

        if 'updated_at' in cols:
            updates.append('updated_at=?')
            params.append(datetime.now(timezone.utc).isoformat())

        params.append(row_id)
        conn.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE id=?", tuple(params))
        conn.commit()
        updated = conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    finally:
        conn.close()

    return jsonify({'ok': True, 'table': table, 'entry': dict(updated) if updated else None})


@app.route('/api/memory/<int:row_id>/attach', methods=['POST'])
def attach_memory(row_id):
    data = request.get_json() or {}
    label = (data.get('label') or '').strip()
    value = (data.get('value') or '').strip()
    table = (data.get('table') or request.args.get('table') or 'memory').strip()
    allowed = {
        'memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight',
        'memory_nine', 'memory_ten', 'memory_grok', 'memory_twelve'
    }
    if table not in allowed:
        return jsonify({'error': 'invalid table'}), 400
    if not label or not value:
        return jsonify({'error': 'label and value required'}), 400

    attachment = f"[attachment:{label}] {value}"
    conn = get_connection()
    try:
        row = conn.execute(f"SELECT id, content FROM {table} WHERE id=?", (row_id,)).fetchone()
        if not row:
            return jsonify({'error': 'memory row not found'}), 404
        merged = (str(row['content'] or '') + ('\n\n' if row['content'] else '') + attachment)
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if 'updated_at' in cols:
            conn.execute(
                f"UPDATE {table} SET content=?, updated_at=? WHERE id=?",
                (merged, datetime.now(timezone.utc).isoformat(), row_id),
            )
        else:
            conn.execute(f"UPDATE {table} SET content=? WHERE id=?", (merged, row_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True, 'table': table, 'id': row_id})


@app.route('/api/memory/<int:row_id>/assign', methods=['POST'])
def assign_memory(row_id):
    data = request.get_json() or {}
    from_table = (data.get('table') or request.args.get('table') or 'memory').strip()
    targets = data.get('targets') or []
    if isinstance(targets, str):
        targets = [x.strip() for x in targets.split(',') if x.strip()]
    targets = [str(t).strip().lower() for t in targets if str(t).strip()]
    if not targets:
        return jsonify({'error': 'targets required'}), 400

    allowed = {
        'memory', 'memory_llama', 'memory_qwen', 'memory_gemma', 'memory_eight',
        'memory_nine', 'memory_ten', 'memory_grok', 'memory_twelve'
    }
    if from_table not in allowed:
        return jsonify({'error': 'invalid source table'}), 400

    conn = get_connection()
    try:
        src = conn.execute(f"SELECT * FROM {from_table} WHERE id=?", (row_id,)).fetchone()
        if not src:
            return jsonify({'error': 'memory row not found'}), 404

        assigned = []
        skipped = []
        for agent_name in targets:
            tgt_table = _AGENT_TABLES.get(agent_name)
            if not tgt_table or tgt_table not in allowed:
                skipped.append({'agent': agent_name, 'reason': 'unknown target'})
                continue

            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tgt_table})").fetchall()}
            now_iso = datetime.now(timezone.utc).isoformat()
            field_values = {}

            if 'agent' in cols:
                field_values['agent'] = agent_name
            if 'subject' in cols:
                src_subject = str(src['subject'] or '').strip() if 'subject' in src.keys() else ''
                field_values['subject'] = src_subject or str(src['content'] or '')[:120]
            if 'content' in cols:
                note = str(data.get('note') or '').strip()
                body = str(src['content'] or '')
                field_values['content'] = (body + (f"\n\n[assigned-note] {note}" if note else ''))
            if 'tags' in cols:
                base_tags = str(src['tags'] or '').strip() if 'tags' in src.keys() else ''
                merged_tags = ','.join([x for x in [base_tags, 'assigned'] if x])
                field_values['tags'] = merged_tags[:400]
            if 'importance' in cols:
                try:
                    imp = int(src['importance'] or 5)
                except Exception:
                    imp = 5
                field_values['importance'] = max(1, min(10, imp))
            if 'source' in cols:
                field_values['source'] = f'assigned_from:{from_table}:{row_id}'
            if 'type' in cols:
                field_values['type'] = 'assigned'
            if 'archived' in cols:
                field_values['archived'] = 0
            if 'created_at' in cols:
                field_values['created_at'] = now_iso
            if 'updated_at' in cols:
                field_values['updated_at'] = now_iso

            keys = list(field_values.keys())
            placeholders = ','.join(['?'] * len(keys))
            conn.execute(
                f"INSERT INTO {tgt_table} ({', '.join(keys)}) VALUES ({placeholders})",
                tuple(field_values[k] for k in keys),
            )
            assigned.append({'agent': agent_name, 'table': tgt_table})

        conn.commit()
    finally:
        conn.close()

    return jsonify({'ok': True, 'assigned': assigned, 'skipped': skipped, 'source': {'table': from_table, 'id': row_id}})


@app.route('/api/tickets/<ticket_number>', methods=['PATCH'])
def api_ticket_patch(ticket_number):
    """Update editable ticket fields: tags, priority."""
    data = request.get_json() or {}
    allowed = {}
    if 'tags' in data:
        allowed['tags'] = str(data['tags'])[:200]
    if 'priority' in data:
        try:
            p = int(data['priority'])
            allowed['priority'] = max(1, min(10, p))
        except (ValueError, TypeError):
            return jsonify({'error': 'priority must be 1-10'}), 400
    if not allowed:
        return jsonify({'error': 'no editable fields provided'}), 400

    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id FROM tickets WHERE ticket_number=?', (ticket_number,)
        ).fetchone()
        if not row:
            return jsonify({'error': 'not found'}), 404
        # tags live in tickets; priority lives in queue (linked via queue_id)
        if 'tags' in allowed:
            conn.execute(
                'UPDATE tickets SET tags=? WHERE ticket_number=?',
                (allowed['tags'], ticket_number)
            )
        if 'priority' in allowed:
            conn.execute(
                '''UPDATE queue SET priority=?
                   WHERE id=(SELECT queue_id FROM tickets WHERE ticket_number=?)''',
                (allowed['priority'], ticket_number)
            )
        conn.commit()
    finally:
        conn.close()
    log_activity('terminal', 'ticket_patched', f'{ticket_number} | {allowed}')
    return jsonify({'ok': True, 'updated': allowed})


@app.route('/api/tickets/<ticket_number>/notes', methods=['POST'])
def add_ticket_note_endpoint(ticket_number):
    from database import add_ticket_note_by_number
    data    = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'empty note'}), 400
    ok = add_ticket_note_by_number(ticket_number, 'ghost@dashboard', content, note_type='ghost_note')
    if not ok:
        return jsonify({'error': 'ticket not found'}), 404
    log_activity('terminal', 'note_added', f'{ticket_number} | {content[:80]}')
    return jsonify({'ok': True})


@app.route('/api/tickets/<ticket_number>/notes/<int:note_id>', methods=['DELETE'])
def delete_ticket_note_endpoint(ticket_number, note_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM ticket_notes WHERE id=?', (note_id,))
        conn.commit()
    finally:
        conn.close()
    log_activity('terminal', 'note_deleted', f'{ticket_number} | note_id={note_id}')
    return jsonify({'ok': True})


# ── Project Docs ────────────────────────────────────────────────────────────────

def _ensure_project_doc_versions_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_doc_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER,
            doc_name TEXT,
            content TEXT,
            tags TEXT,
            version_number INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            source TEXT DEFAULT 'terminal_ui'
        )
        """
    )


def _next_project_doc_version(conn, doc_id):
    row = conn.execute(
        'SELECT COALESCE(MAX(version_number), 0) AS v FROM project_doc_versions WHERE doc_id=?',
        (doc_id,)
    ).fetchone()
    return int((row['v'] if row else 0) or 0) + 1


def _record_project_doc_version(conn, doc_id, doc_name, content, tags, action, source='terminal_ui'):
    _ensure_project_doc_versions_schema(conn)
    version = _next_project_doc_version(conn, doc_id)
    conn.execute(
        """
        INSERT INTO project_doc_versions
        (doc_id, doc_name, content, tags, version_number, action, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (doc_id, doc_name, content, tags, version, action, source)
    )
    return version

@app.route('/api/kb')
def api_kb_list():
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    rows = conn.execute(
        """
        SELECT d.id,
               d.doc_name,
               d.tags,
               d.updated_at,
               LENGTH(COALESCE(d.content, '')) AS content_length,
               COALESCE(v.version_count, 0) AS version_count
        FROM project_docs d
        LEFT JOIN (
            SELECT doc_id, COUNT(*) AS version_count
            FROM project_doc_versions
            GROUP BY doc_id
        ) v ON v.doc_id = d.id
        ORDER BY d.updated_at DESC
        """
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/kb/<int:doc_id>')
def api_kb_get(doc_id):
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    row = conn.execute('SELECT * FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


@app.route('/api/kb/<int:doc_id>/versions')
def api_kb_versions(doc_id):
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    exists = conn.execute('SELECT id FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    versions = conn.execute(
        """
        SELECT id, doc_id, doc_name, tags, version_number, action, created_at, source,
               LENGTH(COALESCE(content, '')) AS content_length
        FROM project_doc_versions
        WHERE doc_id=?
        ORDER BY version_number DESC, id DESC
        """,
        (doc_id,)
    ).fetchall()
    conn.close()

    if not exists and not versions:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True, 'versions': [dict(v) for v in versions]})


@app.route('/api/kb/<int:doc_id>/restore', methods=['POST'])
def api_kb_restore(doc_id):
    data = request.get_json() or {}
    version_id = data.get('version_id')
    if version_id is None:
        return jsonify({'ok': False, 'error': 'version_id required'}), 400

    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    version = conn.execute(
        'SELECT * FROM project_doc_versions WHERE id=? AND doc_id=?',
        (int(version_id), doc_id)
    ).fetchone()
    if not version:
        conn.close()
        return jsonify({'ok': False, 'error': 'version not found'}), 404

    row = conn.execute('SELECT id FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE project_docs SET doc_name=?, content=?, tags=?, updated_at=datetime('now') WHERE id=?",
            (version['doc_name'], version['content'], version['tags'], doc_id)
        )
    else:
        conn.execute(
            "INSERT INTO project_docs (id, doc_name, content, tags, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (doc_id, version['doc_name'], version['content'], version['tags'])
        )

    _record_project_doc_version(
        conn,
        doc_id=doc_id,
        doc_name=version['doc_name'],
        content=version['content'],
        tags=version['tags'],
        action='restore',
        source='terminal_ui',
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/kb', methods=['POST'])
def api_kb_create():
    data     = request.get_json() or {}
    doc_name = (data.get('doc_name') or '').strip()
    content  = (data.get('content') or '').strip()
    tags     = (data.get('tags') or 'all').strip()
    if not doc_name:
        return jsonify({'error': 'doc_name required'}), 400
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    cur = conn.execute(
        "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
        (doc_name, content, tags)
    )
    new_id = cur.lastrowid
    _record_project_doc_version(
        conn,
        doc_id=new_id,
        doc_name=doc_name,
        content=content,
        tags=tags,
        action='create',
        source='terminal_ui',
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'id': new_id})


@app.route('/api/kb/<int:doc_id>', methods=['PUT'])
def api_kb_update(doc_id):
    data     = request.get_json() or {}
    doc_name = (data.get('doc_name') or '').strip()
    content  = (data.get('content') or '').strip()
    tags     = (data.get('tags') or 'all').strip()
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    existing = conn.execute('SELECT id FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404
    conn.execute(
        "UPDATE project_docs SET doc_name=?, content=?, tags=?, updated_at=datetime('now') WHERE id=?",
        (doc_name, content, tags, doc_id)
    )
    _record_project_doc_version(
        conn,
        doc_id=doc_id,
        doc_name=doc_name,
        content=content,
        tags=tags,
        action='update',
        source='terminal_ui',
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/kb/<int:doc_id>', methods=['DELETE'])
def api_kb_delete(doc_id):
    conn = get_connection()
    _ensure_project_doc_versions_schema(conn)
    row = conn.execute('SELECT id, doc_name, content, tags FROM project_docs WHERE id=?', (doc_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404

    _record_project_doc_version(
        conn,
        doc_id=row['id'],
        doc_name=row['doc_name'],
        content=row['content'],
        tags=row['tags'],
        action='delete',
        source='terminal_ui',
    )
    conn.execute('DELETE FROM project_docs WHERE id=?', (doc_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/proposals')
def api_proposals_list():
    """List all pending agent proposals with preview."""
    from sandpits import list_proposals, read_proposal
    proposals = list_proposals()
    result = []
    for p in proposals:
        content = read_proposal(p['filename']) or ''
        result.append({**p, 'preview': content[:600]})
    return jsonify({'proposals': result})


@app.route('/api/proposals/approve', methods=['POST'])
def api_proposals_approve():
    """
    Approve a proposal:
    - Import it as a KB doc
    - Write approval to agent's memory
    - Delete the proposal file
    """
    from sandpits import read_proposal, delete_proposal
    data     = request.get_json() or {}
    filename = (data.get('filename') or '').strip()
    agent    = (data.get('agent') or '').strip()

    if not filename:
        return jsonify({'error': 'filename required'}), 400

    content = read_proposal(filename)
    if content is None:
        return jsonify({'error': 'proposal not found'}), 404

    # Import as KB doc
    conn = get_connection()
    doc_name = f'Proposal: {filename.replace(".md", "")}'
    existing = conn.execute("SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)).fetchone()
    if existing:
        conn.execute("UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                     (content, agent, existing[0]))
    else:
        conn.execute("INSERT INTO project_docs (doc_name, content, tags) VALUES (?, ?, ?)",
                     (doc_name, content, agent))

    # Write approval note to agent's memory using unified helper
    from database import save_agent_memory
    save_agent_memory(
        agent_name=agent,
        subject='Proposal Approved',
        content=f'My proposal "{filename}" was approved by Ghost and added to the KB.',
        importance=7,
        source='proposal_approved'
    )

    conn.commit()
    conn.close()

    # Delete the proposal file
    delete_proposal(filename)

    from database import log_activity
    log_activity('terminal', 'proposal_approved', filename)

    return jsonify({'ok': True})


@app.route('/api/proposals/reject', methods=['POST'])
def api_proposals_reject():
    """
    Reject a proposal:
    - Optionally write feedback to agent's sandpit
    - Delete the proposal file
    """
    from sandpits import delete_proposal, write_file
    from database import log_activity
    data     = request.get_json() or {}
    filename = (data.get('filename') or '').strip()
    agent    = (data.get('agent') or '').strip()
    feedback = (data.get('feedback') or '').strip()

    if not filename:
        return jsonify({'error': 'filename required'}), 400

    # Write feedback to agent's sandpit if provided
    if feedback and agent:
        try:
            from datetime import datetime
            fb_filename = f'rejection_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            write_file(agent, fb_filename,
                       f'Proposal rejected: {filename}\n\nGhost feedback:\n{feedback}')
        except Exception:
            pass

    delete_proposal(filename)
    log_activity('terminal', 'proposal_rejected', filename)

    return jsonify({'ok': True})


@app.route('/api/queue', methods=['GET'])
def api_queue_list():
    """List queue entries, optionally filtered by source_type and status."""
    source_type = (request.args.get('source_type') or '').strip() or None
    status = (request.args.get('status') or '').strip() or None
    try:
        limit = int(request.args.get('limit', 50))
    except Exception:
        limit = 50

    rows = get_queue_entries(source_type=source_type, status=status, limit=max(1, min(limit, 500)))
    return jsonify({'ok': True, 'queue': rows, 'count': len(rows)})


@app.route('/api/queue', methods=['POST'])
def api_queue_create_internal():
    """Create an internal queue entry and matching work proposal."""
    data = request.get_json() or {}
    agent = (data.get('agent') or '').strip().lower()
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    priority = int(data.get('priority', 5) or 5)

    if not agent or not title:
        return jsonify({'ok': False, 'error': 'agent and title required'}), 400

    queue_id, proposal_id = intake_internal(agent, title, description, priority=priority)
    log_activity('terminal', 'queue_internal_created', f'{proposal_id} ({agent})')
    return jsonify({'ok': True, 'queue_id': queue_id, 'proposal_id': proposal_id}), 201


@app.route('/api/queue/<int:queue_id>', methods=['GET'])
def api_queue_get(queue_id):
    """Return one queue entry and linked proposal if present."""
    conn = get_connection()
    row = conn.execute('SELECT * FROM queue WHERE id=?', (queue_id,)).fetchone()
    proposal = conn.execute(
        'SELECT proposal_id, agent, title, status, queue_id, created_at, updated_at '
        'FROM work_proposals WHERE queue_id=?',
        (queue_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'queue entry not found'}), 404

    return jsonify({
        'ok': True,
        'queue': dict(row),
        'proposal': dict(proposal) if proposal else None
    })


@app.route('/api/queue/<int:queue_id>', methods=['PATCH'])
def api_queue_patch(queue_id):
    """Patch queue status and priority for manual workflow control."""
    data = request.get_json() or {}
    status = (data.get('status') or '').strip()
    priority = data.get('priority', None)

    updates = []
    params = []
    if status:
        updates.append('status=?')
        params.append(status)
    if priority is not None:
        updates.append('priority=?')
        params.append(int(priority))

    if not updates:
        return jsonify({'ok': False, 'error': 'no fields to update'}), 400

    params.append(queue_id)
    conn = get_connection()
    conn.execute(f"UPDATE queue SET {', '.join(updates)} WHERE id=?", tuple(params))
    conn.commit()
    row = conn.execute('SELECT * FROM queue WHERE id=?', (queue_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'queue entry not found'}), 404

    log_activity('terminal', 'queue_updated', f'queue_id={queue_id}')
    return jsonify({'ok': True, 'queue': dict(row)})


@app.route('/api/work-proposals', methods=['GET'])
def api_work_proposals_list():
    """List work proposals from DB with optional status/agent filters."""
    statuses = request.args.getlist('status')
    statuses = [s.strip() for s in statuses if s.strip()]
    agent = (request.args.get('agent') or '').strip()
    try:
        limit = int(request.args.get('limit', 100))
    except Exception:
        limit = 100

    clauses = []
    params = []
    if statuses:
        placeholders = ','.join(['?' for _ in statuses])
        clauses.append(f'status IN ({placeholders})')
        params.extend(statuses)
    if agent:
        clauses.append('agent=?')
        params.append(agent)

    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    conn = get_connection()
    rows = conn.execute(
        f"SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at "
        f"FROM work_proposals {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [max(1, min(limit, 500))])
    ).fetchall()
    conn.close()

    payload = [dict(r) for r in rows]
    return jsonify({'ok': True, 'proposals': payload, 'count': len(payload)})


@app.route('/api/work-proposals/<proposal_id>', methods=['PATCH'])
def api_work_proposals_patch(proposal_id):
    """Update proposal status for approval/execution workflows."""
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    status = (data.get('status') or '').strip().lower()
    ticket_number = (data.get('ticket_number') or '').strip()
    ticket_id     = data.get('ticket_id')
    valid = {'pending', 'approved', 'rejected', 'in_progress', 'done', 'executed'}

    if status not in valid:
        return jsonify({'ok': False, 'error': f'invalid status: {status}'}), 400

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    ghost_layer_users = {'ghost', 'nine', 'ten', 'eleven', 'twelve', 'duck', 'sniffles'}
    proposal_agent = str(row['agent'] or '').strip().lower()
    effective_user = identity['effective_user']

    if proposal_agent not in ghost_layer_users and status in {'in_progress', 'done', 'executed'}:
        if effective_user not in ghost_layer_users:
            return jsonify({
                'ok': False,
                'error': 'non-ghost proposals must be implemented by a ghost-layer user',
                'proposal_id': proposal_id,
                'proposal_agent': proposal_agent,
                'effective_user': effective_user,
            }), 403

    current_status = (row['status'] or '').lower()
    allowed_transitions = {
        'pending':     {'pending', 'approved', 'rejected'},
        'approved':    {'approved', 'in_progress', 'executed', 'rejected'},
        'in_progress': {'in_progress', 'done', 'rejected'},
        'done':        {'done', 'executed', 'in_progress'},
        'executed':    {'executed'},
        'rejected':    {'rejected'},
    }
    if status not in allowed_transitions.get(current_status, {current_status}):
        _safe_time_event(
            agent=row['agent'] or 'terminal_ui',
            action='proposal_transition_blocked',
            event_type='proposal_guard',
            target=proposal_id,
            details={'from_status': current_status, 'to_status': status}
        )
        return jsonify({
            'ok': False,
            'error': f'invalid transition: {current_status} -> {status}',
            'proposal_id': proposal_id,
        }), 403

    duck_review = None
    if status == 'approved':
        duck_review = _run_proposal_duck_review(row)
        _log_proposal_duck_review(
            proposal_id,
            row['title'] or proposal_id,
            row['description'] or '',
            duck_review['result'],
            duck_review['reason']
        )
        if duck_review['result'] != 'YES':
            log_activity('terminal', 'proposal_duck_review_blocked', f'{proposal_id} -> {duck_review["reason"]}')
            _safe_time_event(
                agent=row['agent'] or 'terminal_ui',
                action='proposal_duck_review_blocked',
                event_type='proposal_review',
                target=proposal_id,
                details=duck_review
            )
            return jsonify({
                'ok': False,
                'error': 'duck review blocked approval',
                'proposal_id': proposal_id,
                'duck_review': duck_review,
            }), 403

    update_proposal_status(proposal_id, status, ticket_number=ticket_number)
    if ticket_id is not None:
        conn = get_connection()
        conn.execute('UPDATE work_proposals SET ticket_id=?, updated_at=datetime("now") WHERE proposal_id=?',
                     (ticket_id, proposal_id))
        conn.commit()
        conn.close()

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, proposal_file, ticket_number, queue_id, ticket_id, created_at, updated_at '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    log_activity('terminal', 'proposal_status_updated', f'{proposal_id} -> {status} by {effective_user}')
    _safe_time_event(
        agent=row['agent'] or 'terminal_ui',
        action='proposal_status_updated',
        event_type='proposal',
        target=proposal_id,
        details={'from_status': current_status, 'to_status': status, 'queue_id': row['queue_id'], 'duck_review': duck_review}
    )
    if status in ('approved', 'executed', 'rejected'):
        _safe_workflow_checkpoint(
            label=f'{proposal_id}-{status}',
            agent=row['agent'] or 'terminal_ui',
            description=f'Automatic Vortex checkpoint after {proposal_id} moved to {status}'
        )

    # Notify the originating agent via memory so it can act on the outcome
    agent_name = (row['agent'] or '').lower().strip()
    _NOTIFIABLE_AGENTS = {'nine', 'gemma', 'grok', 'llama', 'eight', 'twelve'}
    if agent_name in _NOTIFIABLE_AGENTS and status in ('approved', 'rejected', 'in_progress', 'done', 'executed'):
        try:
            from database import save_agent_memory
            status_labels = {
                'approved':   'Your proposal has been approved by Ghost. Begin planning implementation.',
                'rejected':   'Your proposal was rejected by Ghost. Review and consider revising.',
                'in_progress':'Your proposal is now in progress. Proceed with implementation.',
                'done':       'Your proposal is marked done. Awaiting final execution sign-off.',
                'executed':   'Your proposal has been executed and closed.',
            }
            note = status_labels.get(status, f'Proposal status changed to {status}.')
            save_agent_memory(
                agent_name=agent_name,
                subject=f'Proposal {proposal_id} → {status}',
                content=f'{note} Proposal: "{row["title"]}". Ticket ref: {row["ticket_number"] or "none"}.',
                tags='proposal,alm,status_change',
                importance=8,
                source='alm_pipeline'
            )
        except Exception:
            pass

    payload = {'ok': True, 'proposal': dict(row)}
    if duck_review:
        payload['duck_review'] = duck_review
    return jsonify(payload)


@app.route('/api/work-proposals/<proposal_id>', methods=['DELETE'])
def api_work_proposals_delete(proposal_id):
    """Delete proposal records (Ghost-layer only)."""
    data = request.get_json(silent=True) or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    effective_user = identity['effective_user']
    ghost_layer_users = {'ghost', 'nine', 'ten', 'eleven', 'twelve', 'duck', 'sniffles'}
    if effective_user not in ghost_layer_users:
        return jsonify({
            'ok': False,
            'error': 'proposal deletion requires ghost-layer identity',
            'effective_user': effective_user,
        }), 403

    conn = get_connection()
    row = conn.execute(
        'SELECT id, proposal_id, agent, title, description, status, queue_id, ticket_number '
        'FROM work_proposals WHERE proposal_id=?',
        (proposal_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'proposal not found'}), 404

    conn.execute('DELETE FROM work_proposals WHERE proposal_id=?', (proposal_id,))
    conn.commit()
    conn.close()

    deleted = dict(row)
    log_activity('terminal', 'proposal_deleted', f"{proposal_id} by {effective_user}")
    _safe_time_event(
        agent=deleted.get('agent') or 'terminal_ui',
        action='proposal_deleted',
        event_type='proposal',
        target=proposal_id,
        details={'status': deleted.get('status'), 'effective_user': effective_user}
    )

    return jsonify({'ok': True, 'deleted': deleted})


def _git_repo_root() -> Path:
    return Path('/home/seven/swarm')


def _git_rel_path(path_value: str) -> str:
    rel_path = str(path_value or '').strip().replace('\\', '/').lstrip('/')
    if not rel_path:
        raise ValueError('path required')
    repo_root = _git_repo_root().resolve()
    full_path = (repo_root / rel_path).resolve()
    if not str(full_path).startswith(str(repo_root)):
        raise ValueError('path outside repository')
    try:
        return str(full_path.relative_to(repo_root)).replace('\\', '/')
    except Exception as exc:
        raise ValueError(f'invalid repository path: {exc}') from exc


def _run_git_command(args, timeout=20):
    import subprocess

    repo_root = _git_repo_root()
    proc = subprocess.run(
        ['git', '-C', str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc


def _build_git_operation_description(action: str, paths=None, message='') -> str:
    paths = [str(p).strip() for p in (paths or []) if str(p).strip()]
    action = str(action or '').strip().lower()
    message = str(message or '').strip()

    if action == 'stage':
        human = f"Stage repository path via Git panel: {paths[0] if paths else ''}"
    elif action == 'unstage':
        human = f"Unstage repository path via Git panel: {paths[0] if paths else ''}"
    else:
        human = f"Commit staged repository changes via Git panel: {message}"

    payload = {
        'kind': 'git_operation',
        'action': action,
        'paths': paths,
        'message': message,
    }
    return f"{human}\n\nALM Git payload:\n{json.dumps(payload, ensure_ascii=True)}"


def _parse_git_operation_from_proposal(title: str, description: str):
    title_l = str(title or '').lower()
    desc = str(description or '')

    marker = re.search(r'ALM Git payload:\s*(\{.*\})\s*$', desc, flags=re.IGNORECASE | re.DOTALL)
    if marker:
        try:
            payload = json.loads(marker.group(1))
            action = str(payload.get('action') or '').strip().lower()
            if action in ('stage', 'unstage'):
                return {
                    'action': action,
                    'paths': [str(p).strip() for p in (payload.get('paths') or []) if str(p).strip()],
                }
            if action == 'commit':
                return {'action': action, 'message': str(payload.get('message') or '').strip()}
        except Exception:
            pass

    if 'git stage file' in title_l:
        m = re.search(r'Stage repository path via Git panel:\s*(.+)$', desc, flags=re.IGNORECASE | re.MULTILINE)
        return {'action': 'stage', 'paths': [m.group(1).strip()]} if m else None
    if 'git unstage file' in title_l:
        m = re.search(r'Unstage repository path via Git panel:\s*(.+)$', desc, flags=re.IGNORECASE | re.MULTILINE)
        return {'action': 'unstage', 'paths': [m.group(1).strip()]} if m else None
    if 'git commit staged changes' in title_l:
        m = re.search(r'Commit staged repository changes via Git panel:\s*(.+)$', desc, flags=re.IGNORECASE | re.MULTILINE)
        return {'action': 'commit', 'message': m.group(1).strip()} if m else None
    return None


def _execute_git_operation(operation: dict, proposal_id=''):
    action = str((operation or {}).get('action') or '').strip().lower()
    if action not in ('stage', 'unstage', 'commit'):
        raise ValueError('unsupported git action')

    if action in ('stage', 'unstage'):
        raw_paths = operation.get('paths') or []
        rel_paths = [_git_rel_path(item) for item in raw_paths if str(item or '').strip()]
        if not rel_paths:
            raise ValueError('paths required')
        cmd = ['add', '--', *rel_paths] if action == 'stage' else ['reset', 'HEAD', '--', *rel_paths]
        proc = _run_git_command(cmd, timeout=20)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or f'git {action} failed').strip()[:500])
        return {'action': action, 'paths': rel_paths, 'count': len(rel_paths)}

    message = str(operation.get('message') or '').strip()
    if not message:
        raise ValueError('message required')

    staged = _run_git_command(['diff', '--cached', '--name-only'], timeout=20)
    if staged.returncode != 0:
        raise RuntimeError((staged.stderr or staged.stdout or 'git diff failed').strip()[:500])

    staged_paths = [line.strip() for line in (staged.stdout or '').splitlines() if line.strip()]
    if not staged_paths:
        raise ValueError('no staged changes to commit')

    final_message = message if not proposal_id else f'{message} (proposal:{proposal_id[:12]})'
    commit = _run_git_command(['commit', '-m', final_message], timeout=40)
    if commit.returncode != 0:
        raise RuntimeError((commit.stderr or commit.stdout or 'git commit failed').strip()[:500])

    rev = _run_git_command(['rev-parse', 'HEAD'], timeout=10)
    commit_hash = (rev.stdout or '').strip() if rev.returncode == 0 else ''
    return {
        'action': 'commit',
        'commit_hash': commit_hash,
        'files_changed': len(staged_paths),
        'paths': staged_paths[:200],
        'message': final_message,
    }


def _parse_git_status_porcelain(status_text: str):
    branch = ''
    upstream = ''
    ahead = 0
    behind = 0
    detached = False
    files = []

    for raw_line in (status_text or '').splitlines():
        line = raw_line.rstrip('\n')
        if not line:
            continue
        if line.startswith('## '):
            header = line[3:]
            if header.startswith('HEAD '):
                detached = True
            branch_part = header.split('...')[0].strip()
            branch = branch_part.replace('No commits yet on ', '').strip()
            if '...' in header:
                upstream = header.split('...', 1)[1].split(' [', 1)[0].strip()
            if '[' in header and ']' in header:
                details = header.split('[', 1)[1].split(']', 1)[0]
                for part in details.split(','):
                    piece = part.strip()
                    if piece.startswith('ahead '):
                        try:
                            ahead = int(piece.split(' ', 1)[1])
                        except Exception:
                            ahead = 0
                    elif piece.startswith('behind '):
                        try:
                            behind = int(piece.split(' ', 1)[1])
                        except Exception:
                            behind = 0
            continue

        if len(line) < 4:
            continue

        x = line[0]
        y = line[1]
        path_text = line[3:].strip()
        display_path = path_text.split(' -> ')[-1].strip()
        staged = x not in (' ', '?')
        unstaged = y != ' '
        untracked = x == '?' and y == '?'
        deleted = x == 'D' or y == 'D'
        renamed = x == 'R' or y == 'R' or ' -> ' in path_text
        conflicted = x == 'U' or y == 'U' or (x == 'A' and y == 'A') or (x == 'D' and y == 'D')

        if conflicted:
            status_label = 'conflict'
        elif untracked:
            status_label = 'untracked'
        elif deleted:
            status_label = 'deleted'
        elif renamed:
            status_label = 'renamed'
        elif staged and unstaged:
            status_label = 'mixed'
        elif staged:
            status_label = 'staged'
        elif unstaged:
            status_label = 'modified'
        else:
            status_label = 'unknown'

        files.append({
            'path': display_path,
            'raw_path': path_text,
            'x': x,
            'y': y,
            'staged': staged,
            'unstaged': unstaged,
            'untracked': untracked,
            'deleted': deleted,
            'renamed': renamed,
            'conflicted': conflicted,
            'status_label': status_label,
        })

    return {
        'branch': branch,
        'upstream': upstream,
        'ahead': ahead,
        'behind': behind,
        'detached': detached,
        'files': files,
    }


@app.route('/api/git/status', methods=['GET'])
def api_git_status():
    """Return repository status for the Fridays Git panel."""
    try:
        proc = _run_git_command(['status', '--porcelain=1', '--branch'], timeout=20)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git status failed').strip()[:500]}), 500

    parsed = _parse_git_status_porcelain(proc.stdout or '')
    files = parsed['files']
    return jsonify({
        'ok': True,
        'branch': parsed['branch'],
        'upstream': parsed['upstream'],
        'ahead': parsed['ahead'],
        'behind': parsed['behind'],
        'detached': parsed['detached'],
        'clean': len(files) == 0,
        'counts': {
            'changed': len(files),
            'staged': sum(1 for entry in files if entry['staged']),
            'unstaged': sum(1 for entry in files if entry['unstaged']),
            'untracked': sum(1 for entry in files if entry['untracked']),
            'conflicted': sum(1 for entry in files if entry['conflicted']),
        },
        'files': files,
    })


@app.route('/api/git/diff', methods=['GET'])
def api_git_diff():
    """Return a unified diff for a repository path."""
    path_value = request.args.get('path', '')
    staged = request.args.get('staged', '0') == '1'
    try:
        rel_path = _git_rel_path(path_value)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    args = ['diff']
    if staged:
        args.append('--cached')
    args.extend(['--', rel_path])

    try:
        proc = _run_git_command(args, timeout=20)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git diff failed').strip()[:500]}), 500

    diff_text = proc.stdout or ''
    truncated = len(diff_text) > 120000
    if truncated:
        diff_text = diff_text[:120000] + '\n[... diff truncated]'

    return jsonify({
        'ok': True,
        'path': rel_path,
        'staged': staged,
        'diff': diff_text,
        'truncated': truncated,
    })


@app.route('/api/git/stage', methods=['POST'])
def api_git_stage():
    """Stage one or more repository paths."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    raw_paths = data.get('paths') or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    try:
        rel_paths = [_git_rel_path(item) for item in raw_paths if str(item or '').strip()]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    if not rel_paths:
        return jsonify({'ok': False, 'error': 'paths required'}), 400

    try:
        proc = _run_git_command(['add', '--', *rel_paths], timeout=20)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git add failed').strip()[:500]}), 500

    log_activity('terminal', 'git_stage', ', '.join(rel_paths[:8]))
    return jsonify({'ok': True, 'paths': rel_paths, 'count': len(rel_paths)})


@app.route('/api/git/unstage', methods=['POST'])
def api_git_unstage():
    """Unstage one or more repository paths."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    raw_paths = data.get('paths') or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    try:
        rel_paths = [_git_rel_path(item) for item in raw_paths if str(item or '').strip()]
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    if not rel_paths:
        return jsonify({'ok': False, 'error': 'paths required'}), 400

    try:
        proc = _run_git_command(['reset', 'HEAD', '--', *rel_paths], timeout=20)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if proc.returncode != 0:
        return jsonify({'ok': False, 'error': (proc.stderr or proc.stdout or 'git reset failed').strip()[:500]}), 500

    log_activity('terminal', 'git_unstage', ', '.join(rel_paths[:8]))
    return jsonify({'ok': True, 'paths': rel_paths, 'count': len(rel_paths)})


@app.route('/api/git/commit', methods=['POST'])
def api_git_commit():
    """Commit staged repository changes."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    message = str(data.get('message') or '').strip()
    proposal_id = str(data.get('proposal_id') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'message required'}), 400

    try:
        staged = _run_git_command(['diff', '--cached', '--name-only'], timeout=20)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if staged.returncode != 0:
        return jsonify({'ok': False, 'error': (staged.stderr or staged.stdout or 'git diff failed').strip()[:500]}), 500

    staged_paths = [line.strip() for line in (staged.stdout or '').splitlines() if line.strip()]
    if not staged_paths:
        return jsonify({'ok': False, 'error': 'no staged changes to commit'}), 400

    final_message = message if not proposal_id else f'{message} (proposal:{proposal_id[:12]})'
    try:
        commit = _run_git_command(['commit', '-m', final_message], timeout=40)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    if commit.returncode != 0:
        return jsonify({'ok': False, 'error': (commit.stderr or commit.stdout or 'git commit failed').strip()[:500]}), 500

    rev = _run_git_command(['rev-parse', 'HEAD'], timeout=10)
    commit_hash = (rev.stdout or '').strip() if rev.returncode == 0 else ''
    log_activity('terminal', 'git_commit', commit_hash[:12] or final_message[:48])
    return jsonify({
        'ok': True,
        'commit_hash': commit_hash,
        'files_changed': len(staged_paths),
        'paths': staged_paths[:200],
        'message': final_message,
    })


@app.route('/api/deferred', methods=['GET'])
def api_deferred_list():
    """List unresolved deferred / pinned items."""
    include_resolved = request.args.get('resolved', '0') == '1'
    conn = get_connection()
    where = '' if include_resolved else 'WHERE resolved=0'
    rows = conn.execute(
        f'SELECT id, content, source, source_id, pinned_by, resolved, created_at, resolved_at '
        f'FROM deferred_items {where} ORDER BY created_at DESC LIMIT 200'
    ).fetchall()
    conn.close()
    return jsonify({'ok': True, 'items': [dict(r) for r in rows]})


@app.route('/api/deferred', methods=['POST'])
def api_deferred_create():
    """Pin a new deferred item."""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'ok': False, 'error': 'content required'}), 400
    source    = (data.get('source') or 'manual').strip()
    source_id = (data.get('source_id') or '').strip()
    pinned_by = (data.get('pinned_by') or 'ghost').strip()
    conn = get_connection()
    cur = conn.execute(
        'INSERT INTO deferred_items (content, source, source_id, pinned_by) VALUES (?,?,?,?)',
        (content, source, source_id, pinned_by)
    )
    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_activity('terminal', 'deferred_pinned', content[:80])
    return jsonify({'ok': True, 'id': item_id})


@app.route('/api/deferred/<int:item_id>', methods=['PATCH'])
def api_deferred_patch(item_id):
    """Resolve or edit a deferred item."""
    data = request.get_json() or {}
    conn = get_connection()
    row = conn.execute('SELECT id FROM deferred_items WHERE id=?', (item_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'ok': False, 'error': 'not found'}), 404
    if 'resolved' in data:
        resolved = 1 if data['resolved'] else 0
        resolved_at = 'datetime("now")' if resolved else 'NULL'
        conn.execute(f'UPDATE deferred_items SET resolved=?, resolved_at={resolved_at} WHERE id=?',
                     (resolved, item_id))
    if 'content' in data:
        conn.execute('UPDATE deferred_items SET content=? WHERE id=?',
                     (data['content'].strip(), item_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/deferred/<int:item_id>', methods=['DELETE'])
def api_deferred_delete(item_id):
    """Hard-delete a deferred item."""
    conn = get_connection()
    conn.execute('DELETE FROM deferred_items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/tickets/<ticket_number>/snooze', methods=['POST'])
def add_snooze_endpoint(ticket_number):
    from database import snooze_ticket
    from listener import _parse_snooze_time
    data     = request.get_json() or {}
    when_raw = (data.get('when') or '').strip()
    note     = (data.get('note') or '').strip()
    conn     = get_connection()
    ticket   = conn.execute(
        "SELECT sender_email FROM tickets WHERE ticket_number=?", (ticket_number,)
    ).fetchone()
    conn.close()
    if not ticket:
        return jsonify({'error': 'ticket not found'}), 404
    wake_at = _parse_snooze_time(when_raw)
    if not wake_at:
        return jsonify({'error': f'could not parse time: {when_raw}'}), 400
    snooze_ticket(ticket_number, ticket['sender_email'], wake_at, note)
    log_activity('terminal', 'snooze_added', f'{ticket_number} until {wake_at}')
    return jsonify({'ok': True, 'wake_at': wake_at})


@app.route('/api/tickets/<ticket_number>/resend', methods=['POST'])
def resend_ticket(ticket_number):
    """Re-send the full final response for a ticket to its sender_email."""
    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, sender_email, question, final_answer, status, gemma_routing '
        'FROM tickets WHERE ticket_number=?', (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    sender = ticket['sender_email']
    question = ticket['question'] or ''
    final_answer = ticket['final_answer'] or ''

    if not sender:
        conn.close()
        return jsonify({'error': 'no sender_email on ticket'}), 400

    # Reconstruct the full response body from stored messages
    try:
        conv_id = int(ticket_number.split('-')[-1])
        rows = conn.execute(
            'SELECT from_agent, content, message_type FROM messages '
            'WHERE conversation_id=? ORDER BY id ASC', (conv_id,)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()

    # Build sections from stored messages
    sections = {}
    is_eight = False
    for r in rows:
        agent = (r['from_agent'] or '').lower()
        mtype = r['message_type'] or ''
        if mtype == 'index':
            continue
        if mtype in ('eight_voice', 'eight_verdict'):
            is_eight = True
            sections[r['from_agent']] = r['content']
        elif agent == 'llama' and 'llama' not in sections:
            sections['llama'] = r['content']
        elif agent == 'qwen' and mtype != 'debate_r2' and 'qwen' not in sections:
            sections['qwen'] = r['content']
        elif agent == 'gemma' and mtype == 'chat' and 'gemma' not in sections:
            sections['gemma'] = r['content']

    if is_eight:
        # SAP / Eight ticket — reconstruct Eight email format
        gemma_verdict = (final_answer
                         or sections.get('Eight/Gemma')
                         or '(Eight synthesis did not complete)')
        parts = ['Eight has finished deliberating.\r\n']
        if sections.get('Eight/Functional'):
            parts.append(f"[Functional analysis]:\r\n{sections['Eight/Functional']}\r\n")
        if sections.get('Eight/Technical'):
            parts.append(f"[Technical analysis]:\r\n{sections['Eight/Technical']}\r\n")
        if sections.get('Eight/Devil'):
            parts.append(f"[Devil's Advocate]:\r\n{sections['Eight/Devil']}\r\n")
        parts.append(f"[Eight — Final verdict]:\r\n{gemma_verdict}\r\n")
        parts.append(f"---\r\nRe: {question[:100]}\r\nSent by Eight | Seven's Swarm | sevenpotato9@gmail.com")
    else:
        # Standard swarm ticket
        gemma_verdict = final_answer or sections.get('gemma', '(no verdict stored)')
        parts = ['The swarm has finished deliberating.\r\n']
        if sections.get('llama'):
            parts.append(f"[LLaMA]:\r\n{sections['llama']}\r\n")
        if sections.get('qwen'):
            parts.append(f"[Qwen]:\r\n{sections['qwen']}\r\n")
        parts.append(f"[Gemma — Final verdict]:\r\n{gemma_verdict}\r\n")
        parts.append(f"---\r\nRe: {question[:100]}\r\nSent by Seven's Swarm | sevenpotato9@gmail.com")

    body = '\r\n'.join(parts)
    subject = f'[Swarm] Full response: {question[:60]}'

    from email_handler import send_reply
    ok = send_reply(to_address=sender, subject=subject, body=body)
    if ok:
        print(f'[Terminal] Resent {ticket_number} to {sender}')
        log_activity('terminal', 'ticket_resent', f'{ticket_number} → {sender}')
        return jsonify({'ok': True, 'sent_to': sender})
    else:
        return jsonify({'error': 'send failed'}), 500


@app.route('/api/tickets/<ticket_number>/assign', methods=['POST'])
def assign_ticket(ticket_number):
    """Manually assign a ticket to a specific agent."""
    _valid_agents = {a['name'].lower() for a in _AGENT_ROSTER if a['name'].lower() != 'ghost'}
    data  = request.get_json() or {}
    agent = (data.get('agent') or '').strip()
    if agent not in _valid_agents:
        return jsonify({'error': f'invalid agent — must be one of {sorted(_valid_agents)}'}), 400

    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, gemma_routing FROM tickets WHERE ticket_number=?',
        (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    # Update agents_assigned and patch gemma_routing to reflect manual override
    import json as _json
    routing = {}
    try:
        routing = _json.loads(ticket['gemma_routing'] or '{}')
    except Exception:
        pass
    routing['agents']           = agent.lower()
    routing['manual_assign']    = True
    routing['manual_assign_to'] = agent

    conn.execute(
        'UPDATE tickets SET agents_assigned=?, gemma_routing=? WHERE ticket_number=?',
        (agent, _json.dumps(routing), ticket_number)
    )
    conn.commit()
    conn.close()
    print(f'[Terminal] Assigned {ticket_number} to {agent}')
    log_activity('terminal', 'ticket_assigned', f'{ticket_number} → {agent}')
    return jsonify({'ok': True, 'ticket': ticket_number, 'assigned_to': agent})


@app.route('/api/tickets/<ticket_number>/close', methods=['POST'])
def force_close_ticket(ticket_number):
    """Manually close a ticket — runs Duck, indexes to memory, marks queue done."""
    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, question, final_answer, queue_id, sender_email, status '
        'FROM tickets WHERE ticket_number=?', (ticket_number,)
    ).fetchone()
    if not ticket:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    if ticket['status'] == 'closed':
        conn.close()
        return jsonify({'error': 'ticket already closed'}), 400

    question     = ticket['question']     or '(no question)'
    final_answer = ticket['final_answer'] or '(no answer stored — manually closed)'
    queue_id     = ticket['queue_id']
    sender_email = ticket['sender_email']
    conn.close()

    # Run librarian_close in a background thread so the response returns immediately
    import threading
    def _do_close():
        try:
            from ticket import librarian_close
            librarian_close(ticket_number, question, final_answer,
                            queue_id=queue_id, sender_email=sender_email)
            log_activity('terminal', 'ticket_force_closed', f'{ticket_number} by Ghost via dashboard')
            print(f'[Terminal] Force-closed {ticket_number}')
        except Exception as ex:
            print(f'[Terminal] Force-close error on {ticket_number}: {ex}')
            log_activity('terminal', 'ticket_force_close_error', f'{ticket_number}: {ex}')

    threading.Thread(target=_do_close, daemon=True).start()
    return jsonify({'ok': True, 'ticket': ticket_number, 'status': 'closing'})


@app.route('/api/tickets/<ticket_number>/reopen', methods=['POST'])
def reopen_ticket_endpoint(ticket_number):
    """Manually reopen a closed ticket."""
    from database import reopen_ticket
    conn = get_connection()
    ticket = conn.execute(
        'SELECT ticket_number, status FROM tickets WHERE ticket_number=?',
        (ticket_number,)
    ).fetchone()
    conn.close()
    if not ticket:
        return jsonify({'error': 'not found'}), 404
    if ticket['status'] == 'open':
        return jsonify({'error': 'ticket already open'}), 400
    reopen_ticket(ticket_number)
    log_activity('terminal', 'ticket_reopened', f'{ticket_number} by Ghost via dashboard')
    print(f'[Terminal] Reopened {ticket_number}')
    return jsonify({'ok': True, 'ticket': ticket_number, 'status': 'open'})


@app.route('/api/tickets/<ticket_number>', methods=['DELETE'])
def delete_ticket(ticket_number):
    conn = get_connection()
    try:
        conn.execute(
            'DELETE FROM ticket_notes WHERE ticket_id=(SELECT id FROM tickets WHERE ticket_number=?)',
            (ticket_number,)
        )
        conn.execute('DELETE FROM tickets WHERE ticket_number=?', (ticket_number,))
        conn.commit()
    finally:
        conn.close()
    print(f'[Terminal] Deleted ticket {ticket_number}')
    return jsonify({'deleted': ticket_number})


# ── Docs (swarm_docs/) ─────────────────────────────────────────────────────────

import os as _os

_DOCS_DIR = _os.path.join(_os.path.dirname(__file__), '..', 'docs')

_DOC_DESCRIPTIONS = {
    '00_index.html':        'Master index — all sections, quick-reference tables',
    '01_overview.html':     'What it is, hardware, the three-layer architecture',
    '02_agents.html':       'All agents, personalities, temperatures, roles',
    '03_pipeline.html':     'Email, Terminal, Telegram and Eight pipeline flows',
    '04_database.html':     'All tables, schema, memory design',
    '05_files.html':        'Complete file reference with code highlights',
    '06_access.html':       'Trust levels, Ghost commands, Fridays trust ladder',
    '07_ghost_circle.html': 'Claude API advisory layer, ghost_circle table',
    '08_sessions.html':     'Chronological build log, all sessions',
    '09_roadmap.html':      'What\'s done, what\'s next, backlog phases',
}


# ── Senders / Access control ──────────────────────────────────────────────────

def _get_sender_lists():
    conn = get_connection()
    trusted = [dict(r) for r in conn.execute(
        "SELECT id, email, added_by, notes, added_at FROM trusted_senders ORDER BY added_at DESC"
    ).fetchall()]
    notification = [dict(r) for r in conn.execute(
        "SELECT id, email, added_by, notes, added_at FROM notification_senders ORDER BY added_at DESC"
    ).fetchall()]
    domains = [dict(r) for r in conn.execute(
        "SELECT id, domain, channel, added_by, notes, added_at FROM trusted_domains ORDER BY added_at DESC"
    ).fetchall()]
    conn.close()
    return {'trusted': trusted, 'notification': notification, 'domains': domains}


@app.route('/api/senders')
def api_senders():
    return jsonify(_get_sender_lists())


@app.route('/api/senders', methods=['POST'])
def add_sender():
    from database import add_trusted_domain
    data    = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'senders_add')
    if gate:
        return gate
    lst     = data.get('list', '')
    address = (data.get('address') or '').strip().lower()
    note    = (data.get('note') or '').strip()
    channel = (data.get('channel') or 'email').strip().lower()
    if not address or lst not in ('trusted', 'notification', 'domain'):
        return jsonify({'error': 'invalid'}), 400
    if lst == 'trusted':
        add_trusted_sender(address, added_by='dashboard', note=note)
    elif lst == 'domain':
        add_trusted_domain(address.lstrip('@'), added_by='dashboard', note=note, channel=channel)
    else:
        add_notification_sender(address, added_by='dashboard', note=note)
    print(f'[Terminal] Added {address} to {lst}')
    return jsonify({'ok': True, 'list': lst, 'address': address})


@app.route('/api/senders', methods=['DELETE'])
def remove_sender():
    data    = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'senders_remove')
    if gate:
        return gate
    lst     = data.get('list', '')
    address = (data.get('address') or '').strip().lower()
    if not address or lst not in ('trusted', 'notification', 'domain'):
        return jsonify({'error': 'invalid'}), 400
    if lst == 'trusted':
        remove_trusted_sender(address)
    elif lst == 'domain':
        conn = get_connection()
        conn.execute("DELETE FROM trusted_domains WHERE LOWER(domain)=?", (address.lstrip('@'),))
        conn.commit()
        conn.close()
    else:
        remove_notification_sender(address)
    print(f'[Terminal] Removed {address} from {lst}')
    return jsonify({'ok': True, 'list': lst, 'address': address})


@app.route('/api/access/manager/onboard', methods=['POST'])
def api_manager_onboard():
    """
    Onboard a second trusted user (manager) using Fridays trust model.
    Body:
      {
        "manager_email": "manager@company.com",        # required
        "manager_name": "Manager",                     # optional
        "manager_telegram_chat_id": "123456789",      # optional
        "add_as_moderator": false,                      # optional
        "dry_run": true,                                # optional (default true)
        "proposal_id": "..."                           # required when dry_run=false and Time Wizard active
      }
    """
    data = request.get_json() or {}
    manager_email = (data.get('manager_email') or '').strip().lower()
    manager_name = (data.get('manager_name') or 'Manager').strip() or 'Manager'
    manager_telegram_chat_id = str(data.get('manager_telegram_chat_id') or '').strip()
    add_as_moderator = bool(data.get('add_as_moderator', False))
    dry_run = bool(data.get('dry_run', True))

    if not manager_email or '@' not in manager_email:
        return jsonify({'ok': False, 'error': 'manager_email required'}), 400

    if manager_telegram_chat_id and not manager_telegram_chat_id.isdigit():
        return jsonify({'ok': False, 'error': 'manager_telegram_chat_id must be numeric'}), 400

    if not dry_run:
        gate = _alm_gate_or_response(data, 'manager_onboard')
        if gate:
            return gate

    trusted_entries = [manager_email]
    if manager_telegram_chat_id:
        trusted_entries.append(f'telegram:{manager_telegram_chat_id}')

    plan = {
        'manager_email': manager_email,
        'manager_name': manager_name,
        'add_as_moderator': add_as_moderator,
        'trusted_entries_to_add': trusted_entries,
        'moderator_entry_to_add': manager_email if add_as_moderator else None,
        'tailscale_step_required': True,
        'tailscale_note': 'Grant manager Tailscale access separately; API does not manage Tailscale identities.',
    }

    if dry_run:
        return jsonify({'ok': True, 'dry_run': True, 'plan': plan})

    results = []
    try:
        add_trusted_sender(manager_email, added_by='dashboard', note=f'Manager onboarding: {manager_name}')
        results.append({'action': 'trusted_sender_add', 'entry': manager_email, 'status': 'ok'})
    except Exception as e:
        if 'UNIQUE' in str(e).upper():
            results.append({'action': 'trusted_sender_add', 'entry': manager_email, 'status': 'exists'})
        else:
            return jsonify({'ok': False, 'error': f'failed to add manager email: {e}', 'results': results}), 500

    if manager_telegram_chat_id:
        tg_entry = f'telegram:{manager_telegram_chat_id}'
        try:
            add_trusted_sender(tg_entry, added_by='dashboard', note=f'Manager onboarding: {manager_name}')
            results.append({'action': 'trusted_sender_add', 'entry': tg_entry, 'status': 'ok'})
        except Exception as e:
            if 'UNIQUE' in str(e).upper():
                results.append({'action': 'trusted_sender_add', 'entry': tg_entry, 'status': 'exists'})
            else:
                return jsonify({'ok': False, 'error': f'failed to add manager telegram: {e}', 'results': results}), 500

    if add_as_moderator:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO moderators (email, name, notes) VALUES (?, ?, ?)",
                (manager_email, manager_name, 'Added via manager onboarding API')
            )
            conn.commit()
            results.append({'action': 'moderator_add', 'entry': manager_email, 'status': 'ok'})
        except Exception as e:
            conn.rollback()
            return jsonify({'ok': False, 'error': f'failed to add moderator: {e}', 'results': results}), 500
        finally:
            conn.close()

    log_activity('terminal', 'manager_onboard', f'email={manager_email} tg={manager_telegram_chat_id or "none"}')
    return jsonify({
        'ok': True,
        'dry_run': False,
        'plan': plan,
        'results': results,
    }), 201


@app.route('/api/docs')
def api_docs():
    docs = []

    # HTML docs (legacy export set)
    html_dir = _os.path.join(_DOCS_DIR, 'html')
    if _os.path.isdir(html_dir):
        for f in sorted(_os.listdir(html_dir)):
            if f.endswith('.html') and f != 'swarm_flow_v3.html':
                path = _os.path.join(html_dir, f)
                mtime = datetime.fromtimestamp(_os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
                docs.append({
                    'filename': f,
                    'title': f,
                    'description': _DOC_DESCRIPTIONS.get(f, ''),
                    'size': _os.path.getsize(path),
                    'kind': 'html',
                    'section': 'html',
                    'modified_at': mtime,
                })

    # Markdown/text docs at docs root + docs/testing for live operational docs
    md_roots = [
        (_DOCS_DIR, 'root'),
        (_os.path.join(_DOCS_DIR, 'testing'), 'testing'),
    ]
    for base, section in md_roots:
        if not _os.path.isdir(base):
            continue
        for f in sorted(_os.listdir(base)):
            if not f.lower().endswith(('.md', '.txt', '.log')):
                continue
            path = _os.path.join(base, f)
            rel = f if section == 'root' else f'{section}/{f}'
            mtime = datetime.fromtimestamp(_os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
            docs.append({
                'filename': rel,
                'title': f,
                'description': '',
                'size': _os.path.getsize(path),
                'kind': 'text',
                'section': section,
                'modified_at': mtime,
            })

    # Newest first for operational visibility
    docs.sort(key=lambda d: d.get('modified_at', ''), reverse=True)
    return jsonify(docs)


@app.route('/api/docs/text/<path:filename>')
def api_docs_text(filename):
    """Serve markdown/text docs from docs roots for modal viewing."""
    if not filename or '..' in filename or filename.startswith('/'):
        return jsonify({'ok': False, 'error': 'invalid filename'}), 400

    candidates = []
    # Allow both explicit subpaths (e.g. testing/ALM_TEST_SPECIFICATION.md)
    # and basename lookups (e.g. ALM_DRIVER.md).
    candidates.append(_os.path.normpath(_os.path.join(_DOCS_DIR, filename)))
    basename = _os.path.basename(filename)
    candidates.append(_os.path.normpath(_os.path.join(_DOCS_DIR, basename)))
    candidates.append(_os.path.normpath(_os.path.join(_DOCS_DIR, 'testing', basename)))

    allowed_roots = [
        _os.path.normpath(_DOCS_DIR),
        _os.path.normpath(_os.path.join(_DOCS_DIR, 'testing')),
    ]

    picked = None
    for path in candidates:
        if not any(path.startswith(root + _os.sep) or path == root for root in allowed_roots):
            continue
        if _os.path.isfile(path) and path.lower().endswith(('.md', '.txt', '.log', '.json')):
            picked = path
            break

    if not picked:
        return jsonify({'ok': False, 'error': 'not found'}), 404

    with open(picked, encoding='utf-8') as fh:
        content = fh.read()
    return jsonify({'ok': True, 'filename': _os.path.basename(picked), 'content': content})


@app.route('/docs/html/<filename>')
def serve_doc_html(filename):
    """Serve a raw HTML doc file (used by iframe in the docs accordion)."""
    if not filename.endswith('.html') or '/' in filename or '..' in filename:
        return 'Not found', 404
    path = _os.path.join(_DOCS_DIR, 'html', filename)
    if not _os.path.isfile(path):
        return 'Not found', 404
    with open(path, encoding='utf-8') as fh:
        content = fh.read()
    return content, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/docs/download/<filename>')
def download_doc_html(filename):
    """Download an HTML doc file."""
    if not filename.endswith('.html') or '/' in filename or '..' in filename:
        return 'Not found', 404
    path = _os.path.join(_DOCS_DIR, 'html', filename)
    if not _os.path.isfile(path):
        return 'Not found', 404
    from flask import send_file
    return send_file(path, as_attachment=True, download_name=filename,
                     mimetype='text/html')


@app.route('/api/project-md')
def api_project_md():
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})


@app.route('/api/project-md', methods=['POST'])
def api_project_md_save():
    """Save edited PROJECT.md content from the dashboard."""
    data    = request.get_json() or {}
    content = data.get('content', '')
    if not content:
        return jsonify({'error': 'empty content'}), 400
    path = '/home/seven/swarm/docs/PROJECT.md'
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    log_activity('terminal', 'project_md_saved', f'{len(content)} chars')
    return jsonify({'ok': True, 'chars': len(content)})


@app.route('/api/kb/seed-swarm-docs', methods=['POST'])
def api_kb_seed_swarm_docs():
    """
    Seed the KB with key PROJECT.md sections so agents can read about the system.
    Idempotent — updates existing docs, inserts new ones.
    """
    import re
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'PROJECT.md not found'}), 404

    with open(path, encoding='utf-8') as fh:
        text = fh.read()

    # Split into H2 sections
    sections = re.split(r'\n(?=## )', text)
    seeded = 0
    conn = get_connection()
    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].lstrip('#').strip()
        content = '\n'.join(lines).strip()
        if len(content) < 40:
            continue
        # Determine which agents see this
        if any(k in heading for k in ('SAP', 'Eight')):
            tags = 'eight'
        elif any(k in heading for k in ('Ghost', 'Nine', 'Layer')):
            tags = 'all'
        else:
            tags = 'all'

        doc_name = f'[Swarm] {heading}'
        existing = conn.execute(
            "SELECT id FROM project_docs WHERE doc_name=?", (doc_name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE doc_name=?",
                (content[:4000], tags, doc_name)
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc_name, content[:4000], tags)
            )
        seeded += 1

    conn.commit()
    conn.close()
    log_activity('terminal', 'kb_seeded', f'{seeded} sections from PROJECT.md')
    return jsonify({'ok': True, 'sections_seeded': seeded})


@app.route('/api/project-md/raw')
def api_project_md_raw():
    from flask import send_file as _sf
    path = '/home/seven/swarm/docs/PROJECT.md'
    if not _os.path.isfile(path):
        return 'Not found', 404
    return _sf(path, as_attachment=True, download_name='PROJECT.md', mimetype='text/markdown')


@app.route('/api/testing-md')
def api_testing_md():
    """Return the content of UAT_TEST_SCRIPTS.md for the dashboard."""
    path = '/home/seven/swarm/docs/UAT_TEST_SCRIPTS.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})


@app.route('/api/bugs-md')
def api_bugs_md():
    """Return the content of BUGS.md for the dashboard."""
    path = '/home/seven/swarm/docs/BUGS.md'
    if not _os.path.isfile(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as fh:
        return jsonify({'content': fh.read()})


@app.route('/api/testing/run-simulation', methods=['POST'])
def api_run_simulation():
    """Trigger simulate.py and return the output captured from stdout/stderr."""
    import subprocess
    import os
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'run_simulation')
    if gate:
        return gate
    try:
        script_path = '/home/seven/swarm/utils/simulate.py'
        # Run via the current interpreter to ensure paths and env are correct
        result = subprocess.run([sys.executable, script_path], 
                                capture_output=True, text=True, timeout=600)
        return jsonify({
            'ok': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/shell/execute', methods=['POST'])
def api_shell_execute():
    """Execute a whitelisted shell command via shell_agent."""
    from fridays.shell_agent import run as shell_run
    data = request.get_json() or {}
    command = data.get('command', '').strip()

    gate = _alm_gate_or_response(data, 'shell_execute')
    if gate:
        return gate
    
    if not command:
        return jsonify({'ok': False, 'output': 'No command provided', 'message': 'Command is required'}), 400
    
    try:
        success, output = shell_run(command, agent='terminal_ui', notify_ghost=True)
        return jsonify({
            'ok': success,
            'output': output,
            'command': command,
        })
    except Exception as e:
        return jsonify({
            'ok': False,
            'output': f'Error executing command: {str(e)}',
            'command': command,
        }), 500


@app.route('/api/shell/stream', methods=['POST'])
def api_shell_stream():
    """Execute a whitelisted shell command and stream output via SSE."""
    from fridays import shell_agent as _shell

    data = request.get_json() or {}
    command = str(data.get('command') or '').strip()

    gate = _alm_gate_or_response(data, 'shell_execute')
    if gate:
        return gate

    if not command:
        return jsonify({'ok': False, 'error': 'Command is required'}), 400

    match = _shell._match_whitelist(command)
    if match is None:
        return jsonify({'ok': False, 'error': f'Command not on whitelist: {command[:100]}'}), 403

    max_output = int(getattr(_shell, 'MAX_OUTPUT', 4000))
    timeout_sec = int(getattr(_shell, 'TIMEOUT_SEC', 30))

    def _emit(payload):
        return f"data: {json.dumps(payload)}\n\n"

    def _generate():
        import subprocess
        started = time.time()
        total = 0
        proc = None
        truncated = False
        command_id = uuid.uuid4().hex

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd='/home/seven/swarm',
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            with _SHELL_STREAM_LOCK:
                _SHELL_STREAM_PROCS[command_id] = proc

            yield _emit({'type': 'start', 'command': command, 'command_id': command_id})

            while True:
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if line == '' and proc.poll() is not None:
                    break

                if line:
                    total += len(line)
                    if total > max_output:
                        allowed = max(0, max_output - (total - len(line)))
                        clipped = line[:allowed]
                        if clipped:
                            yield _emit({'type': 'chunk', 'text': clipped})
                        truncated = True
                        proc.kill()
                        break
                    yield _emit({'type': 'chunk', 'text': line})

                if time.time() - started > timeout_sec:
                    proc.kill()
                    yield _emit({'type': 'error', 'error': 'command timed out'})
                    return

            returncode = proc.wait(timeout=1) if proc else 1
            elapsed_ms = int((time.time() - started) * 1000)
            yield _emit({
                'type': 'done',
                'ok': returncode == 0 and not truncated,
                'returncode': returncode,
                'truncated': truncated,
                'elapsed_ms': elapsed_ms,
                'command_id': command_id,
            })
        except Exception as e:
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            yield _emit({'type': 'error', 'error': str(e), 'command_id': command_id})
        finally:
            with _SHELL_STREAM_LOCK:
                _SHELL_STREAM_PROCS.pop(command_id, None)

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/terminal/run', methods=['POST'])
def api_terminal_run():
    """Alias for /api/shell/execute for backward compatibility."""
    return api_shell_execute()


@app.route('/api/terminal/stream', methods=['POST'])
def api_terminal_stream():
    """Alias for /api/shell/stream for backward compatibility."""
    return api_shell_stream()


@app.route('/api/shell/stream/stop', methods=['POST'])
def api_shell_stream_stop():
    """Stop a running shell stream command by command_id."""
    data = request.get_json() or {}
    command_id = str(data.get('command_id') or '').strip()
    if not command_id:
        return jsonify({'ok': False, 'error': 'command_id required'}), 400

    stopped = False
    with _SHELL_STREAM_LOCK:
        proc = _SHELL_STREAM_PROCS.get(command_id)
    if proc and proc.poll() is None:
        try:
            proc.kill()
            stopped = True
        except Exception:
            stopped = False

    return jsonify({'ok': True, 'command_id': command_id, 'stopped': stopped})


@app.route('/api/terminal/stream/stop', methods=['POST'])
def api_terminal_stream_stop():
    """Alias for /api/shell/stream/stop."""
    return api_shell_stream_stop()


@app.route('/api/hands/run', methods=['POST'])
def api_hands_run():
    """Alias for /api/shell/execute - named for Ghost/terminal metaphor."""
    return api_shell_execute()


@app.route('/api/workspace/dir', methods=['GET'])
def api_workspace_dir():
    """
    Browse workspace directory structure.
    Query params:
    - path: directory path to list (default: /home/seven/swarm) — must be within SWARM_ROOT
    - depth: recursion depth for tree listing (default: 1, max: 3) — 0 = flat list only
    
    Returns: {ok, path, entries: [{name, type, size, modified, is_dir, permissions, ...}]}
    """
    import stat as _stat
    
    base_path = request.args.get('path', '/home/seven/swarm').strip() or '/home/seven/swarm'
    try:
        depth = int(request.args.get('depth', 1) or 1)
    except ValueError:
        depth = 1
    depth = max(0, min(depth, 3))  # Cap at 3 levels
    
    # Security: only allow paths within SWARM_ROOT
    try:
        swarm_root = Path('/home/seven/swarm')
        requested = Path(base_path).resolve()
        if not str(requested).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400
    
    if not requested.exists():
        return jsonify({'ok': False, 'error': 'path not found'}), 404
    if not requested.is_dir():
        return jsonify({'ok': False, 'error': 'path is not a directory'}), 400
    
    def _entry_dict(path):
        """Convert a file/dir to a dict with metadata."""
        try:
            stat = path.stat()
            is_dir = path.is_dir()
            return {
                'name': path.name,
                'type': 'dir' if is_dir else 'file',
                'size': stat.st_size if not is_dir else 0,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'permissions': oct(stat.st_mode)[-3:],
                'path': str(path.relative_to(swarm_root)),
            }
        except Exception:
            return None
    
    def _list_dir_recursive(dir_path, current_depth):
        """Recursively list directory with depth limit."""
        entries = []
        try:
            items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            for item in items:
                # Skip hidden files/dirs and common noise
                if item.name.startswith('.') or item.name in ('__pycache__', '.pytest_cache', 'node_modules'):
                    continue
                entry = _entry_dict(item)
                if entry:
                    entries.append(entry)
                    # Recurse into subdirs if within limit
                    if item.is_dir() and current_depth < depth:
                        entries.extend(_list_dir_recursive(item, current_depth + 1))
        except PermissionError:
            pass
        return entries
    
    entries = _list_dir_recursive(requested, 0)
    
    return jsonify({
        'ok': True,
        'path': str(requested.relative_to(swarm_root)),
        'absolute_path': str(requested),
        'entries': entries,
        'count': len(entries),
        'depth_limit': depth,
    })


@app.route('/api/workspace/file', methods=['GET'])
def api_workspace_file():
    """
    Read a file from the workspace.
    Query params:
    - path: file path relative to SWARM_ROOT (required)
    - max_bytes: max size to read (default: 100000, max: 500000)
    
    Returns: {ok, path, content, size, mime_type}
    """
    import mimetypes
    
    file_path = request.args.get('path', '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'path required'}), 400
    
    try:
        max_bytes = int(request.args.get('max_bytes', 100000) or 100000)
    except ValueError:
        max_bytes = 100000
    max_bytes = max(1024, min(max_bytes, 500000))  # 1KB min, 500KB max
    
    try:
        swarm_root = Path('/home/seven/swarm')
        full_path = (swarm_root / file_path).resolve()
        
        # Security check
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400
    
    if not full_path.exists():
        return jsonify({'ok': False, 'error': 'file not found'}), 404
    if not full_path.is_file():
        return jsonify({'ok': False, 'error': 'path is not a file'}), 400
    
    try:
        size = full_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(str(full_path))
        
        # Read file content (with limit)
        with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read(max_bytes)
        
        # Flag if truncated
        truncated = size > max_bytes
        
        return jsonify({
            'ok': True,
            'path': str(full_path.relative_to(swarm_root)),
            'content': content,
            'size': size,
            'truncated': truncated,
            'mime_type': mime_type or 'text/plain',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/workspace/file', methods=['PUT'])
def api_workspace_file_save():
    """
    Save a text file inside the workspace.
    JSON body:
    - path: file path relative to SWARM_ROOT (required)
    - content: new text content (required)
    - proposal_id: required when ALM gate is active
    """
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'workspace_file_write')
    if gate:
        return gate

    file_path = str(data.get('path') or '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'path required'}), 400

    if 'content' not in data:
        return jsonify({'ok': False, 'error': 'content required'}), 400
    content = str(data.get('content') or '')

    # Soft limit to keep payloads bounded in UI workflow.
    if len(content.encode('utf-8', errors='replace')) > 1_000_000:
        return jsonify({'ok': False, 'error': 'content too large (max 1MB)'}), 413

    try:
        swarm_root = Path('/home/seven/swarm')
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    if not full_path.exists():
        return jsonify({'ok': False, 'error': 'file not found'}), 404
    if not full_path.is_file():
        return jsonify({'ok': False, 'error': 'path is not a file'}), 400

    # Basic binary-file guard for UI save operations.
    try:
        with open(full_path, 'rb') as fh:
            probe = fh.read(4096)
        if b'\x00' in probe:
            return jsonify({'ok': False, 'error': 'refusing to overwrite binary file'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'file probe failed: {e}'}), 500

    try:
        with open(full_path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        size = full_path.stat().st_size
        rel_path = str(full_path.relative_to(swarm_root))
        log_activity('terminal', 'workspace_file_saved', rel_path)
        return jsonify({'ok': True, 'path': rel_path, 'size': size})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/workspace/search', methods=['GET'])
def api_workspace_search():
    """
    Search for files in workspace by name pattern.
    Query params:
    - pattern: filename pattern (glob-style, * = wildcard, default: *)
    - max_results: max results to return (default: 50, max: 500)
    
    Returns: {ok, pattern, matches: [{name, path, size, type}]}
    """
    from fnmatch import fnmatch
    
    pattern = request.args.get('pattern', '*').strip() or '*'
    try:
        max_results = int(request.args.get('max_results', 50) or 50)
    except ValueError:
        max_results = 50
    max_results = max(1, min(max_results, 500))
    
    swarm_root = Path('/home/seven/swarm')
    matches = []
    
    try:
        for path in swarm_root.rglob('*'):
            # Skip hidden, noise
            if any(part.startswith('.') for part in path.parts):
                continue
            if any(part in ('__pycache__', '.pytest_cache', 'node_modules') for part in path.parts):
                continue
            
            # Match against pattern
            if not fnmatch(path.name, pattern):
                continue
            
            if len(matches) >= max_results:
                break
            
            try:
                stat = path.stat()
                matches.append({
                    'name': path.name,
                    'path': str(path.relative_to(swarm_root)),
                    'type': 'dir' if path.is_dir() else 'file',
                    'size': stat.st_size if path.is_file() else 0,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except Exception:
                pass
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    
    return jsonify({
        'ok': True,
        'pattern': pattern,
        'matches': matches,
        'count': len(matches),
        'truncated': len(matches) >= max_results,
    })


def _workspace_replace_candidates(scope_path, pattern, max_files=300):
    """Return candidate files inside workspace for find/replace operations."""
    swarm_root = Path('/home/seven/swarm')
    rel_scope = str(scope_path or '').strip().lstrip('/')
    scope = (swarm_root / rel_scope).resolve() if rel_scope else swarm_root
    if not str(scope).startswith(str(swarm_root)):
        raise ValueError('scope outside workspace')
    if not scope.exists():
        raise ValueError('scope not found')

    def _skip(path_obj):
        parts = path_obj.parts
        if any(part.startswith('.') for part in parts):
            return True
        if any(part in ('__pycache__', '.pytest_cache', 'node_modules') for part in parts):
            return True
        return False

    candidates = []
    if scope.is_file():
        if not _skip(scope.relative_to(swarm_root)):
            candidates.append(scope)
        return swarm_root, candidates

    for path in scope.rglob(pattern or '*.py'):
        if len(candidates) >= max_files:
            break
        if not path.is_file():
            continue
        rel = path.relative_to(swarm_root)
        if _skip(rel):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except Exception:
            continue
        candidates.append(path)
    return swarm_root, candidates


@app.route('/api/workspace/replace/preview', methods=['POST'])
def api_workspace_replace_preview():
    """Preview bulk find/replace without writing files."""
    data = request.get_json() or {}
    find_text = str(data.get('find_text') or '')
    replace_text = str(data.get('replace_text') or '')
    pattern = str(data.get('pattern') or '*.py').strip() or '*.py'
    scope_path = str(data.get('scope_path') or '').strip()

    if not find_text:
        return jsonify({'ok': False, 'error': 'find_text required'}), 400
    if len(find_text) > 5000:
        return jsonify({'ok': False, 'error': 'find_text too large'}), 400

    try:
        swarm_root, candidates = _workspace_replace_candidates(scope_path, pattern, max_files=400)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    matches = []
    total_replacements = 0
    scanned = 0
    for file_path in candidates:
        scanned += 1
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        occurrences = content.count(find_text)
        if occurrences <= 0:
            continue
        total_replacements += occurrences
        line_hits = []
        for idx, line in enumerate(content.splitlines(), start=1):
            if find_text in line:
                line_hits.append(idx)
                if len(line_hits) >= 8:
                    break
        matches.append({
            'path': str(file_path.relative_to(swarm_root)),
            'occurrences': occurrences,
            'lines': line_hits,
        })

    return jsonify({
        'ok': True,
        'scope_path': scope_path,
        'pattern': pattern,
        'find_text': find_text,
        'replace_text': replace_text,
        'scanned_files': scanned,
        'matched_files': len(matches),
        'total_replacements': total_replacements,
        'matches': matches[:200],
        'truncated': len(matches) > 200,
    })


@app.route('/api/workspace/replace/apply', methods=['POST'])
def api_workspace_replace_apply():
    """Apply bulk find/replace across workspace files."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    find_text = str(data.get('find_text') or '')
    replace_text = str(data.get('replace_text') or '')
    pattern = str(data.get('pattern') or '*.py').strip() or '*.py'
    scope_path = str(data.get('scope_path') or '').strip()

    if not find_text:
        return jsonify({'ok': False, 'error': 'find_text required'}), 400
    if len(find_text) > 5000:
        return jsonify({'ok': False, 'error': 'find_text too large'}), 400

    try:
        swarm_root, candidates = _workspace_replace_candidates(scope_path, pattern, max_files=400)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

    changed_files = []
    total_replacements = 0
    for file_path in candidates:
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        occurrences = content.count(find_text)
        if occurrences <= 0:
            continue

        updated = content.replace(find_text, replace_text)
        if updated == content:
            continue

        try:
            file_path.write_text(updated, encoding='utf-8')
        except Exception:
            continue

        total_replacements += occurrences
        changed_files.append({
            'path': str(file_path.relative_to(swarm_root)),
            'occurrences': occurrences,
        })

    log_activity('terminal', 'workspace_replace_apply', f"scope={scope_path or '/'} pattern={pattern} files={len(changed_files)} replacements={total_replacements}")
    return jsonify({
        'ok': True,
        'scope_path': scope_path,
        'pattern': pattern,
        'changed_files': len(changed_files),
        'total_replacements': total_replacements,
        'changes': changed_files[:200],
        'truncated': len(changed_files) > 200,
    })


@app.route('/api/code-ops/pytest', methods=['POST'])
def api_code_ops_pytest():
    """Run pytest on a file inside the workspace."""
    data = request.get_json() or {}
    file_path = str(data.get('file_path') or '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'file_path required'}), 400

    try:
        swarm_root = Path('/home/seven/swarm')
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
        if not full_path.exists() or not full_path.is_file():
            return jsonify({'ok': False, 'error': 'file not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'pytest', str(full_path), '-q', '--maxfail=20'],
            cwd=str(swarm_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        passed = output.count(' passed')
        failed = output.count(' failed')
        return jsonify({
            'ok': proc.returncode == 0,
            'passed': passed,
            'failed': failed,
            'returncode': proc.returncode,
            'output': output[-8000:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'pytest timed out'}), 504
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/code-ops/pylint', methods=['POST'])
def api_code_ops_pylint():
    """Run pylint on a Python file inside the workspace."""
    data = request.get_json() or {}
    file_path = str(data.get('file_path') or '').strip()
    if not file_path:
        return jsonify({'ok': False, 'error': 'file_path required'}), 400
    if not file_path.endswith('.py'):
        return jsonify({'ok': False, 'error': 'only .py files supported'}), 400

    try:
        swarm_root = Path('/home/seven/swarm')
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
        if not full_path.exists() or not full_path.is_file():
            return jsonify({'ok': False, 'error': 'file not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'pylint', str(full_path), '--output-format=text', '--score=n'],
            cwd=str(swarm_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        issue_lines = [ln for ln in output.splitlines() if ': ' in ln and ('warning' in ln.lower() or 'error' in ln.lower() or 'convention' in ln.lower() or 'refactor' in ln.lower())]
        issues = [{'line': 0, 'msg': ln[:240]} for ln in issue_lines[:20]]
        return jsonify({
            'ok': len(issues) == 0 and proc.returncode == 0,
            'count': len(issues),
            'issues': issues,
            'returncode': proc.returncode,
            'output': output[-8000:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': 'pylint timed out'}), 504
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/code-ops/format', methods=['POST'])
def api_code_ops_format():
    """Format Python source text using black and return formatted content."""
    data = request.get_json() or {}
    file_path = str(data.get('file_path') or '').strip()
    content = str(data.get('content') or '')
    if not file_path:
        return jsonify({'ok': False, 'error': 'file_path required'}), 400
    if not file_path.endswith('.py'):
        return jsonify({'ok': False, 'error': 'only .py files supported'}), 400

    try:
        swarm_root = Path('/home/seven/swarm')
        full_path = (swarm_root / file_path).resolve()
        if not str(full_path).startswith(str(swarm_root)):
            return jsonify({'ok': False, 'error': 'path outside workspace'}), 403
    except Exception as e:
        return jsonify({'ok': False, 'error': f'invalid path: {e}'}), 400

    try:
        import black
        formatted = black.format_str(content, mode=black.FileMode())
    except ImportError:
        return jsonify({'ok': False, 'error': 'black not installed'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': f'black format failed: {e}'}), 400

    orig_lines = content.split('\n')
    new_lines = formatted.split('\n')
    changed = sum(1 for a, b in zip(orig_lines, new_lines) if a != b) + abs(len(orig_lines) - len(new_lines))
    return jsonify({
        'ok': True,
        'formatted_content': formatted,
        'lines_changed': changed,
    })


@app.route('/api/code-ops/commit', methods=['POST'])
def api_code_ops_commit():
    """Commit staged workspace changes."""
    data = request.get_json() or {}
    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    message = str(data.get('message') or 'Update via Files panel').strip()
    proposal_id = str(data.get('proposal_id') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'message required'}), 400

    import subprocess
    try:
        swarm_root = '/home/seven/swarm'
        subprocess.run(['git', '-C', swarm_root, 'add', '-A'], capture_output=True, text=True, timeout=20)
        status = subprocess.run(['git', '-C', swarm_root, 'status', '--porcelain'], capture_output=True, text=True, timeout=20)
        status_lines = [ln for ln in (status.stdout or '').splitlines() if ln.strip()]
        if not status_lines:
            return jsonify({'ok': True, 'message': 'No changes to commit', 'files_changed': 0})

        final_msg = message
        if proposal_id:
            final_msg = f"{message} (proposal:{proposal_id[:12]})"

        commit = subprocess.run(
            ['git', '-C', swarm_root, 'commit', '-m', final_msg],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if commit.returncode != 0:
            return jsonify({'ok': False, 'error': (commit.stderr or commit.stdout or 'commit failed').strip()[:500]}), 500

        rev = subprocess.run(['git', '-C', swarm_root, 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10)
        commit_hash = (rev.stdout or '').strip()
        return jsonify({
            'ok': True,
            'commit_hash': commit_hash,
            'files_changed': len(status_lines),
            'message': 'Changes committed',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/monitor/stats')
def api_monitor_stats():
    """System snapshot + API usage counts for Monitor tab."""
    import subprocess
    conn = get_connection()

    # System snapshot (live)
    try:
        import psutil
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu  = psutil.cpu_percent(interval=0.2)
        sys_snap = {
            'ram_used_gb':   round(mem.used  / 1e9, 1),
            'ram_total_gb':  round(mem.total / 1e9, 1),
            'ram_percent':   mem.percent,
            'swap_used_gb':  round(swap.used  / 1e9, 1),
            'swap_total_gb': round(swap.total / 1e9, 1),
            'swap_percent':  swap.percent,
            'cpu_percent':   cpu,
        }
    except Exception:
        sys_snap = {}

    # Claude usage
    claude_today = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM claude_log WHERE date(created_at)=date('now')"
    ).fetchone()
    claude_total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_used),0) FROM claude_log"
    ).fetchone()

    # Serper usage
    serper_today = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='serper' AND event='search' AND date(created_at)=date('now')"
    ).fetchone()[0]
    serper_total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='serper' AND event='search'"
    ).fetchone()[0]

    # Tavily usage
    tavily_today = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='tavily' AND event='search' AND date(created_at)=date('now')"
    ).fetchone()[0]
    tavily_total = conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE service='tavily' AND event='search'"
    ).fetchone()[0]

    # Service health (systemctl)
    services = {
        'swarm-listener':  'Listener',
        'swarm-telegram':  'Telegram',
        'swarm-discord':   'Discord',
        'swarm-scheduler': 'Scheduler',
        'swarm-terminal':  'Terminal',
        'swarm-skills':    'Skills',
    }
    health = {}
    for svc, label in services.items():
        try:
            r = subprocess.run(['systemctl', 'is-active', svc],
                               capture_output=True, text=True, timeout=3)
            health[svc] = {'label': label, 'state': r.stdout.strip()}
        except Exception:
            health[svc] = {'label': label, 'state': 'unknown'}

    return jsonify({
        'system': sys_snap,
        'claude': {
            'calls_today': claude_today[0],
            'tokens_today': claude_today[1],
            'calls_total': claude_total[0],
            'tokens_total': claude_total[1],
        },
        'serper': {'calls_today': serper_today, 'calls_total': serper_total},
        'tavily': {'calls_today': tavily_today, 'calls_total': tavily_total},
        'services': health,
    })


@app.route('/api/tailscale')
def api_tailscale():
    """Return Tailscale peer list from cached status."""
    import subprocess, json
    try:
        r = subprocess.run(['tailscale', 'status', '--json'],
                           capture_output=True, text=True, timeout=5)
        data = json.loads(r.stdout)
        peers = []
        self_node = data.get('Self', {})
        peers.append({
            'name':   self_node.get('HostName', 'self'),
            'ip':     (self_node.get('TailscaleIPs') or [''])[0],
            'online': True,
            'self':   True,
            'os':     self_node.get('OS', ''),
        })
        for key, peer in (data.get('Peer') or {}).items():
            peers.append({
                'name':   peer.get('HostName', key[:8]),
                'ip':     (peer.get('TailscaleIPs') or [''])[0],
                'online': peer.get('Online', False),
                'self':   False,
                'os':     peer.get('OS', ''),
            })
        return jsonify({'peers': peers, 'error': None})
    except Exception as e:
        return jsonify({'peers': [], 'error': str(e)})


@app.route('/api/sandpits')
def api_sandpits():
    stats = get_sandpit_stats()
    # Normalise into agents list for VS Explorer + keep raw stats
    agents = [
        {'agent': k, 'file_count': v.get('files', 0), 'bytes': v.get('bytes', 0)}
        for k, v in stats.items()
        if k != '_total'
    ]
    return jsonify({
        'agents': agents,
        'stats':  stats,
        'log':    sandpit_log(50),
    })


@app.route('/api/skills')
def api_skills():
    from fridays.skills import list_skills
    return jsonify(list_skills())


@app.route('/api/auth/profiles')
def api_auth_profiles():
    include_inactive = request.args.get('include_inactive', '0') in ('1', 'true', 'yes')
    return jsonify({'ok': True, 'profiles': list_user_profiles(include_inactive=include_inactive)})


@app.route('/api/auth/context')
def api_auth_context():
    data = {
        'acting_user': request.args.get('acting_user', 'ghost'),
        'proxy_as': request.args.get('proxy_as', ''),
    }
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    return jsonify({
        'ok': True,
        'identity': {
            'acting_user': identity['acting_user'],
            'proxy_as': identity['proxy_as'],
            'effective_user': identity['effective_user'],
            'can_proxy': identity['can_proxy'],
        },
        'effective_profile': identity['effective'],
    })


@app.route('/api/auth/profiles', methods=['POST'])
def api_auth_profiles_create():
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['acting_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can create profiles'}), 403

    username = (data.get('username') or '').strip().lower()
    display_name = (data.get('display_name') or username).strip()
    user_type = (data.get('user_type') or 'human').strip().lower()
    linked_agent = (data.get('linked_agent') or '').strip().lower()
    is_active = bool(data.get('is_active', True))
    can_proxy = bool(data.get('can_proxy', False))
    if not username:
        return jsonify({'ok': False, 'error': 'username required'}), 400

    profile = upsert_user_profile(
        username=username,
        display_name=display_name,
        user_type=user_type,
        linked_agent=linked_agent,
        is_active=1 if is_active else 0,
        can_proxy=1 if can_proxy else 0,
        created_by='ghost',
    )
    log_activity('terminal', 'profile_created', f'{username} by ghost')
    return jsonify({'ok': True, 'profile': profile}), 201


@app.route('/api/auth/profiles/<username>', methods=['PATCH'])
def api_auth_profiles_patch(username):
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['acting_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can update profiles'}), 403

    existing = get_user_profile(username)
    if not existing:
        return jsonify({'ok': False, 'error': 'profile not found'}), 404

    updated = upsert_user_profile(
        username=username,
        display_name=data.get('display_name', existing.get('display_name') or username),
        user_type=data.get('user_type', existing.get('user_type') or 'human'),
        linked_agent=data.get('linked_agent', existing.get('linked_agent') or ''),
        is_active=bool(data.get('is_active', bool(existing.get('is_active')))),
        can_proxy=bool(data.get('can_proxy', bool(existing.get('can_proxy')))),
        created_by='ghost',
    )
    log_activity('terminal', 'profile_updated', f'{username} by ghost')
    return jsonify({'ok': True, 'profile': updated})


@app.route('/api/skills/permissions')
def api_skills_permissions():
    username = (request.args.get('username') or request.args.get('user') or '').strip().lower()
    if not username:
        return jsonify({'ok': False, 'error': 'username required'}), 400
    profile = get_user_profile(username)
    if not profile:
        return jsonify({'ok': False, 'error': 'profile not found'}), 404
    return jsonify({
        'ok': True,
        'username': username,
        'permissions': list_user_skill_permissions(username),
    })


@app.route('/api/skills/permissions', methods=['POST'])
def api_skills_permissions_update():
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['acting_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can update permissions'}), 403

    username = (data.get('username') or '').strip().lower()
    skill_name = (data.get('skill_name') or data.get('skill') or '').strip().lower()
    allowed = bool(data.get('allowed', True))
    if not username or not skill_name:
        return jsonify({'ok': False, 'error': 'username and skill_name required'}), 400
    if not get_user_profile(username):
        return jsonify({'ok': False, 'error': 'profile not found'}), 404

    set_user_skill_permission(username, skill_name, allowed=allowed, created_by='ghost')
    log_activity('terminal', 'skill_permission_updated', f'{username}:{skill_name}={"allow" if allowed else "deny"}')
    return jsonify({
        'ok': True,
        'username': username,
        'permissions': list_user_skill_permissions(username),
    })


@app.route('/api/skills/run', methods=['POST'])
def api_skills_run():
    data = request.get_json() or {}
    skill_name = (data.get('skill') or '').strip().lower()
    args       = (data.get('args')  or '').strip()

    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    if not skill_name:
        return jsonify({'error': 'skill name required'}), 400
    from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY
    meta = SKILL_REGISTRY.get(skill_name)
    if not meta:
        known = ', '.join(sorted(SKILL_REGISTRY.keys()))
        return jsonify({'ok': False, 'error': f"Unknown skill: {skill_name!r}. Known skills: {known}"}), 400

    effective_user = identity['effective_user']
    if not can_user_invoke_skill(effective_user, skill_name, default_allow=True):
        return jsonify({'ok': False, 'error': f'user {effective_user} is not authorized for skill {skill_name}'}), 403

    trust_level = int(meta.get('trust_level', 0) or 0)
    if trust_level >= 1:
        gate = _alm_gate_or_response(data, f'skills_run_{skill_name}')
        if gate:
            return gate

    ok, output = skill_call(skill_name, args=args, agent=effective_user)
    return jsonify({'ok': ok, 'output': output, 'identity': {
        'acting_user': identity['acting_user'],
        'proxy_as': identity['proxy_as'],
        'effective_user': effective_user,
    }})


@app.route('/api/ghost_circle')
def api_ghost_circle():
    from database import get_ghost_circle_entries
    limit = int(request.args.get('limit', 50))
    return jsonify(get_ghost_circle_entries(limit=limit))


@app.route('/api/monitor')
def api_monitor():
    """Monitor data for the home dashboard."""
    from monitor import get_system_status
    status = get_system_status()
    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        running_jobs = [
            _chat_job_public(j)
            for j in _CHAT_JOBS.values()
            if str(j.get('status', 'running')).lower() == 'running'
        ]
    running_jobs.sort(key=lambda j: j.get('agent') or '')

    active_models = status.get('active_models') or []
    vram_used_bytes = 0
    resident_bytes = 0
    for model in active_models:
        if not isinstance(model, dict):
            continue
        try:
            vram_used_bytes += max(0, int(model.get('size_vram') or 0))
        except Exception:
            pass
        try:
            resident_bytes += max(0, int(model.get('size') or 0))
        except Exception:
            pass

    vram_used_gb = round(vram_used_bytes / (1024 ** 3), 2)
    resident_models_gb = round(resident_bytes / (1024 ** 3), 2)
    if active_models and vram_used_bytes <= 0:
        inference_mode = 'cpu-only'
    elif active_models:
        inference_mode = 'gpu-accelerated'
    else:
        inference_mode = 'idle'

    cpu_pct = float(status.get('cpu_percent') or 0)
    ram_pct = float(status.get('ram_percent') or 0)
    swap_pct = float(status.get('swap_percent') or 0)
    insights = []

    if inference_mode == 'cpu-only' and active_models:
        insights.append('GPU VRAM unavailable: local inference is CPU-only; slowdowns under load are expected.')
    if cpu_pct >= 95 and len(running_jobs) >= 3:
        insights.append('High contention: CPU saturated with multiple active agent jobs.')
    if swap_pct >= 10:
        insights.append('Swap pressure is high: expect longer responses while memory pages move to NVMe swap.')
    elif swap_pct >= 3 and running_jobs:
        insights.append('Swap is active during runtime jobs: throughput may dip, but completion should continue.')
    if ram_pct >= 90:
        insights.append('RAM usage is very high: prefer fewer concurrent local agents for faster turnaround.')

    delayed_agents = []
    for j in running_jobs:
        eta = int(j.get('eta_seconds') or 0)
        elapsed = int(j.get('elapsed_ms') or 0)
        if eta > 0 and elapsed > int(eta * 1400):
            delayed_agents.append(j.get('agent') or 'agent')
    if delayed_agents:
        unique = ', '.join(sorted(set(delayed_agents)))
        insights.append(f'ETA drift detected for: {unique}. Jobs are still running; monitor live stage updates.')

    if not insights:
        insights.append('System stable: no immediate runtime pressure detected.')

    return jsonify({
        'agents_online':  status.get('open_tickets', 0),   # repurposed for display
        'last_activity':  status.get('timestamp', '—'),
        'pending_tasks':  status.get('queue_depth', 0),
        'system_load':    f"{status.get('cpu_percent', 0):.0f}%",
        'memory_usage':   f"{status.get('ram_percent', 0):.0f}%",
        # Rich fields for the Monitor window
        'cpu_percent':    status.get('cpu_percent', 0),
        'cpu_temp_c':     status.get('cpu_temp_c', 0),
        'ram_percent':    status.get('ram_percent', 0),
        'ram_used_gb':    status.get('ram_used_gb', 0),
        'ram_total_gb':   status.get('ram_total_gb', 0),
        'swap_percent':   status.get('swap_percent', 0),
        'active_model':   status.get('active_model', 'none'),
        'active_models':  active_models,
        'active_models_count': status.get('active_models_count', 0),
        'vram_used_gb':   vram_used_gb,
        'resident_models_gb': resident_models_gb,
        'inference_mode': inference_mode,
        'monitor_insights': insights,
        'open_tickets':   status.get('open_tickets', 0),
        'queue_depth':    status.get('queue_depth', 0),
        'queue_processing': status.get('queue_processing', 0),
        'consults_today': status.get('consults_today', 0),
        'disks':          status.get('disks', []),
        'memory_pools':   status.get('memory_pools', {}),
        'runtime_jobs':   running_jobs,
        'duck_flags_today': _get_duck_flags_today(),
    })


def _get_duck_flags_today():
    """Return count of Duck NO results today (used by attention panel)."""
    try:
        conn = get_connection()
        n = conn.execute(
            "SELECT COUNT(*) FROM duck_log WHERE result='NO' AND DATE(created_at)=DATE('now')"
        ).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


@app.route('/api/alm/status')
def api_alm_status():
    """Return ALM governance status for UI visibility and audits."""
    require_approvals = os.environ.get('ALM_REQUIRE_APPROVALS', '1') == '1'
    time_wizard_active = _is_time_wizard_active()
    sniffles_enabled = 'Sniffles' not in DISABLED_AGENTS

    pending = 0
    approved = 0
    executed = 0
    total = 0
    legacy_pending_files = 0

    conn = get_connection()
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='work_proposals'"
        ).fetchone()
        if table:
            rows = conn.execute(
                "SELECT status, COUNT(*) as c FROM work_proposals GROUP BY status"
            ).fetchall()
            for r in rows:
                st = (r['status'] or '').lower()
                c = int(r['c'])
                total += c
                if st == 'pending':
                    pending += c
                elif st == 'approved':
                    approved += c
                elif st == 'executed':
                    executed += c
    finally:
        conn.close()

    try:
        from sandpits import list_proposals
        legacy_pending_files = len(list_proposals() or [])
    except Exception:
        legacy_pending_files = 0

    status = 'enforced' if (require_approvals and time_wizard_active) else 'warn'
    return jsonify({
        'ok': True,
        'status': status,
        'time_wizard_active': time_wizard_active,
        'alm_require_approvals': require_approvals,
        'sniffles_enabled': sniffles_enabled,
        'work_proposals': {
            'total': total,
            'pending': pending,
            'approved': approved,
            'executed': executed,
        },
        'legacy_pending_files': legacy_pending_files,
    })


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Send a chat message to one or more agents on a shared conversation thread."""
    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    agent = (data.get('agent') or 'gemma').strip().lower()
    requested_agents = data.get('agents')
    requested_conv_id = data.get('conversation_id')
    force_new_thread = bool(data.get('new_thread'))
    history_mode = str(data.get('history_mode') or 'full').strip().lower()
    history_limit_raw = data.get('history_limit')

    if not message:
        return jsonify({'ok': False, 'response': 'Empty message'}), 400

    if history_mode not in {'full', 'recent', 'none'}:
        history_mode = 'full'

    try:
        history_limit = int(history_limit_raw) if history_limit_raw is not None else 8
    except Exception:
        history_limit = 8
    history_limit = max(1, min(30, history_limit))

    allowed_agents = {a['name'].lower() for a in _AGENT_ROSTER if a['name'].lower() != 'ghost'}

    if isinstance(requested_agents, list) and requested_agents:
        normalized_agents = []
        for item in requested_agents:
            name = str(item or '').strip().lower()
            if name and name not in normalized_agents:
                normalized_agents.append(name)
        if not normalized_agents:
            return jsonify({'ok': False, 'response': 'No agents selected'}), 400
    else:
        normalized_agents = [agent]

    bad_agents = [name for name in normalized_agents if name not in allowed_agents]
    if bad_agents:
        return jsonify({'ok': False, 'response': f"Unsupported agent(s): {', '.join(bad_agents)}"}), 400

    identity, err = _resolve_identity_or_response(data)
    if err:
        return err

    def _parse_chat_skill_command(text):
        raw = (text or '').strip()
        upper = raw.upper()
        if not raw:
            return None

        if upper in {'/SKILLS', 'SKILLS', '/SKILL', 'SKILL'}:
            return 'list', ''

        if upper.startswith('/SKILL '):
            payload = raw[7:].strip()
        elif upper.startswith('SKILL '):
            payload = raw[6:].strip()
        else:
            return None

        if not payload:
            return 'list', ''

        parts = payload.split(None, 1)
        skill_name = parts[0].strip().lower()
        skill_args = parts[1].strip() if len(parts) > 1 else ''
        return skill_name, skill_args

    def _is_execution_confirmation(text):
        raw = str(text or '').strip().lower()
        if not raw:
            return False
        confirmations = {
            'go ahead', 'yes', 'y', 'yep', 'yeah', 'continue', 'proceed', 'do it',
            'go for it', 'execute', 'run it', 'ship it'
        }
        if raw in confirmations:
            return True
        return bool(re.search(r'\b(go\s+ahead|continue|proceed|do\s+it|execute|run\s+it|ship\s+it|yes)\b', raw))

    def _derive_proposal_from_text(selected_agent, text, user_prompt):
        body = str(text or '').strip()
        if not body:
            return None

        if not re.search(r'proposal|draft|title|scope|description', body, re.IGNORECASE):
            return None

        title = ''
        desc = ''

        m_title = re.search(r'(?:\*\*\s*)?title(?:\s*\*\*)?\s*:\s*(.+)', body, re.IGNORECASE)
        if m_title:
            title = m_title.group(1).strip().strip('*').strip()

        m_desc = re.search(r'(?:\*\*\s*)?description(?:\s*\*\*)?\s*:\s*([\s\S]{20,1200})', body, re.IGNORECASE)
        if m_desc:
            desc = m_desc.group(1).strip()
            desc = re.split(r'\n\s*(?:---|##+\s+|\*\*\w)', desc, maxsplit=1)[0].strip()

        if not title:
            title = f'{selected_agent} proposal from chat confirmation'
        if not desc:
            desc = str(user_prompt or '').strip()[:600] or body[:600]

        if not title or not desc:
            return None

        return title[:180], desc[:1500]

    def _extract_skill_lines_from_text(text):
        from fridays.skills import parse_skill_command

        cmds = []
        for raw_line in str(text or '').splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed = None
            if line.upper().startswith('SKILL '):
                parsed = parse_skill_command(line)
            elif line.upper().startswith('/SKILL '):
                parsed = parse_skill_command('SKILL ' + line[7:].strip())
            if not parsed:
                continue
            skill_name, skill_args = parsed
            if skill_name == 'list':
                continue
            cmds.append((skill_name, skill_args))
        return cmds[:4]

    def _execute_agent_skill_lines(selected_agent, response_text, request_data):
        from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY

        # Restrict auto-execution to explicit proposal-creation actions.
        allowed_auto_skills = {'alm_create_proposal', 'ticket_create'}
        cmds = _extract_skill_lines_from_text(response_text)
        if not cmds:
            derived = _derive_proposal_from_text(selected_agent, response_text, message)
            if not derived:
                return ''
            title, desc = derived
            safe_title = str(title).replace('"', "'")
            safe_desc = str(desc).replace('"', "'")
            synthetic_args = f'"{safe_title}" "{safe_desc}"'
            ok, out = skill_call('alm_create_proposal', args=synthetic_args, agent=selected_agent)
            preview = str(out or '')[:3000]
            return f"[skill:alm_create_proposal] {'OK' if ok else 'FAILED'}\\n{preview}"

        lines = []
        for skill_name, skill_args in cmds:
            if skill_name not in allowed_auto_skills:
                lines.append(f'[skill:{skill_name}] SKIPPED\\nAuto-execution only allows proposal skills.')
                continue

            meta = SKILL_REGISTRY.get(skill_name)
            if not meta:
                lines.append(f'[skill:{skill_name}] FAILED\\nUnknown skill')
                continue

            if not can_user_invoke_skill(selected_agent, skill_name, default_allow=True):
                lines.append(f'[skill:{skill_name}] FAILED\\nNot authorized for user {selected_agent}')
                continue

            trust_level = int(meta.get('trust_level', 0) or 0)
            if trust_level >= 1 and skill_name not in {'ticket_create', 'alm_create_proposal'}:
                gate = _alm_gate_or_response(request_data, f'chat_skill_{skill_name}')
                if gate:
                    lines.append(f'[skill:{skill_name}] FAILED\\nALM gate blocked execution (approval required).')
                    continue

            ok, out = skill_call(skill_name, args=skill_args, agent=selected_agent)
            preview = str(out or '')[:3000]
            lines.append(f"[skill:{skill_name}] {'OK' if ok else 'FAILED'}\\n{preview}")

        return '\\n\\n'.join(lines)

    def _load_local_agent_memories(selected_agent, latest_message, topic_limit=4, recent_limit=2):
        query = str(latest_message or '').strip()[:160]
        collected = []
        seen_ids = set()

        for search_query, limit in ((query, topic_limit), ('', recent_limit)):
            try:
                rows = get_agent_memory(selected_agent, query=search_query, limit=limit) or []
            except Exception:
                rows = []
            for row in rows:
                row_id = row['id'] if 'id' in row.keys() else id(row)
                if row_id in seen_ids:
                    continue
                seen_ids.add(row_id)
                collected.append(row)
        return collected

    def _build_local_memory_block(selected_agent, latest_message):
        memories = _load_local_agent_memories(selected_agent, latest_message)
        if not memories:
            return ''

        lines = []
        for row in memories:
            tags = str(row['tags'] or '').strip()
            subject = str(row['subject'] or '').strip()[:120]
            content = str(row['content'] or '').strip().replace('\n', ' ')[:420]
            prefix = f'[{tags}] ' if tags else ''
            lines.append(f'- {prefix}{subject}: {content}')

        return (
            '\n\n=== Your recent memory ===\n'
            + '\n'.join(lines)
            + '\n=== End memory ===\n'
            + 'Use this for continuity and hand-off. Do not quote it verbatim unless asked.'
        )

    def _build_local_agent_prompt(selected_agent, threaded_prompt, latest_message, reply_context):
        memory_block = _build_local_memory_block(selected_agent, latest_message)
        handoff_block = _build_chat_handoff_block(selected_agent, reply_context)
        base_prompt = handoff_block + threaded_prompt + memory_block
        if selected_agent in {'duck', 'sniffles'}:
            return (
                '=== Audit mode ===\n'
                'Review the thread and latest user message. Focus on factual consistency, risk,'
                ' contradictions, and missing assumptions. Return concise findings only.\n\n'
                + base_prompt
            )
        return base_prompt

    def _persist_local_agent_memory(selected_agent, latest_message, response_text):
        answer = str(response_text or '').strip()
        if not answer:
            return

        lowered = answer.lower()
        if lowered.startswith(f'[{selected_agent}] acknowledged.'):
            return
        if 'taking longer than expected' in lowered:
            return
        if lowered.endswith('no response'):
            return

        content = (
            f'User asked: {str(latest_message or '').strip()[:400]}\n'
            f'You answered: {answer[:1600]}'
        )
        try:
            save_agent_memory(
                agent_name=selected_agent,
                subject=str(latest_message or '').strip()[:100] or f'{selected_agent} terminal chat',
                content=content,
                tags='chat,terminal-ui,shared-thread',
                importance=7,
                source='terminal_chat',
            )
        except Exception as exc:
            log_activity('terminal', 'chat_memory_persist_warning', f'{selected_agent}: {exc}')

    def _run_ghost_layer_chat(selected_agent, prompt, history, stage_cb=None):
        from claude_api import _load_api_key, CLAUDE_MODEL
        import anthropic
        from config import NINE_SYSTEM_PROMPT, TEN_SYSTEM_PROMPT
        from fridays.skills import parse_skill_command, call as skill_call

        def _emit_stage(text):
            if callable(stage_cb):
                try:
                    stage_cb(text, None)
                except Exception:
                    pass

        api_key = _load_api_key()
        if not api_key:
            return None, 0, 'ANTHROPIC_API_KEY not configured'

        base_system = NINE_SYSTEM_PROMPT if selected_agent == 'nine' else TEN_SYSTEM_PROMPT
        _emit_stage('loading ghost-layer memory')

        try:
            recent_memories = get_agent_memory(selected_agent, query='', limit=6)
            if recent_memories:
                mem_lines = []
                for row in recent_memories:
                    subj = str(row['subject'] or '').strip()[:120]
                    body = str(row['content'] or '').strip()[:400]
                    mem_lines.append(f'- [{subj}] {body}')
                memory_block = (
                    '\n\n=== Your recent memory (most important first) ===\n'
                    + '\n'.join(mem_lines)
                    + '\n=== End memory ===\n'
                    + 'Use this for continuity but do not narrate or repeat it verbatim.'
                )
                system_prompt = base_system.rstrip() + memory_block
            else:
                system_prompt = base_system
        except Exception:
            system_prompt = base_system

        client = anthropic.Anthropic(api_key=api_key)

        def _extract_skill_lines(text):
            cmds = []
            for raw_line in str(text or '').splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                parsed = None
                if line.upper().startswith('SKILL '):
                    parsed = parse_skill_command(line)
                elif line.upper().startswith('/SKILL '):
                    parsed = parse_skill_command('SKILL ' + line[7:].strip())
                if not parsed:
                    continue
                skill_name, skill_args = parsed
                if skill_name == 'list':
                    continue
                cmds.append((skill_name, skill_args))
            return cmds[:4]

        def _run_skill_lines(cmds):
            def _route_shell_to_fs_readonly(shell_args):
                cmd = (shell_args or '').strip()
                if not cmd:
                    return None

                match = re.match(r'^ls(?:\s+-[a-zA-Z]+)?\s+(.+)$', cmd)
                if match:
                    return f'ls {match.group(1).strip()}'

                match = re.match(r'^cat\s+(.+)$', cmd)
                if match:
                    return f'read {match.group(1).strip()} 5000'

                match = re.match(r'^head\s+-n\s+(\d+)\s+(.+)$', cmd)
                if match:
                    return f'head {match.group(2).strip()} {match.group(1)}'

                match = re.match(r'^tail\s+-n\s+(\d+)\s+(.+)$', cmd)
                if match:
                    return f'tail {match.group(2).strip()} {match.group(1)}'

                return None

            lines = []
            for skill_name, skill_args in cmds:
                _emit_stage(f'executing skill: {skill_name}')
                effective_name = skill_name
                effective_args = skill_args
                if skill_name == 'shell':
                    mapped = _route_shell_to_fs_readonly(skill_args)
                    if mapped:
                        effective_name = 'fs_readonly'
                        effective_args = mapped

                if not can_user_invoke_skill(selected_agent, effective_name, default_allow=True):
                    lines.append(f'[skill:{effective_name}] FAILED\\nNot authorized for user {selected_agent}')
                    continue
                ok, out = skill_call(effective_name, args=effective_args, agent=selected_agent)
                preview = str(out or '')[:3000]
                lines.append(f"[skill:{effective_name}] {'OK' if ok else 'FAILED'}\\n{preview}")
            return '\\n\\n'.join(lines)

        _emit_stage('sending model request')
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=(history[-10:] if history else []) + [{'role': 'user', 'content': prompt}],
        )
        first_answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        answer = first_answer
        skill_cmds = _extract_skill_lines(first_answer)
        if skill_cmds:
            _emit_stage('running requested skills')
            skill_results = _run_skill_lines(skill_cmds)
            followup_messages = (history[-10:] if history else []) + [
                {'role': 'user', 'content': prompt},
                {'role': 'assistant', 'content': first_answer},
                {
                    'role': 'user',
                    'content': (
                        'Executed skill outputs are below. Use these concrete results to produce your final answer. '
                        'Do not ask to run the same commands again in this response.\\n\\n'
                        + skill_results
                    ),
                },
            ]
            _emit_stage('synthesizing final answer')
            second = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=followup_messages,
            )
            answer = second.content[0].text + '\\n\\n---\\nExecuted skill output:\\n' + skill_results
            tokens += second.usage.input_tokens + second.usage.output_tokens

        _emit_stage('persisting response memory')
        save_agent_memory(
            agent_name=selected_agent,
            subject=message[:100],
            content=answer,
            tags='chat,shared-thread',
            importance=7,
            source='terminal_chat'
        )
        log_activity('terminal', f'{selected_agent}_chat', f'tokens={tokens} | {message[:80]}')
        return answer, tokens, None

    def _run_single_agent(selected_agent, prompt, history, reply_context, persistent_mode=False, stage_cb=None):
        def _duck_fast_check(text):
            t = (text or '').strip()
            if not t:
                return 'Sanity check: no claim provided.'
            cues = []
            if '?' in t:
                cues.append('contains a question; verify assumptions before acting')
            if any(k in t.lower() for k in ['always', 'never', 'guaranteed', 'impossible']):
                cues.append('absolute wording detected; high risk of overclaim')
            if any(k in t.lower() for k in ['maybe', 'probably', 'i think']):
                cues.append('uncertainty markers found; ask for evidence')
            if not cues:
                cues.append('no obvious red flags; still verify with one independent source')
            return 'Duck quick sanity: ' + '; '.join(cues) + '.'

        def _stage(text, eta_seconds=None):
            if callable(stage_cb):
                try:
                    stage_cb(text, eta_seconds)
                except Exception:
                    pass

        response_text = None
        tokens_used = 0
        started_at = time.time()
        executor = ThreadPoolExecutor(max_workers=1)
        est_eta = _chat_eta_seconds(selected_agent)
        effective_prompt = _build_local_agent_prompt(selected_agent, prompt, message, reply_context)
        if _is_execution_confirmation(message):
            effective_prompt = (
                effective_prompt
                + '\n\n=== EXECUTION CONFIRMATION ===\n'
                + 'User explicitly approved execution. If your next step is to create a work proposal, '
                + 'output exactly one executable command line in this format and then brief context:\n'
                + 'SKILL alm_create_proposal "<title>" "<description>"\n'
                + 'Do not ask for reconfirmation.'
            )
        _stage('queued', est_eta)
        local_timeout = 12
        if selected_agent == 'sniffles':
            local_timeout = 35
        elif selected_agent == 'duck':
            local_timeout = 18
        if persistent_mode:
            if selected_agent in {'gemma', 'llama', 'qwen', 'librarian', 'duck', 'sniffles'}:
                local_timeout = 900
            else:
                local_timeout = 240
        try:
            if selected_agent in {'gemma', 'llama', 'qwen', 'eight', 'librarian', 'duck', 'sniffles'}:
                _stage('loading local memory', est_eta)
                if selected_agent in {'duck', 'sniffles'}:
                    _stage('assembling audit context', est_eta)
                else:
                    _stage('processing thread hand-off', est_eta)
                future = executor.submit(orchestrator.ask_agent, selected_agent, effective_prompt)
                _stage('running local inference', est_eta)
                response_text = future.result(timeout=local_timeout)
                _stage('storing agent memory', 0)
                _persist_local_agent_memory(selected_agent, message, response_text)
            elif selected_agent == 'nine':
                _stage('dispatching to ghost datacenter', est_eta)
                future = executor.submit(_run_ghost_layer_chat, selected_agent, effective_prompt, history, stage_cb)
                answer, tokens, api_err = future.result(timeout=240 if persistent_mode else 20)
                if api_err:
                    raise RuntimeError(api_err)
                response_text = answer
                tokens_used = tokens
            elif selected_agent == 'ten':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.ten import copilot_agent
                future = executor.submit(copilot_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[ten] No response — check server logs.'
                tokens_used = tokens or 0
            elif selected_agent == 'eleven':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.eleven import grok_agent
                future = executor.submit(grok_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[eleven unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'twelve':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.twelve import twelve_agent
                future = executor.submit(twelve_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[twelve unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'scholar':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.scholar import scholar_agent
                future = executor.submit(scholar_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[scholar unavailable]'
                tokens_used = tokens or 0
            elif selected_agent == 'seeker':
                _stage('dispatching to ghost datacenter', est_eta)
                from agents.seeker import seeker_agent
                future = executor.submit(seeker_agent.chat, effective_prompt, history, stage_cb)
                answer, tokens = future.result(timeout=240 if persistent_mode else 20)
                response_text = answer or '[seeker unavailable]'
                tokens_used = tokens or 0
            _stage('finalizing answer', 0)
        except FuturesTimeoutError:
            _stage('timed out waiting for completion', 0)
            if persistent_mode:
                raise RuntimeError(f'{selected_agent} timed out after {local_timeout}s')
            if selected_agent == 'duck':
                response_text = _duck_fast_check(message)
            elif selected_agent in {'gemma', 'llama', 'qwen', 'librarian'}:
                raise
            else:
                response_text = (
                    f'[{selected_agent}] is taking longer than expected. '
                    'Try again in a moment or switch to another agent.'
                )
        finally:
            executor.shutdown(wait=False)

        if response_text is None:
            response_text = f'[{selected_agent}] no response'

        elapsed_ms = int((time.time() - started_at) * 1000)
        return response_text, tokens_used, elapsed_ms

    try:
        conv_id = None
        if requested_conv_id is not None:
            try:
                parsed = int(requested_conv_id)
                conn = get_connection()
                try:
                    exists = conn.execute('SELECT 1 FROM conversations WHERE id=?', (parsed,)).fetchone()
                finally:
                    conn.close()
                if exists:
                    conv_id = parsed
            except Exception:
                conv_id = None

        if conv_id is None and not force_new_thread:
            conn = get_connection()
            try:
                latest = conn.execute(
                    "SELECT id FROM conversations WHERE source='terminal-ui' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if latest:
                conv_id = int(latest['id'])

        if conv_id is None:
            title_agents = ','.join(normalized_agents[:2])
            conv_id = new_conversation(f'{title_agents}: {message[:90]}', source='terminal-ui')

        to_agent = normalized_agents[0] if len(normalized_agents) == 1 else ','.join(normalized_agents)
        log_message(conv_id, 'user', message, to_agent=to_agent, message_type='chat')

        parsed_skill = _parse_chat_skill_command(message)
        if parsed_skill:
            from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY

            skill_name, skill_args = parsed_skill
            meta = SKILL_REGISTRY.get(skill_name)

            if not meta:
                known = ', '.join(sorted(SKILL_REGISTRY.keys()))
                skill_ok = False
                skill_output = f"Unknown skill: {skill_name!r}. Known skills: {known}"
            else:
                effective_user = identity['effective_user']
                if not can_user_invoke_skill(effective_user, skill_name, default_allow=True):
                    return jsonify({
                        'ok': False,
                        'error': f'user {effective_user} is not authorized for skill {skill_name}'
                    }), 403
                trust_level = int(meta.get('trust_level', 0) or 0)
                if trust_level >= 1 and skill_name not in {'ticket_create', 'alm_create_proposal'}:
                    gate = _alm_gate_or_response(data, f'chat_skill_{skill_name}')
                    if gate:
                        return gate
                caller_agent = effective_user
                skill_ok, skill_output = skill_call(skill_name, args=skill_args, agent=caller_agent)

            skill_response = (
                f"[skill:{skill_name}] {'OK' if skill_ok else 'FAILED'}\n"
                f'{skill_output}'
            )
            log_message(conv_id, 'fridays', skill_response, to_agent='user', message_type='response')

            return jsonify({
                'ok': True,
                'mode': 'skill',
                'skill': {
                    'name': skill_name,
                    'args': skill_args,
                    'ok': skill_ok,
                },
                'identity': {
                    'acting_user': identity['acting_user'],
                    'proxy_as': identity['proxy_as'],
                    'effective_user': identity['effective_user'],
                },
                'agent': 'fridays',
                'response': skill_response,
                'tokens': 0,
                'responses': [{
                    'agent': 'fridays',
                    'response': skill_response,
                    'tokens': 0,
                    'elapsed_ms': 0,
                }],
                'agents': normalized_agents,
                'conversation_id': conv_id,
            })

        if history_mode == 'none':
            thread_rows = []
        elif history_mode == 'recent':
            thread_rows = _fetch_chat_thread_rows(conv_id, limit=history_limit)
        else:
            thread_rows = _fetch_chat_thread_rows(conv_id, limit=60)
        history = _chat_history_from_rows(thread_rows)
        transcript = _thread_transcript_from_rows(thread_rows[-12:])
        reply_contexts = {
            selected_agent: _conversation_reply_context_from_rows(thread_rows, selected_agent)
            for selected_agent in normalized_agents
        }
        threaded_prompt = (
            '=== Shared conversation thread (latest) ===\n'
            f"{transcript or 'No previous messages.'}\n\n"
            '=== New user message ===\n'
            f'{message}'
        )

        responses_map = {}
        pending_jobs = []
        deferred_agents = set()
        runnable_agents = list(normalized_agents)
        if 'sniffles' in runnable_agents and len(runnable_agents) > 1:
            runnable_agents = [a for a in runnable_agents if a != 'sniffles']
            deferred_agents.add('sniffles')

        def _register_persistent_job(selected_agent, future, reply_context, job_ref=None):
            job_id = f'chatjob-{uuid.uuid4().hex[:12]}'
            started_ts = time.time()
            now_iso = _chat_now_iso()
            eta_seconds = _chat_eta_seconds(selected_agent)
            with _CHAT_JOB_LOCK:
                _cleanup_chat_jobs_locked()
                _CHAT_JOBS[job_id] = {
                    'job_id': job_id,
                    'conversation_id': conv_id,
                    'agent': selected_agent,
                    'status': 'running',
                    'runtime_class': _chat_runtime_class(selected_agent),
                    'stage': _chat_stage_for(selected_agent, 0),
                    'eta_seconds': eta_seconds,
                    'started_ts': started_ts,
                    'updated_ts': started_ts,
                    'started_at': now_iso,
                    'updated_at': now_iso,
                    'future': future,
                    'cancel_requested': False,
                }
            if isinstance(job_ref, dict):
                job_ref['job_id'] = job_id

            def _finish_job(done_future):
                updated_ts = time.time()
                updated_iso = _chat_now_iso()
                try:
                    response_text, tokens_used, elapsed_ms = done_future.result()
                    if selected_agent in {'nine', 'ten', 'eleven', 'twelve'} and _is_execution_confirmation(message):
                        try:
                            skill_output = _execute_agent_skill_lines(selected_agent, response_text, data)
                            if skill_output:
                                response_text = f"{response_text}\n\n---\nAuto-executed skill output:\n{skill_output}"
                        except Exception as skill_exc:
                            response_text = (
                                f"{response_text}\n\n---\n"
                                f"Auto-executed skill output:\n[skill:auto] FAILED\\n{skill_exc}"
                            )
                    with _CHAT_JOB_LOCK:
                        existing = _CHAT_JOBS.get(job_id)
                        cancelled = bool(existing and existing.get('status') == 'cancelled')
                    if cancelled:
                        return
                    response_target = _resolve_chat_reply_target(selected_agent, response_text, reply_context)
                    log_message(
                        conv_id,
                        selected_agent,
                        response_text,
                        to_agent=response_target,
                        message_type='response',
                        tokens_used=int(tokens_used or 0),
                    )
                    with _CHAT_JOB_LOCK:
                        job = _CHAT_JOBS.get(job_id)
                        if job and job.get('status') != 'cancelled':
                            job.update({
                                'status': 'completed',
                                'stage': 'completed',
                                'eta_seconds': 0,
                                'updated_ts': updated_ts,
                                'updated_at': updated_iso,
                                'elapsed_ms': int(elapsed_ms or 0),
                                'tokens': int(tokens_used or 0),
                            })
                except Exception as exc:
                    err_text = str(exc or '').strip() or exc.__class__.__name__
                    with _CHAT_JOB_LOCK:
                        existing = _CHAT_JOBS.get(job_id)
                        cancelled = bool(existing and existing.get('status') == 'cancelled')
                    if cancelled:
                        return
                    fail_msg = f'[{selected_agent}] background run failed: {err_text}'
                    try:
                        response_target = _resolve_chat_reply_target(selected_agent, fail_msg, reply_context)
                        log_message(
                            conv_id,
                            selected_agent,
                            fail_msg,
                            to_agent=response_target,
                            message_type='response',
                            tokens_used=0,
                        )
                    except Exception:
                        pass
                    with _CHAT_JOB_LOCK:
                        job = _CHAT_JOBS.get(job_id)
                        if job and job.get('status') != 'cancelled':
                            job.update({
                                'status': 'failed',
                                'stage': 'failed',
                                'eta_seconds': 0,
                                'error': err_text,
                                'updated_ts': updated_ts,
                                'updated_at': updated_iso,
                            })

            future.add_done_callback(_finish_job)
            return job_id

        debate_turn = []

        def _agent_label(agent_key):
            key = str(agent_key or '').strip().lower()
            labels = {
                'gemma': 'Gemma',
                'llama': 'LLaMA',
                'qwen': 'Qwen',
                'eight': 'Eight',
                'librarian': 'Librarian',
                'duck': 'Duck',
                'sniffles': 'Sniffles',
                'nine': 'Nine',
                'ten': 'Ten',
                'eleven': 'Eleven',
                'twelve': 'Twelve',
            }
            return labels.get(key, key or 'Agent')

        def _build_debate_prompt(selected_agent):
            if len(runnable_agents) <= 1:
                return threaded_prompt

            active_labels = [_agent_label(a) for a in runnable_agents]
            if debate_turn:
                turn_lines = '\n'.join(
                    f"{_agent_label(item['agent'])}: {str(item['response'])[:800]}"
                    for item in debate_turn
                )
            else:
                turn_lines = 'No peer responses yet in this turn.'

            return (
                threaded_prompt
                + '\n\n=== Multi-Agent Debate Mode (Current Turn) ===\n'
                + f"You are {_agent_label(selected_agent)}.\n"
                + f"ACTIVE AGENTS IN THIS CHAT: {', '.join(active_labels)}.\n"
                + 'RULES: Only address agents from the list above. Do NOT mention, ask, or direct questions to '
                + 'any agent, person, or entity not in ACTIVE AGENTS. Do NOT ask Ghost to respond — '
                + 'Ghost has already sent their message above.\n'
                + 'Read the peer responses below and reply to them where useful. '
                + 'When another active agent already covered a point, extend or challenge it instead of restating it. '
                + 'If you agree or disagree, name the agent and explain in 1-2 lines. '
                + 'Then give your own answer.\n\n'
                + 'Peer responses so far this turn:\n'
                + turn_lines
            )

        for selected_agent in runnable_agents:
            job_ref = {'job_id': None}

            def _stage_cb(stage_text, eta_seconds=None, _job_ref=job_ref):
                job_id = _job_ref.get('job_id')
                if not job_id:
                    return
                _chat_update_job(job_id, stage=stage_text, eta_seconds=eta_seconds)

            agent_prompt = _build_debate_prompt(selected_agent)
            single_executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = single_executor.submit(
                    _run_single_agent,
                    selected_agent,
                    agent_prompt,
                    history,
                    reply_contexts[selected_agent],
                    True,
                    _stage_cb,
                )
                try:
                    wait_timeout = 20 if selected_agent == 'sniffles' else 10
                    response_text, tokens_used, elapsed_ms = future.result(timeout=wait_timeout)
                    pending = False
                    pending_job_id = None
                except FuturesTimeoutError:
                    pending_job_id = _register_persistent_job(selected_agent, future, reply_contexts[selected_agent], job_ref)
                    pending_jobs.append(pending_job_id)
                    pending = True
                    eta_seconds = _chat_eta_seconds(selected_agent)
                    response_text, tokens_used = (
                        f'[{selected_agent}] acknowledged. Running now. ETA ~{eta_seconds}s; monitor shows live stage.',
                        0,
                    )
                    elapsed_ms = int(wait_timeout * 1000)
                except Exception as exc:
                    response_text, tokens_used = (f'[{selected_agent}] error: {str(exc)}', 0)
                    elapsed_ms = 0
                    pending = False
                    pending_job_id = None
            finally:
                single_executor.shutdown(wait=False, cancel_futures=False)

            responses_map[selected_agent] = {
                'agent': selected_agent,
                'response': response_text,
                'tokens': tokens_used,
                'elapsed_ms': elapsed_ms,
                'runtime_class': _chat_runtime_class(selected_agent),
                'eta_seconds': _chat_eta_seconds(selected_agent) if pending else 0,
                'pending': pending,
                'job_id': pending_job_id,
            }

            if (not pending) and selected_agent in {'nine', 'ten', 'eleven', 'twelve'} and _is_execution_confirmation(message):
                skill_output = _execute_agent_skill_lines(selected_agent, response_text, data)
                if skill_output:
                    responses_map[selected_agent]['response'] = (
                        f"{response_text}\n\n---\nAuto-executed skill output:\n{skill_output}"
                    )

            debate_turn.append({'agent': selected_agent, 'response': response_text})

        for agent_name in deferred_agents:
            responses_map[agent_name] = {
                'agent': agent_name,
                'response': (
                    '[sniffles] deferred: heavyweight auditor runs on-demand. '
                    'Send to sniffles alone for a full audit.'
                ),
                'tokens': 0,
                'elapsed_ms': 0,
                'runtime_class': _chat_runtime_class(agent_name),
                'eta_seconds': 0,
                'pending': False,
                'job_id': None,
            }

        responses = [responses_map[a] for a in normalized_agents if a in responses_map]
        total_tokens = sum(int(r.get('tokens') or 0) for r in responses)
        for entry in responses:
            if entry.get('pending'):
                continue
            response_target = _resolve_chat_reply_target(entry['agent'], entry['response'], reply_contexts[entry['agent']])
            log_message(
                conv_id,
                entry['agent'],
                entry['response'],
                to_agent=response_target,
                message_type='response',
                tokens_used=int(entry.get('tokens') or 0),
            )

        primary = responses[0] if responses else {'agent': normalized_agents[0], 'response': '', 'tokens': 0}

        return jsonify({
            'ok': True,
            'agent': primary['agent'],
            'response': primary['response'],
            'tokens': total_tokens,
            'responses': responses,
            'pending_jobs': pending_jobs,
            'agents': normalized_agents,
            'history_mode': history_mode,
            'history_limit': history_limit if history_mode == 'recent' else None,
            'conversation_id': conv_id,
        })
    except Exception as exc:
        return jsonify({'ok': False, 'response': f'Error: {str(exc)}'}), 500


@app.route('/api/chat/jobs/status')
def api_chat_jobs_status():
    """Poll status for long-running chat jobs.

    Query params:
    - conversation_id (optional)
    - job_ids (optional comma-separated list)
    """
    conv_id = request.args.get('conversation_id')
    raw_job_ids = (request.args.get('job_ids') or '').strip()
    want_ids = {x.strip() for x in raw_job_ids.split(',') if x.strip()} if raw_job_ids else set()

    conv_id_int = None
    if conv_id:
        try:
            conv_id_int = int(conv_id)
        except Exception:
            conv_id_int = None

    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        jobs = []
        for job in _CHAT_JOBS.values():
            if conv_id_int is not None and int(job.get('conversation_id') or -1) != conv_id_int:
                continue
            if want_ids and job.get('job_id') not in want_ids:
                continue
            jobs.append(_chat_job_public(job))

    jobs.sort(key=lambda j: (j.get('status') != 'running', j.get('agent') or ''))
    return jsonify({'ok': True, 'jobs': jobs})


@app.route('/api/chat/jobs/cancel', methods=['POST'])
def api_chat_jobs_cancel():
    """Best-effort cancellation for long-running chat jobs.

    Body:
    - job_ids: array of job IDs or comma-separated string (optional)
    - conversation_id: optional, cancel all running jobs in conversation when job_ids omitted
    """
    data = request.get_json() or {}
    raw_ids = data.get('job_ids') or []
    if isinstance(raw_ids, str):
        raw_ids = [x.strip() for x in raw_ids.split(',') if x.strip()]
    want_ids = {str(x).strip() for x in raw_ids if str(x).strip()}

    conv_id = data.get('conversation_id')
    conv_id_int = None
    if conv_id is not None and str(conv_id).strip() != '':
        try:
            conv_id_int = int(conv_id)
        except Exception:
            return jsonify({'ok': False, 'error': 'conversation_id must be int'}), 400

    cancelled = []
    skipped = []
    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        for job_id, job in list(_CHAT_JOBS.items()):
            if want_ids and job_id not in want_ids:
                continue
            if conv_id_int is not None and int(job.get('conversation_id') or -1) != conv_id_int:
                continue

            status = str(job.get('status') or 'running')
            if status in {'completed', 'failed', 'cancelled'}:
                skipped.append({'job_id': job_id, 'reason': f'already {status}'})
                continue

            fut = job.get('future')
            cancel_signal_sent = False
            if fut is not None:
                try:
                    cancel_signal_sent = bool(fut.cancel())
                except Exception:
                    cancel_signal_sent = False

            now_ts = time.time()
            now_iso = _chat_now_iso()
            job.update({
                'status': 'cancelled',
                'stage': 'cancelled by user',
                'eta_seconds': 0,
                'error': 'cancelled by user',
                'cancel_requested': True,
                'updated_ts': now_ts,
                'updated_at': now_iso,
            })
            cancelled.append({'job_id': job_id, 'agent': job.get('agent'), 'cancel_signal_sent': cancel_signal_sent})

    for item in cancelled:
        log_activity('terminal', 'chat_job_cancelled', f"job_id={item['job_id']} agent={item.get('agent')}")

    return jsonify({'ok': True, 'cancelled': cancelled, 'skipped': skipped, 'count': len(cancelled)})


@app.route('/api/activity')
def api_activity():
    from database import get_activity_log
    since = int(request.args.get('since', 0))
    limit = int(request.args.get('limit', 100))
    logs = get_activity_log(limit=limit, since_id=since)
    
    # Format for frontend
    activities = []
    for log in logs:
        activities.append({
            'timestamp': log.get('created_at', '—')[:16],
            'message': f"{log.get('service', 'System')}: {log.get('event', '')} {log.get('detail', '')}".strip(),
            'level': 'info',  # Could be enhanced based on event type
        })
    
    return jsonify({'activities': activities})


@app.route('/api/activity/stream')
def api_activity_stream():
    """SSE stream — sends new activity_log entries as they arrive."""
    from database import get_activity_log
    import time

    def generate():
        since_id = 0
        # Send last 20 entries on connect so the feed isn't empty
        rows = get_activity_log(limit=20)
        rows.reverse()
        for row in rows:
            yield f"data: {__import__('json').dumps(row)}\n\n"
            since_id = max(since_id, row['id'])

        while True:
            time.sleep(2)
            new_rows = get_activity_log(limit=50, since_id=since_id)
            new_rows.reverse()
            for row in new_rows:
                yield f"data: {__import__('json').dumps(row)}\n\n"
                since_id = max(since_id, row['id'])

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


_AGENT_ROSTER = [
    {'name': 'Gemma',     'model': 'gemma3:latest',          'role': 'Director',                    'default_temp': 0.3},
    {'name': 'LLaMA',     'model': 'llama3.2:latest',        'role': 'Researcher',                  'default_temp': 0.6},
    {'name': 'Qwen',      'model': 'qwen2.5:latest',         'role': 'Analyst',                     'default_temp': 0.7},
    {'name': 'Librarian', 'model': 'qwen:latest',            'role': 'Archivist',                   'default_temp': 0.1},
    {'name': 'Duck',      'model': 'qwen:latest',            'role': 'Checker',                     'default_temp': 0.1},
    {'name': 'Sniffles',  'model': 'deepseek-r1:7b',         'role': 'Auditor',                     'default_temp': 0.1},
    {'name': 'Eight',     'model': 'qwen2.5:latest',         'role': 'SAP Specialist',              'default_temp': 0.7},
    {'name': 'Nine',      'model': 'claude-sonnet-4-6',      'role': 'System Architect · Ghost Layer', 'default_temp': None, 'no_temp': True,  'ghost_layer': True},
    {'name': 'Ten',       'model': 'gpt-5.3-codex',          'role': 'Software Engineering Advisor · Copilot · Ghost Layer', 'default_temp': 0.4, 'ghost_layer': True},
    {'name': 'Eleven',    'model': 'grok-api',               'role': 'Reasoning Advisor · Ghost Layer', 'default_temp': None, 'no_temp': True, 'ghost_layer': True},
    {'name': 'Twelve',    'model': 'claude-haiku',           'role': 'Vortex · Ghost Layer',        'default_temp': 0.3, 'ghost_layer': True},
    {'name': 'Scholar',   'model': 'gemini-2.0-flash',       'role': 'Vision & Reasoning · Ghost Layer', 'default_temp': 0.4, 'ghost_layer': True},
    {'name': 'Seeker',    'model': 'tavily-search',          'role': 'Real-Time Intelligence · Ghost Layer', 'default_temp': 0.5, 'ghost_layer': True},
    {'name': 'Ghost',     'model': '(human operator)',        'role': 'Operator · Ghost Layer',      'default_temp': None, 'no_temp': True,  'ghost_layer': True, 'no_toggle': True},
]


def _agent_reachability_status(agent_name):
    """Return 'online', 'degraded', or 'offline' based on real API key / service availability."""
    name = (agent_name or '').strip().lower()
    if name in DISABLED_AGENTS:
        return 'offline'
    # Local Ollama agents — assume online if not disabled
    if name in {'gemma', 'llama', 'qwen', 'librarian', 'duck', 'sniffles', 'eight'}:
        return 'online'
    # Ghost operator — always online
    if name == 'ghost':
        return 'online'
    # Ghost Layer API-backed agents — check key presence
    try:
        from config import (
            GITHUB_TOKEN, XAI_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY,
        )
        from claude_api import _load_api_key
        anthropic_key = _load_api_key()
    except Exception:
        return 'unknown'
    key_map = {
        'nine':    anthropic_key,
        'twelve':  anthropic_key,
        'ten':     GITHUB_TOKEN,
        'eleven':  XAI_API_KEY,
        'scholar': GEMINI_API_KEY,
        'seeker':  TAVILY_API_KEY,
    }
    key = key_map.get(name)
    if key is None:
        return 'online'  # unknown agent, assume online
    return 'online' if key else 'offline'


@app.route('/api/agents')
def api_agents():
    result = []
    for a in _AGENT_ROSTER:
        entry = dict(a)
        entry['enabled']     = a['name'] not in DISABLED_AGENTS
        entry['temperature'] = orchestrator.TEMPERATURES.get(a['name'], a['default_temp'])
        entry['status']      = _agent_reachability_status(a['name'])
        entry['ghost_layer'] = a.get('ghost_layer', False)
        result.append(entry)
    return jsonify(result)


@app.route('/api/agents/capability-matrix')
def api_agents_capability_matrix():
    """Read-only matrix of granted capabilities per agent for governance UI."""
    include_inactive = request.args.get('include_inactive', '0') == '1'
    try:
        from database import get_agent_capabilities, AGENT_CAPABILITY_REGISTRY

        roster_agents = sorted({str(a.get('name', '')).strip().lower() for a in _AGENT_ROSTER if a.get('name')})
        if include_inactive:
            extras = {'fridays', 'ghost'}
            roster_agents = sorted(set(roster_agents) | extras)

        matrix = []
        for agent_name in roster_agents:
            caps = get_agent_capabilities(agent_name)
            granted = []
            for cap in caps:
                if not bool(cap.get('granted')):
                    continue
                cname = str(cap.get('capability') or '').strip().lower()
                meta = AGENT_CAPABILITY_REGISTRY.get(cname, {})
                granted.append({
                    'capability': cname,
                    'description': meta.get('desc', ''),
                    'trust_level': int(cap.get('trust_level') or meta.get('trust', 0) or 0),
                    'granted_by': cap.get('granted_by', ''),
                    'granted_at': cap.get('granted_at', ''),
                })

            granted.sort(key=lambda item: (item.get('trust_level', 0), item.get('capability', '')))
            matrix.append({
                'agent': agent_name,
                'granted_count': len(granted),
                'capabilities': granted,
            })

        return jsonify({'ok': True, 'agents': matrix})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.route('/api/agents/capabilities', methods=['POST'])
def api_agents_capabilities_update():
    """Grant or revoke one or more capabilities for a target agent."""
    data = request.get_json() or {}
    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    if identity['effective_user'] != 'ghost':
        return jsonify({'ok': False, 'error': 'only ghost can update agent capabilities'}), 403

    target_agent = str(data.get('agent') or '').strip().lower()
    if not target_agent:
        return jsonify({'ok': False, 'error': 'agent required'}), 400

    known_agents = {str(a.get('name') or '').strip().lower() for a in _AGENT_ROSTER if a.get('name')}
    if target_agent not in known_agents:
        return jsonify({'ok': False, 'error': f'unknown agent: {target_agent}'}), 404

    raw_caps = data.get('capabilities', data.get('capability', []))
    if isinstance(raw_caps, str):
        raw_caps = [raw_caps]
    capabilities = []
    for cap in (raw_caps or []):
        cname = str(cap or '').strip().lower()
        if cname and cname not in capabilities:
            capabilities.append(cname)
    if not capabilities:
        return jsonify({'ok': False, 'error': 'capability or capabilities required'}), 400

    invalid = [c for c in capabilities if c not in AGENT_CAPABILITY_REGISTRY]
    if invalid:
        return jsonify({'ok': False, 'error': f'unknown capabilities: {", ".join(invalid)}'}), 400

    enabled = bool(data.get('enabled', True))
    proposal_id = str(data.get('proposal_id') or '').strip()
    notes = str(data.get('notes') or '').strip()
    granted_by = str(identity.get('effective_user') or 'ghost').strip().lower() or 'ghost'

    changed = []
    for cap in capabilities:
        if enabled:
            grant_agent_capability(
                target_agent,
                cap,
                granted_by=granted_by,
                proposal_id=proposal_id,
                notes=notes,
            )
        else:
            revoke_agent_capability(target_agent, cap)
        changed.append({'capability': cap, 'enabled': enabled})

    granted_rows = [
        row for row in get_agent_capabilities(target_agent)
        if bool(row.get('granted'))
    ]
    granted_rows.sort(key=lambda item: (int(item.get('trust_level') or 0), str(item.get('capability') or '')))

    action_label = 'grant' if enabled else 'revoke'
    log_activity(
        'terminal',
        'agent_capabilities_updated',
        f'{target_agent}:{action_label}:{",".join(capabilities)} by {granted_by}'
    )

    return jsonify({
        'ok': True,
        'agent': target_agent,
        'changed': changed,
        'granted_count': len(granted_rows),
        'capabilities': granted_rows,
    })


@app.route('/api/agents/<name>/toggle', methods=['POST'])
def toggle_agent(name):
    if name in DISABLED_AGENTS:
        DISABLED_AGENTS.discard(name)
        enabled = True
    else:
        DISABLED_AGENTS.add(name)
        enabled = False
    print(f'[Terminal] {name} {"enabled" if enabled else "disabled"}')
    return jsonify({'name': name, 'enabled': enabled})


@app.route('/api/agents/<name>/temperature', methods=['POST'])
def set_agent_temperature(name):
    data = request.get_json() or {}
    try:
        temp = float(data.get('temperature', 0.5))
        temp = round(max(0.0, min(1.0, temp)), 2)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid temperature'}), 400
    orchestrator.TEMPERATURES[name] = temp
    print(f'[Terminal] {name} temperature → {temp}')
    return jsonify({'name': name, 'temperature': temp})


@app.route('/chat', methods=['POST'])
def chat():
    data     = request.get_json() or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'empty question'}), 400

    # Librarian intake — queue entry created, same as email path
    queue_id, queue_position, tags = queue_intake('ghost@terminal', 'Terminal', question)

    # Create conversation + ticket — Duck will run inside librarian_close
    conv_id       = new_conversation(question, source='terminal', sender='ghost')
    ticket_number = f'TICKET-{conv_id}'
    ticket_create(ticket_number, 'ghost@terminal', question, tags=tags, queue_id=queue_id)
    log_message(conv_id, 'Ghost', question, to_agent='Gemma', message_type='chat')

    # Event queue for this ticket's SSE stream
    q = queue.Queue()
    _streams[ticket_number] = q

    def run_pipeline():
        try:
            q.put({'type': 'status', 'text': 'Gemma reading the question...'})
            mark_processing(queue_id)
            web, llama, ctx, routing = orchestrator.consult_stage1(question)
            q.put({'type': 'routing', 'routing': routing})
            # Save routing to ticket so Tickets view shows it
            _conn = get_connection()
            _conn.execute(
                "UPDATE tickets SET gemma_routing=? WHERE ticket_number=?",
                (json.dumps(routing), ticket_number)
            )
            _conn.commit()
            _conn.close()

            if routing.get('is_sap'):
                # ── Eight pipeline ────────────────────────────────────────────
                q.put({'type': 'status', 'text': 'Eight engaged — SAP specialist deliberating...'})
                def eight_status(msg):
                    q.put({'type': 'status', 'text': msg})
                result = orchestrator.consult_stage_eight(
                    question, web, ctx, conv_id, status_cb=eight_status
                )
                q.put({'type': 'eight_voice', 'voice': 'Functional', 'text': result['functional']})
                q.put({'type': 'eight_voice', 'voice': 'Technical',  'text': result['technical']})
                q.put({'type': 'eight_voice', 'voice': 'Devil',      'text': result['devil']})
                q.put({'type': 'agent', 'agent': 'Gemma', 'text': result['gemma_verdict']})
                final_answer = result['gemma_verdict']
            else:
                # ── Standard pipeline ─────────────────────────────────────────
                q.put({'type': 'agent', 'agent': 'LLaMA', 'text': llama})

                q.put({'type': 'status', 'text': 'Qwen analysing...'})
                qwen, gemma, debate = orchestrator.consult_stage2(
                    question, web, llama, ctx, conv_id, routing
                )
                q.put({'type': 'agent', 'agent': 'Qwen', 'text': qwen})

                if debate['fired']:
                    q.put({'type': 'status', 'text': 'Debate detected — running challenge round...'})
                    q.put({'type': 'debate_r2', 'agent': 'LLaMA', 'text': debate['llama_r2']})
                    q.put({'type': 'debate_r2', 'agent': 'Qwen',  'text': debate['qwen_r2']})

                q.put({'type': 'agent', 'agent': 'Gemma', 'text': gemma})
                final_answer = gemma

            q.put({'type': 'status', 'text': 'Duck checking...'})
            librarian_close(ticket_number, question, final_answer,
                            queue_id=queue_id, sender_email='ghost@terminal')

            q.put({'type': 'done', 'ticket': ticket_number})

        except Exception as e:
            print(f'[Terminal] Pipeline error: {e}')
            q.put({'type': 'error', 'text': str(e)})
        finally:
            q.put(None)  # sentinel — stream ends

    threading.Thread(target=run_pipeline, daemon=True).start()
    return jsonify({'ticket': ticket_number, 'conv_id': conv_id})


@app.route('/stream/<ticket_number>')
def stream(ticket_number):
    def generate():
        q = _streams.get(ticket_number)
        if not q:
            yield f"data: {json.dumps({'type': 'error', 'text': 'stream not found'})}\n\n"
            return
        while True:
            try:
                event = q.get(timeout=900)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'error', 'text': 'timeout'})}\n\n"
                break
            if event is None:
                _streams.pop(ticket_number, None)
                break
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── One-click approval endpoints ───────────────────────────────────────────────

def _run_pending_for_trusted(target_email, approved_by):
    """Process any pending emails from newly trusted sender in a background thread."""
    from email_cleaner import clean_subject
    from orchestrator import consult_stage1, consult_stage2, consult_stage_eight
    from email_handler import send_reply

    pending = get_pending_emails(target_email)
    if not pending:
        return

    for p in pending:
        pending_from    = p[1]
        pending_subject = clean_subject(p[2]) if p[2] else 'Your question'
        pending_body    = p[3] or pending_subject

        queue_id, position, tags = queue_intake(pending_from, pending_subject, pending_body)
        from database import new_conversation, log_message
        conv_id       = new_conversation(pending_body, source='email', sender=pending_from)
        ticket_number = f'TICKET-{conv_id}'
        ticket_create(ticket_number, pending_from, pending_body, tags=tags, queue_id=queue_id)
        log_message(conv_id, 'Ghost', pending_body, to_agent='Gemma', message_type='chat')

        send_reply(
            to_address=pending_from,
            subject='[Swarm] On it: ' + pending_subject,
            body=(
                'Welcome! Seven\'s Swarm has received your message.\r\n\r\n'
                'The swarm is deliberating. Full response coming shortly.\r\n\r\n'
                '---\r\n'
                'Re: ' + pending_subject + '\r\n'
                "— Gemma | Seven's Swarm | sevenpotato9@gmail.com"
            )
        )

        web_results, llama_answer, shared_context, routing = consult_stage1(pending_body)
        log_message(conv_id, 'LLaMA', llama_answer, to_agent='Gemma', message_type='chat')

        send_reply(
            to_address=pending_from,
            subject='[Swarm] Received: ' + pending_subject,
            body=(
                'Consulted the web immediately.\r\n\r\n'
                '[LLaMA]:\r\n' + llama_answer + '\r\n\r\n'
                'Full swarm deliberating. Response coming shortly.\r\n\r\n'
                '---\r\n'
                "Sent by Seven's Swarm | sevenpotato9@gmail.com"
            )
        )

        if routing.get('is_sap'):
            eight_result = consult_stage_eight(pending_body, web_results, shared_context, conv_id)
            gemma_answer = eight_result['gemma_verdict']
            email2_body  = (
                '[Eight — Final verdict]:\r\n' + gemma_answer
            )
        else:
            qwen_answer, gemma_answer, debate = consult_stage2(
                pending_body, web_results, llama_answer, shared_context, conv_id, routing
            )
            debate_section = ''
            if debate['fired']:
                debate_section = (
                    '[Debate]\r\nLLaMA: ' + debate['llama_r2'] + '\r\n'
                    'Qwen: ' + debate['qwen_r2'] + '\r\n\r\n'
                )
            email2_body = (
                '[Qwen]:\r\n' + qwen_answer + '\r\n\r\n' +
                debate_section +
                '[Gemma — Final verdict]:\r\n' + gemma_answer
            )

        send_reply(
            to_address=pending_from,
            subject='[Swarm] Full response: ' + pending_subject,
            body=email2_body + '\r\n\r\n---\r\nSent by Seven\'s Swarm | sevenpotato9@gmail.com'
        )

        librarian_close(ticket_number, pending_body, gemma_answer,
                        queue_id=queue_id, sender_email=pending_from)
        mark_pending_processed(p[0])
        print(f'[Approval] {ticket_number} processed for {pending_from}')


@app.route('/approve/<action>/<token>')
def approval_action(action, token):
    """
    One-click approval endpoint. Ghost clicks link in email.
    action: trust | notify | ignore
    token: UUID from approval_tokens table
    """
    result = use_approval_token(token)

    if not result:
        return (
            '<html><body style="font-family:monospace;padding:40px;background:#1a1a1a;color:#f00">'
            '<h2>Invalid or already used token.</h2>'
            '<p>This link has already been actioned or has expired.</p>'
            '</body></html>'
        ), 400

    target  = result['target_email']
    act     = result['action']

    # Validate action matches URL (belt and braces)
    if act != action.lower():
        return ('<html><body>Token/action mismatch.</body></html>'), 400

    if act == 'trust':
        add_trusted_sender(target, 'ghost@terminal', 'Approved via one-click link')
        threading.Thread(
            target=_run_pending_for_trusted,
            args=(target, 'ghost@terminal'),
            daemon=True
        ).start()
        colour = '#0f0'
        heading = '✅ Sender trusted'
        detail  = f'{target} added to trusted senders. Any pending emails are being processed now.'
    elif act == 'notify':
        add_notification_sender(target, 'ghost@terminal', 'Filed via one-click link')
        colour = '#fa0'
        heading = '🔕 Sender filed as notification'
        detail  = f'{target} will be filed silently. No response ever.'
    elif act == 'ignore':
        add_notification_sender(target, 'ghost@terminal', 'Ignored via one-click link')
        colour = '#888'
        heading = '🚫 Sender ignored'
        detail  = f'{target} will be silently ignored from now on.'
    else:
        return ('<html><body>Unknown action.</body></html>'), 400

    print(f'[Approval] One-click: {act} → {target}')
    return (
        f'<html><body style="font-family:monospace;padding:40px;background:#1a1a1a;color:{colour}">'
        f'<h2>{heading}</h2>'
        f'<p style="color:#ccc">{detail}</p>'
        f'<p style="color:#555;font-size:12px">You can close this tab.</p>'
        f'</body></html>'
    )


# ── Nine / VS tab ─────────────────────────────────────────────────────────────

@app.route('/api/swarm/status')
def api_swarm_status():
    """Quick swarm health snapshot — no LLM, pure DB. Used by VS tab dashboard."""
    from database import log_activity as _la
    import subprocess, datetime
    conn = get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    try:
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        closed_t   = conn.execute("SELECT COUNT(*) FROM tickets WHERE DATE(closed_at)=DATE('now')").fetchone()[0]
        duck_yes   = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='YES' AND DATE(created_at)=DATE('now')").fetchone()[0]
        duck_no    = conn.execute("SELECT COUNT(*) FROM duck_log WHERE result='NO'  AND DATE(created_at)=DATE('now')").fetchone()[0]
        recent_act = conn.execute(
            "SELECT service, event, detail, created_at FROM activity_log ORDER BY id DESC LIMIT 8"
        ).fetchall()
        
        nine_mem = []
        if 'memory_nine' in tables:
            nine_mem = conn.execute("SELECT subject, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 5").fetchall()
        
        ten_mem = []
        if 'memory_ten' in tables:
            ten_mem = conn.execute("SELECT subject, created_at FROM memory_ten WHERE archived=0 ORDER BY created_at DESC LIMIT 5").fetchall()
        
        debates = []
        if 'debates' in tables:
            debates = conn.execute("SELECT topic, status, rounds FROM debates ORDER BY created_at DESC LIMIT 4").fetchall()
            
        proposals  = []
        try:
            from sandpits import list_proposals
            proposals = [p.get('agent','?') + ': ' + str(p.get('filename',''))[:60] for p in list_proposals()[:4]]
        except Exception:
            pass
    finally:
        conn.close()

    # Service health via systemctl
    svcs = {}
    for svc in ('swarm-listener', 'swarm-telegram', 'swarm-discord', 'swarm-terminal'):
        try:
            r = subprocess.run(['systemctl', 'is-active', svc], capture_output=True, text=True, timeout=2)
            svcs[svc] = r.stdout.strip()
        except Exception:
            svcs[svc] = 'unknown'

    return jsonify({
        'ts':         datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'queue':      {'queued': queued, 'processing': processing},
        'tickets':    {'open': open_t, 'closed_today': closed_t},
        'duck':       {'yes': duck_yes, 'no': duck_no},
        'services':   svcs,
        'activity':   [{'service': r[0], 'event': r[1], 'detail': str(r[2] or '')[:80], 'ts': str(r[3] or '')[:16]} for r in recent_act],
        'nine_memory': [{'subject': r[0], 'ts': str(r[1] or '')[:16]} for r in nine_mem],
        'ten_memory': [{'subject': r[0], 'ts': str(r[1] or '')[:16]} for r in ten_mem],
        'debates':    [{'topic': r[0][:60], 'status': r[1], 'rounds': r[2]} for r in debates],
        'proposals':  proposals,
    })


@app.route('/api/nine/history')
def api_nine_history():
    conn = get_connection()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if 'memory_nine' not in tables:
        conn.close()
        return jsonify([])
        
    rows = conn.execute(
        "SELECT subject, content, created_at FROM memory_nine "
        "WHERE archived=0 AND source IN ('vs_tab','repl_session','dashboard') "
        "ORDER BY created_at ASC LIMIT 40"
    ).fetchall()
    conn.close()
    return jsonify([{'question': r['subject'], 'answer': r['content'], 'ts': str(r['created_at'] or '')[:16]} for r in rows])


@app.route('/api/nine/actions')
def api_nine_actions():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, subject, content, created_at FROM memory_nine "
        "WHERE archived=0 AND tags LIKE '%action%' "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([{
        'id': r['id'],
        'title': r['subject'],
        'description': r['content'],
        'ts': str(r['created_at'] or '')[:16]
    } for r in rows])


@app.route('/api/nine', methods=['POST'])
def api_nine_chat():
    from datetime import datetime as _dt
    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400

    from database import get_agent_memory, save_agent_memory
    try:
        from claude_api import _load_api_key, CLAUDE_MODEL
        from config import NINE_SYSTEM_PROMPT
        import anthropic

        api_key = _load_api_key()
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY not configured — add to /etc/environment'}), 500

        conn       = get_connection()
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        processing = conn.execute("SELECT COUNT(*) FROM queue WHERE status='processing'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        
        # Recall: Recent flow + Relevant context
        nine_history  = conn.execute("SELECT subject, content, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 10").fetchall()
        nine_relevant = get_agent_memory('nine', query=message, limit=5)

        # Pending proposals
        try:
            from sandpits import list_proposals
            proposals = list_proposals()[:5]
        except Exception:
            proposals = []
        # Open debates
        open_debates = conn.execute(
            "SELECT topic, rounds FROM debates WHERE status='open' ORDER BY created_at DESC LIMIT 5"
        ).fetchall() if 'debates' in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()] else []
        conn.close()

        ctx  = f"=== Swarm state: {_dt.now().strftime('%Y-%m-%d %H:%M')} ===\n"
        ctx += f"Queue: {queued} queued, {processing} processing\n"
        ctx += f"Open tickets: {open_t}\n"
        ctx += "\n=== Governance (ALM) ===\n"
        ctx += "Mutating actions require approved proposal IDs (approved/executed).\n"
        ctx += "Use proposal-first workflow for shell/skill/exec/write actions.\n"
        ctx += "Draft/refine ideas in sandpits and pressure-test options with Ten, Eleven, and Twelve.\n"
        if proposals:
            ctx += f"Pending proposals: {len(proposals)}\n"
            for p in proposals[:3]:
                ctx += f"  - {str(p.get('title',''))[:80]}\n"
        if open_debates:
            ctx += f"Open debates: {len(open_debates)}\n"
            for d in open_debates:
                ctx += f"  - {d[0][:60]} ({d[1]} rounds)\n"
        if nine_relevant:
            ctx += "\n=== Relevant past context ===\n"
            for m in nine_relevant:
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        if nine_history:
            ctx += "\n=== Recent conversation history ===\n"
            for m in reversed(nine_history):
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"

        full_message = ctx + f"\n=== Ghost asks ===\n{message}"

        client   = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=NINE_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': full_message}]
        )
        answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        save_agent_memory(
            agent_name='nine', subject=message[:100], content=answer,
            tags='vs,dashboard', importance=8, source='vs_tab'
        )

        from database import log_activity
        log_activity('terminal', 'nine_consulted', f'tokens={tokens} | {message[:80]}')

        return jsonify({'answer': answer, 'tokens': tokens})

    except Exception as e:
        print(f'[Terminal] Nine error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/nine/stream', methods=['POST'])
def api_nine_stream():
    """Streaming version of Nine chat via SSE."""
    from datetime import datetime as _dt
    data    = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'empty message'}), 400

    from database import get_agent_memory, save_agent_memory
    try:
        from claude_api import _load_api_key, CLAUDE_MODEL
        from config import NINE_SYSTEM_PROMPT
        import anthropic

        api_key = _load_api_key()
        if not api_key:
            def _err():
                yield 'data: {"error": "ANTHROPIC_API_KEY not set"}\n\n'
            return Response(_err(), mimetype='text/event-stream')

        conn       = get_connection()
        queued     = conn.execute("SELECT COUNT(*) FROM queue WHERE status='queued'").fetchone()[0]
        open_t     = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        nine_history = conn.execute("SELECT subject, content, created_at FROM memory_nine WHERE archived=0 ORDER BY created_at DESC LIMIT 8").fetchall()
        nine_relevant = get_agent_memory('nine', query=message, limit=4)
        conn.close()

        ctx  = f"=== Swarm state: {_dt.now().strftime('%Y-%m-%d %H:%M')} ===\n"
        ctx += f"Queue: {queued} queued | Open tickets: {open_t}\n"
        if nine_relevant:
            ctx += "\n=== Relevant past context ===\n"
            for m in nine_relevant:
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        if nine_history:
            ctx += "\n=== Recent conversation history ===\n"
            for m in reversed(nine_history):
                ctx += f"[{str(m['created_at'] or '')[:16]}] {m['subject']}: {str(m['content'] or '')[:1000]}\n"
        full_message = ctx + f"\n=== Ghost asks ===\n{message}"

        client = anthropic.Anthropic(api_key=api_key)

        def _generate():
            full_answer = []
            try:
                with client.messages.stream(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    system=NINE_SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': full_message}]
                ) as stream:
                    for text in stream.text_stream:
                        full_answer.append(text)
                        yield f'data: {json.dumps({"text": text})}\n\n'
                answer = ''.join(full_answer)
                tokens = stream.get_final_message().usage
                total  = tokens.input_tokens + tokens.output_tokens
                save_agent_memory(
                    agent_name='nine', subject=message[:100], content=answer,
                    tags='vs,dashboard', importance=8, source='vs_tab'
                )
                from database import log_activity
                log_activity('terminal', 'nine_consulted', f'tokens={total} | {message[:80]}')
                yield f'data: {json.dumps({"done": True, "tokens": total})}\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'

        return Response(_generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Terminal tab ───────────────────────────────────────────────────────────────


# ── Ghost Layer exec (Nine + Ghost, elevated) ─────────────────────────────────

# Commands Nine/Ghost can run directly from the VS tab.
# systemctl swarm-* uses NOPASSWD sudoers rule.
# Everything else goes through the shell_agent whitelist.
import re as _re
_SUDO_ALLOWED = _re.compile(
    r'^sudo\s+systemctl\s+(restart|start|stop|status)\s+swarm-\w+$'
)

@app.route('/api/exec', methods=['POST'])
def api_exec():
    import subprocess as _sp
    data = request.get_json() or {}
    cmd  = (data.get('command') or '').strip()

    gate = _alm_gate_or_response(data, 'exec')
    if gate:
        return gate

    if not cmd:
        return jsonify({'output': '', 'ok': True})

    from database import log_activity

    if _SUDO_ALLOWED.match(cmd):
        try:
            result = _sp.run(
                cmd.split(), capture_output=True, text=True, timeout=15
            )
            output = (result.stdout + result.stderr).strip() or '(done)'
            ok     = result.returncode == 0
            log_activity('terminal', 'ghost_exec_sudo', cmd[:80])
            return jsonify({'output': output, 'ok': ok})
        except Exception as e:
            return jsonify({'output': f'Error: {e}', 'ok': False})

    # Fallback: shell_agent whitelist
    from fridays.skills import call as skill_call
    ok, output = skill_call('shell', args=cmd, agent='ghost')
    log_activity('terminal', 'ghost_exec', cmd[:80])
    return jsonify({'output': output, 'ok': ok})


# ── Ghost Layer file write (Nine proposes, Ghost applies via VS tab) ───────────

import os as _os

_SWARM_ROOT = '/home/seven/swarm'

@app.route('/api/exec/write', methods=['POST'])
def api_exec_write():
    """Write a file. Path must be inside /home/seven/swarm."""
    data    = request.get_json() or {}
    path    = (data.get('path') or '').strip()
    content = data.get('content', '')
    desc    = (data.get('description') or '').strip()

    gate = _alm_gate_or_response(data, 'exec_write')
    if gate:
        return gate

    if not path or not path.startswith(_SWARM_ROOT):
        return jsonify({'error': 'Path must be within /home/seven/swarm'}), 400
    if '..' in path:
        return jsonify({'error': 'Invalid path'}), 400

    try:
        # Read previous content for audit trail
        try:
            with open(path, 'r') as f:
                previous = f.read()
        except FileNotFoundError:
            previous = ''

        # Ensure parent dir exists
        _os.makedirs(_os.path.dirname(path), exist_ok=True)

        with open(path, 'w') as f:
            f.write(content)

        conn = get_connection()
        conn.execute(
            "INSERT INTO file_writes (path, description, previous_content, new_content, applied_by) VALUES (?,?,?,?,?)",
            (path, desc, previous[:2000], content[:4000], 'ghost')
        )
        conn.commit()
        conn.close()

        from database import log_activity
        log_activity('terminal', 'file_write', f'{path} — {desc[:60]}')

        lines_old = len(previous.splitlines())
        lines_new = len(content.splitlines())
        return jsonify({'ok': True, 'output': f'Written: {path}\n{lines_old} → {lines_new} lines'})
    except Exception as e:
        return jsonify({'error': str(e), 'ok': False}), 500


# ── Debates (agent deliberation protocol) ─────────────────────────────────────

@app.route('/api/debates')
def api_debates_list():
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT id, topic, initiator, status, rounds, consensus, created_at FROM debates ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'topic': r[1], 'initiator': r[2],
        'status': r[3], 'rounds': r[4], 'consensus': r[5], 'ts': str(r[6] or '')[:16]
    } for r in rows])


@app.route('/api/debates', methods=['POST'])
def api_debates_create():
    data  = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'error': 'topic required'}), 400
    conn = get_connection()
    conn.execute("INSERT INTO debates (topic, initiator) VALUES (?, ?)", (topic, 'nine'))
    conn.commit()
    debate_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    from database import log_activity
    log_activity('terminal', 'debate_opened', topic[:80])
    return jsonify({'id': debate_id, 'ok': True})


@app.route('/api/debates/<int:debate_id>/turns')
def api_debate_turns(debate_id):
    conn  = get_connection()
    turns = conn.execute(
        "SELECT agent, position, round, created_at FROM debate_turns WHERE debate_id=? ORDER BY round, created_at",
        (debate_id,)
    ).fetchall()
    conn.close()
    return jsonify([{'agent': t[0], 'position': t[1], 'round': t[2], 'ts': str(t[3] or '')[:16]} for t in turns])


@app.route('/api/debates/<int:debate_id>/run', methods=['POST'])
def api_debate_run(debate_id):
    """Run a debate asynchronously — returns immediately, debate runs in background thread."""
    import threading
    def _run():
        try:
            from debate import run_debate
            result = run_debate(debate_id)
            print(f'[Terminal] Debate #{debate_id} finished: {result["status"]}')
        except Exception as e:
            print(f'[Terminal] Debate #{debate_id} error: {e}')
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True, 'message': f'Debate #{debate_id} started in background'})


@app.route('/api/debates/quick', methods=['POST'])
def api_debate_quick():
    """Open + run a debate from VS tab. Topic in request body."""
    data  = request.get_json() or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify({'error': 'topic required'}), 400
    import threading
    results = {}
    def _run():
        try:
            from debate import run_and_resolve
            results['result'] = run_and_resolve(topic, initiator='nine')
        except Exception as e:
            results['error'] = str(e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=0)  # Fire and forget — VS tab polls for result
    conn = get_connection()
    debate_id = conn.execute("SELECT id FROM debates WHERE topic=? ORDER BY id DESC LIMIT 1", (topic,)).fetchone()
    conn.close()
    return jsonify({'ok': True, 'debate_id': debate_id[0] if debate_id else None,
                    'message': f'Debate started: {topic[:60]}'})


# ── Agent Autonomy Endpoints ──────────────────────────────────────────────────

@app.route('/api/agents/<agent>/memory')
def api_agent_memory(agent):
    """Browse an agent's persistent memory pool. Query params: ?query=... &limit=10 &importance=5+"""
    query = request.args.get('query', '').strip()
    limit = int(request.args.get('limit', 10))
    min_importance = int(request.args.get('min_importance', 0))
    
    conn = get_connection()
    
    # Map agent name to memory table
    agent_key = agent.lower()
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    table = memory_tables.get(agent_key)
    if not table:
        conn.close()
        return jsonify({'error': f'No memory pool for agent: {agent}'}), 404
    
    # Check what columns exist in this table
    try:
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = {col[1] for col in c.fetchall()}
        
        # Build query based on available columns
        if 'subject' in columns:
            # Schema: memory_gemma, memory_eight, memory_nine style
            search_clause = "(subject LIKE ? OR content LIKE ?)" if query else "1=1"
            search_params = (f'%{query}%', f'%{query}%') if query else ()
            
            rows = conn.execute(f"""
                SELECT id, subject, content, tags, importance, created_at 
                FROM {table}
                WHERE {search_clause}
                AND importance >= ? AND archived = 0
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, search_params + (min_importance, limit)).fetchall()
        else:
            # Schema: memory_twelve style (no subject)
            rows = conn.execute(f"""
                SELECT id, content, tags, type, importance, created_at 
                FROM {table}
                WHERE content LIKE ?
                AND importance >= ? AND archived = 0
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
            """, (f'%{query}%', min_importance, limit)).fetchall()
        
        conn.close()
        return jsonify({
            'agent': agent,
            'table': table,
            'query': query,
            'limit': limit,
            'entries': [dict(r) for r in rows]
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/agents/<agent>/memory/write', methods=['POST'])
def api_agent_memory_write(agent):
    """Write to an agent's memory pool. Body: {content, tags?, importance?} for memory_twelve style"""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    tags = (data.get('tags') or '').strip()
    importance = int(data.get('importance', 5))
    memo_type = (data.get('type') or 'observation').strip()  # For memory_twelve
    subject = (data.get('subject') or '').strip()  # For memory_gemma/eight/nine
    
    if not content:
        return jsonify({'error': 'content required'}), 400
    
    if not 1 <= importance <= 10:
        return jsonify({'error': 'importance must be 1-10'}), 400
    
    conn = get_connection()
    
    agent_key = agent.lower()
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    table = memory_tables.get(agent_key)
    if not table:
        conn.close()
        return jsonify({'error': f'No memory pool for agent: {agent}'}), 404
    
    try:
        now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        
        # Detect schema
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        columns = {col[1] for col in c.fetchall()}
        
        if 'subject' in columns:
            # memory_gemma/eight/nine style
            source = data.get('source', 'api')
            conn.execute(f"""
                INSERT INTO {table} (agent, subject, content, tags, importance, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (agent_key, (subject or content[:100])[:200], content, tags, importance, source, now))
        else:
            # memory_twelve style  
            conn.execute(f"""
                INSERT INTO {table} (agent, content, tags, importance, type, created_at, updated_at, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (agent_key, content, tags, importance, memo_type, now, now))
        
        conn.commit()
        
        entry_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()['id']
        conn.close()
        
        return jsonify({
            'ok': True,
            'agent': agent,
            'table': table,
            'entry_id': entry_id,
            'importance': importance
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/agents/memories/query')
def api_agents_memories_query():
    """Cross-agent memory search. Find what any agent knows about a topic."""
    q = request.args.get('q', '').strip()
    agents_filter = [a.strip().lower() for a in request.args.get('agents', '').split(',') if a.strip()]  # Handle empty strings
    limit = int(request.args.get('limit', 5))
    min_importance = int(request.args.get('min_importance', 1))  # Changed default to 1 for broader search
    
    if not q:
        return jsonify({'error': 'q (query) required'}), 400
    
    memory_tables = {
        'gemma': 'memory_gemma', 'llama': 'memory_llama', 'qwen': 'memory_qwen',
        'eight': 'memory_eight', 'nine': 'memory_nine', 'ten': 'memory_ten',
        'twelve': 'memory_twelve', 'eleven': 'memory_grok', 'grok': 'memory_grok',
        'librarian': 'memory', 'duck': 'memory', 'sniffles': 'memory'
    }
    
    conn = get_connection()
    results = {}
    
    # If agents specified, search only those; otherwise search all
    tables_to_search = {k: v for k, v in memory_tables.items() 
                       if not agents_filter or k in agents_filter}
    
    for agent_key, table in tables_to_search.items():
        try:
            # Detect schema for this table
            c = conn.cursor()
            c.execute(f"PRAGMA table_info({table})")
            columns = {col[1] for col in c.fetchall()}
            
            if 'subject' in columns:
                # memory_gemma/eight/nine style
                rows = conn.execute(f"""
                    SELECT id, subject, content, tags, importance, created_at 
                    FROM {table}
                    WHERE (subject LIKE ? OR content LIKE ?) 
                    AND importance >= ? AND archived = 0
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (f'%{q}%', f'%{q}%', min_importance, limit)).fetchall()
            else:
                # memory_twelve style
                rows = conn.execute(f"""
                    SELECT id, content, tags, type, importance, created_at 
                    FROM {table}
                    WHERE content LIKE ?
                    AND importance >= ? AND archived = 0
                    ORDER BY importance DESC, created_at DESC
                    LIMIT ?
                """, (f'%{q}%', min_importance, limit)).fetchall()
            
            if rows:
                results[agent_key] = [dict(r) for r in rows]
        except:
            pass  # Table might not exist, skip
    
    conn.close()
    
    return jsonify({
        'query': q,
        'agents': list(results.keys()),
        'results': results
    })


# ═══════════════════════════════════════════════════════════════════════════════
# TIME MACHINE — Agent Twelve's temporal tracking endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/time/timeline', methods=['GET'])
def api_time_timeline():
    """Get agent timeline — all recorded events."""
    agent = request.args.get('agent', None)
    start_time = request.args.get('start', None)
    end_time = request.args.get('end', None)
    limit = int(request.args.get('limit', 100))
    
    timeline = time_wizard.get_timeline(
        agent=agent,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'agent': agent,
        'count': len(timeline),
        'timeline': timeline
    })


@app.route('/api/time/sessions', methods=['GET'])
def api_time_sessions():
    """Get all temporal sessions."""
    agent = request.args.get('agent', None)
    status = request.args.get('status', None)
    
    sessions = time_wizard.get_sessions(agent=agent, status=status)
    
    return jsonify({
        'agent': agent,
        'status': status,
        'count': len(sessions),
        'sessions': sessions
    })


@app.route('/api/time/checkpoint/<name>', methods=['GET'])
def api_time_checkpoint(name):
    """Retrieve a specific checkpoint."""
    checkpoint = time_wizard.get_checkpoint(name)
    
    if not checkpoint:
        return jsonify({'error': f'Checkpoint "{name}" not found'}), 404
    
    return jsonify(checkpoint)


@app.route('/api/time/checkpoints', methods=['GET'])
def api_time_checkpoints():
    """List all checkpoints."""
    before = request.args.get('before', None)
    after = request.args.get('after', None)
    limit = int(request.args.get('limit', 100))
    
    checkpoints = time_wizard.list_checkpoints(before_time=before, after_time=after, limit=limit)
    
    return jsonify({
        'count': len(checkpoints),
        'checkpoints': checkpoints
    })


@app.route('/api/time/checkpoints', methods=['POST'])
def api_time_create_checkpoint():
    """Capture a Swarm-facing Vortex checkpoint from current workflow state."""
    data = request.get_json() or {}
    label = (data.get('label') or 'manual-checkpoint').strip()
    description = (data.get('description') or '').strip()
    agent = (data.get('agent') or 'terminal_ui').strip()

    try:
        checkpoint = time_wizard.create_workflow_checkpoint(label=label, agent=agent, description=description)
        return jsonify({'ok': True, 'checkpoint': checkpoint}), 201
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/time/restore', methods=['POST'])
def api_time_restore():
    """Preview or apply a workflow state step-back to a named Vortex checkpoint."""
    data = request.get_json() or {}
    checkpoint_name = (data.get('checkpoint_name') or '').strip()
    actor = (data.get('actor') or 'terminal_ui').strip()
    dry_run = bool(data.get('dry_run', True))

    if not checkpoint_name:
        return jsonify({'ok': False, 'error': 'checkpoint_name required'}), 400

    # Non-dry-run state restore is irreversible — require an approved proposal.
    if not dry_run:
        gate = _alm_gate_or_response(data, 'time_restore')
        if gate:
            return gate

    try:
        result = time_wizard.restore_workflow_state(checkpoint_name=checkpoint_name, actor=actor, dry_run=dry_run)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/time/stats/<agent>', methods=['GET'])
def api_time_stats(agent):
    """Get temporal statistics for an agent."""
    stats = time_wizard.get_temporal_stats(agent)
    return jsonify(stats)


@app.route('/api/time/bootstrap', methods=['POST'])
def api_time_bootstrap():
    """Initialize a new Time Wizard session."""
    try:
        session_id = time_wizard.bootstrap_session()
        if session_id:
            return jsonify({'ok': True, 'session_id': session_id}), 201
        else:
            return jsonify({'ok': False, 'error': 'Bootstrap failed'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/time/log-decision', methods=['POST'])
def api_time_log_decision():
    """Log a decision execution event."""
    data = request.get_json() or {}
    decision_id = data.get('decision_id')
    agent = data.get('agent', 'twelve')
    status = data.get('status', 'executed')
    details = data.get('details', {})
    
    if not decision_id:
        return jsonify({'ok': False, 'error': 'decision_id required'}), 400
    
    try:
        event_id = time_wizard.log_decision_execution(
            decision_id, agent, status, details
        )
        return jsonify({
            'ok': True,
            'event_id': event_id,
            'decision_id': decision_id
        }), 201
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/time/decision-history/<decision_id>', methods=['GET'])
def api_time_decision_history(decision_id):
    """Get execution history for a decision."""
    try:
        history = time_wizard.get_decision_history(decision_id)
        return jsonify({
            'ok': True,
            'decision_id': decision_id,
            'events': history,
            'total': len(history)
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# KILL SWITCHES — Emergency control endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/killswitch/buttons', methods=['GET'])
def api_killswitch_buttons():
    """Get desktop kill switch button configuration."""
    return jsonify(kill_switch.create_desktop_buttons())


@app.route('/api/killswitch/emergency', methods=['POST'])
def api_killswitch_emergency():
    """EMERGENCY SHUTDOWN — immediate stop all agents."""
    reason = request.json.get('reason', 'Manual emergency shutdown') if request.json else 'Manual emergency shutdown'
    
    kill_switch.record_kill_event('emergency_shutdown', agent='system', reason=reason)
    success = kill_switch.emergency_shutdown(reason=reason)
    
    return jsonify({
        'action': 'emergency_shutdown',
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })


@app.route('/api/killswitch/pause', methods=['POST'])
def api_killswitch_pause():
    """Pause all active agents."""
    reason = request.json.get('reason', 'Manual pause') if request.json else 'Manual pause'
    
    kill_switch.record_kill_event('pause_all', agent='system', reason=reason)
    success = kill_switch.pause_all_agents(reason=reason)
    
    return jsonify({
        'action': 'pause_all',
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })


@app.route('/api/killswitch/resume', methods=['POST'])
def api_killswitch_resume():
    """Resume paused agents."""
    kill_switch.record_kill_event('resume_all', agent='system')
    success = kill_switch.resume_agents()
    
    return jsonify({
        'action': 'resume_all',
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })


@app.route('/api/killswitch/restart', methods=['POST'])
def api_killswitch_restart():
    """Restart swarm server."""
    kill_switch.record_kill_event('restart_server', agent='system')
    kill_switch.broadcast_alert('🔄 RESTART SERVER initiated')
    
    # Spawn restart in background
    def _restart():
        import time
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    threading.Thread(target=_restart, daemon=True).start()
    
    return jsonify({
        'action': 'restart',
        'success': True,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
        'note': 'Server restarting in 1 second...'
    })


@app.route('/api/killswitch/agent/<agent_name>/reset', methods=['POST'])
def api_killswitch_agent_reset(agent_name):
    """Reset specific agent."""
    kill_switch.record_kill_event('agent_reset', agent=agent_name)
    success = kill_switch.reset_agent(agent_name)
    
    return jsonify({
        'action': 'agent_reset',
        'agent': agent_name,
        'success': success,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })


# ══════════════════════════════════════════════════════════════════════════════
# GHOST BRIEF — Swarm Intelligence Feed
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/brief')
def api_brief_get():
    """Return the latest cached Ghost Brief from DB (read-only, no generation)."""
    from brief_engine import get_latest_brief
    try:
        brief = get_latest_brief()
        return jsonify({'brief': brief})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/brief/generate', methods=['POST'])
def api_brief_generate():
    """Force-generate a new Ghost Brief immediately."""
    from brief_engine import generate_brief
    try:
        brief = generate_brief(trigger='manual')
        if not brief:
            return jsonify({'error': 'Brief generation failed — check Claude API key'}), 503
        return jsonify(brief)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/brief/history')
def api_brief_history():
    """Return list of past Ghost Briefs."""
    from brief_engine import get_brief_history
    try:
        limit = int(request.args.get('limit', 10))
        return jsonify({'briefs': get_brief_history(limit=limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# TIME WIZARD — Decision Logging & Audit Trail API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/decisions')
def api_decisions():
    """
    List all decisions from the Time Wizard decision index.
    Returns decision metadata from sandpits/twelve/DECISION_INDEX.md
    """
    import os
    import re
    
    index_path = str(SWARM_ROOT / 'sandpits' / 'twelve' / 'DECISION_INDEX.md')
    
    if not os.path.exists(index_path):
        return jsonify({'decisions': [], 'total': 0, 'message': 'No decisions logged yet'})
    
    try:
        with open(index_path, 'r') as f:
            content = f.read()
        
        # Parse decisions from markdown table 
        # | ID | Title | Status | Proposed | Category | Impact |
        lines = content.split('\n')
        decisions = []
        
        for line in lines:
            if line.startswith('|') and 'Title' not in line and '---' not in line and line.count('|') >= 5:
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 5:
                    decisions.append({
                        'id': parts[0],
                        'title': parts[1],
                        'status': parts[2],
                        'proposed': parts[3],
                        'category': parts[4] if len(parts) > 4 else '',
                        'impact': parts[5] if len(parts) > 5 else ''
                    })
        
        return jsonify({
            'decisions': decisions,
            'total': len(decisions),
            'last_updated': datetime.now(timezone.utc).isoformat() + 'Z'
        })
    
    except Exception as e:
        return jsonify({'error': str(e), 'decisions': []}), 500


@app.route('/api/decisions/<decision_id>')
def api_decision_detail(decision_id):
    """
    Get full details of a specific decision.
    Reads from sandpits/twelve/proposals/DECISION-NNN-*.md
    """
    import os
    import glob
    
    proposal_dir = str(SWARM_ROOT / 'sandpits' / 'twelve' / 'proposals')
    
    # Find the proposal file — decision_id is already full e.g. "DECISION-001"
    pattern = f'{proposal_dir}/{decision_id}-*.md'
    matches = glob.glob(pattern)
    # Fallback: bare numeric id e.g. "001"
    if not matches:
        pattern = f'{proposal_dir}/DECISION-{decision_id}-*.md'
        matches = glob.glob(pattern)

    if not matches:
        return jsonify({'error': f'Decision {decision_id} not found'}), 404

    try:
        with open(matches[0], 'r') as f:
            content = f.read()

        # Parse markdown decision
        lines = content.split('\n')
        decision_data = {
            'id': decision_id,
            'file': os.path.basename(matches[0]),
            'content': content,
            'sections': {}
        }

        # Extract flat fields from well-known header lines
        for line in lines[:12]:
            if line.startswith('# '):
                decision_data['title'] = line.lstrip('# ').strip()
            if line.startswith('**Status**:'):
                decision_data['status'] = line.split(':', 1)[1].strip().strip('*')
            if line.startswith('**Agent**:'):
                decision_data['agent'] = line.split(':', 1)[1].strip().strip('*')

        current_section = None
        for line in lines:
            if line.startswith('## '):
                current_section = line.replace('## ', '').strip()
                decision_data['sections'][current_section] = []
            elif current_section and line.strip():
                decision_data['sections'][current_section].append(line)

        # Map sections to flat fields expected by the UI
        sec = decision_data['sections']
        decision_data['issue']      = '\n'.join(sec.get('Issue', sec.get('Problem', [])))
        decision_data['solution']   = '\n'.join(sec.get('Proposed Solution', sec.get('Solution', [])))
        decision_data['scope']      = '\n'.join(sec.get('Scope', sec.get('Impact', [])))
        decision_data['risks']      = '\n'.join(sec.get('Risks', sec.get('Risk', [])))
        decision_data['next_steps'] = '\n'.join(sec.get('Next Steps', sec.get('Actions', [])))

        return jsonify(decision_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline')
def api_decision_timeline():
    """
    Get chronological timeline of all decisions.
    Useful for audit trail and dependency visualization.
    """
    import os
    import glob
    from datetime import datetime as dt
    
    proposal_dir = str(SWARM_ROOT / 'sandpits' / 'twelve' / 'proposals')
    timeline = []
    
    # Find all decision files
    decision_files = glob.glob(f'{proposal_dir}/DECISION-*.md')
    
    for file_path in sorted(decision_files):
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Extract metadata from top of file
            lines = content.split('\n')
            entry = {
                'file': os.path.basename(file_path),
                'decision_id': os.path.basename(file_path).split('-')[1],
                'proposed': None,
                'status': 'UNKNOWN',
                'title': ''
            }
            
            for line in lines[:20]:
                if line.startswith('# Decision'):
                    entry['title'] = line.replace('# Decision', '').strip()
                elif line.startswith('**Status**:'):
                    entry['status'] = line.split('**Status**:')[1].strip().split('|')[0].strip()
                elif line.startswith('**Proposed**:'):
                    entry['proposed'] = line.split('**Proposed**:')[1].strip()
            
            timeline.append(entry)
        
        except Exception as e:
            print(f'[Time Wizard] Error parsing {file_path}: {e}')
    
    # Sort by proposed date
    timeline.sort(key=lambda x: x['proposed'] or '', reverse=True)
    
    return jsonify({
        'timeline': timeline,
        'total': len(timeline),
        'last_update': datetime.now(timezone.utc).isoformat() + 'Z'
    })


if __name__ == '__main__':
    print("\n╔═══════════════════════════════╗")
    print("║   Fridays Terminal  —  5050   ║")
    print("╚═══════════════════════════════╝")
    print("  http://localhost:5050")
    print("  Tailscale only in production.\n")
    print(f"  {THEME_SYNC_REMINDER}")
    
    # Initialize Time Wizard session on startup when supported.
    try:
        bootstrap = getattr(time_wizard, 'bootstrap_session', None)
        if callable(bootstrap):
            session_id = bootstrap()
            print(f"  Time Wizard initialized: {session_id}\n")
        else:
            print("  Time Wizard initialized: compatibility mode (no bootstrap_session)\n")
    except Exception as e:
        print(f"  Time Wizard init warning: {e}\n")
    
    class _ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class _ThreadingIPv6WSGIServer(_ThreadingWSGIServer):
        address_family = socket.AF_INET6

    # Prefer IPv6 bind so localhost (::1) works in browsers that resolve IPv6 first.
    # Fall back to IPv4 if the host environment doesn't support IPv6 sockets.
    try:
        with make_server('::', 5050, app, server_class=_ThreadingIPv6WSGIServer) as httpd:
            print('  Serving threaded WSGI on [::]:5050')
            httpd.serve_forever()
    except OSError as e:
        print(f"  IPv6 bind failed ({e}); falling back to IPv4 0.0.0.0")
        with make_server('0.0.0.0', 5050, app, server_class=_ThreadingWSGIServer) as httpd:
            print('  Serving threaded WSGI on 0.0.0.0:5050')
            httpd.serve_forever()
