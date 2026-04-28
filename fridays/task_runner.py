"""
fridays/task_runner.py — Python task runner registry for the Tasker.

Maps task function names to Python callables so scheduled_tasks with
action_type='PYTHON' can invoke internal functions directly instead of
shelling out via subprocess.

Usage
-----
    from fridays.task_runner import run_task, list_registered, TASK_REGISTRY

    success, output = run_task('housekeeping')
    success, output = run_task('knowledge_seed', args='fridays')
"""

import logging
import sys
import time
from datetime import datetime

sys.path.insert(0, '/home/seven/swarm')

logger = logging.getLogger('seven.task_runner')


# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry: name → {fn, description, category}
# fn is a callable: fn(**kwargs) -> str  (returns summary string)

TASK_REGISTRY = {}


def register(name, description='', category='system'):
    """Decorator to register a task function."""
    def wrapper(fn):
        TASK_REGISTRY[name] = {
            'fn': fn,
            'description': description,
            'category': category,
        }
        return fn
    return wrapper


# ── Built-in tasks ────────────────────────────────────────────────────────────

@register('housekeeping', 'Full housekeeping cycle: archive, dedup, curate, play time, landscape refresh', 'maintenance')
def _task_housekeeping(**kwargs):
    from lib.system.housekeeping import run_housekeeping
    run_housekeeping()
    return 'Housekeeping cycle complete'


@register('archive_memories', 'Archive old low-importance memories (>30 days)', 'maintenance')
def _task_archive_memories(**kwargs):
    from lib.system.housekeeping import archive_old_memories
    count = archive_old_memories()
    return f'Archived {count} old memories'


@register('dedup_memories', 'Remove duplicate memory entries across all tables', 'maintenance')
def _task_dedup_memories(**kwargs):
    from lib.system.housekeeping import deduplicate_memories
    count = deduplicate_memories()
    return f'Removed {count} duplicates'


@register('curate_memories', 'AI-powered memory curation via Gemma3', 'maintenance')
def _task_curate_memories(**kwargs):
    from lib.system.housekeeping import curate_agent_memories
    removed, rewritten = curate_agent_memories()
    return f'Curation: {removed} deleted, {rewritten} rewritten'


@register('daily_digest', 'Send daily digest email + Discord notification', 'comms')
def _task_daily_digest(**kwargs):
    from utils.swarm_tasks import send_daily_digest
    send_daily_digest()
    return 'Daily digest sent'


@register('daily_brief', 'Generate and email Ghost Brief via Claude', 'comms')
def _task_daily_brief(**kwargs):
    from fridays.scheduler import run_daily_brief
    run_daily_brief()
    return 'Daily brief sent'


@register('sla_check', 'Warn Ghost about tickets open > 4 hours', 'monitoring')
def _task_sla_check(**kwargs):
    from utils.swarm_tasks import check_sla
    check_sla(hours=4)
    return 'SLA check complete'


@register('snoozed_check', 'Wake snoozed tickets whose time has passed', 'monitoring')
def _task_snoozed_check(**kwargs):
    from utils.swarm_tasks import check_snoozed
    check_snoozed()
    return 'Snoozed check complete'


@register('proposals_check', 'Scan for new agent proposals and notify Ghost', 'monitoring')
def _task_proposals_check(**kwargs):
    from utils.swarm_tasks import check_proposals
    check_proposals()
    return 'Proposals check complete'


@register('play_time', 'Give idle agents proposal drafting time', 'agents')
def _task_play_time(**kwargs):
    from utils.swarm_tasks import run_play_time
    run_play_time()
    return 'Play time complete'


@register('relay_recovery_sweep', 'Review stalled chat relay recovery cards with Librarian and Duck', 'agents')
def _task_relay_recovery_sweep(**kwargs):
    """
    Sweep open chat relay recovery cards.

    Args:
      limit=3             max cards to inspect
      run_agents=0        set to 1 to actually ask Librarian and Duck
      agents=librarian,duck
      lease_minutes=30    active-review lease duration
      idle_window=22:00-06:00
      force=0             set to 1 to override the idle window

    Dry-run is the default so Tasker can safely surface pending recoveries.
    """
    import json
    import shlex
    from utils.db.chat import (
        get_open_chat_relay_recoveries,
        lease_chat_relay_recoveries,
        log_message,
        update_chat_relay_recovery_status,
    )

    opts = {
        'limit': '3',
        'run_agents': '0',
        'agents': 'librarian,duck',
        'lease_minutes': '30',
        'idle_window': '22:00-06:00',
        'force': '0',
    }
    for tok in shlex.split(kwargs.get('args') or ''):
        if '=' not in tok:
            continue
        k, v = tok.split('=', 1)
        if k.strip().lower() in opts:
            opts[k.strip().lower()] = v.strip()

    try:
        limit = max(1, min(int(opts['limit']), 10))
    except Exception:
        limit = 3
    run_agents = str(opts.get('run_agents') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    try:
        lease_seconds = max(60, min(int(float(opts.get('lease_minutes') or 30) * 60), 7200))
    except Exception:
        lease_seconds = 1800
    force = str(opts.get('force') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    agents = [
        item.strip().lower()
        for item in str(opts.get('agents') or '').split(',')
        if item.strip().lower() in {'librarian', 'duck'}
    ] or ['librarian', 'duck']

    if not run_agents:
        recoveries = get_open_chat_relay_recoveries(limit=limit)
        if not recoveries:
            return 'No open chat relay recoveries.'
        ids = ', '.join(str(r.get('recovery_id') or '?') for r in recoveries)
        return f'{len(recoveries)} open relay recoveries pending: {ids}. Re-run with run_agents=1 to ask Librarian/Duck.'

    idle_window = str(opts.get('idle_window') or '22:00-06:00').strip()
    if not force and not _tasker_in_idle_window(idle_window):
        return (
            f'Active relay recovery deferred outside idle window {idle_window}. '
            'Re-run with force=1 to override.'
        )

    try:
        import orchestrator
    except Exception:
        from core.pipeline import orchestrator

    recoveries = lease_chat_relay_recoveries(
        'tasker:relay_recovery_sweep',
        limit=limit,
        lease_seconds=lease_seconds,
    )
    if not recoveries:
        return 'No unleased open chat relay recoveries.'

    reviewed = []
    for recovery in recoveries:
        recovery_id = str(recovery.get('recovery_id') or '').strip()
        conv_id = int(recovery.get('conversation_id') or 0)
        context = {}
        try:
            context = json.loads(recovery.get('relay_context_json') or '{}')
        except Exception:
            context = {}
        thread_tail = context.get('thread_tail') if isinstance(context, dict) else []
        stage_trace = context.get('stage_trace') if isinstance(context, dict) else []
        prompt = _relay_recovery_agent_prompt(recovery, thread_tail, stage_trace)

        outputs = []
        for agent in agents:
            try:
                answer = orchestrator.ask_agent(agent, prompt)
            except Exception as exc:
                answer = f'[{agent}] relay recovery review failed: {exc}'
            outputs.append(f'{agent}: {str(answer or "").strip()[:1200]}')
            if conv_id:
                log_message(
                    conv_id,
                    agent,
                    str(answer or '').strip() or f'[{agent}] no recovery review returned',
                    to_agent='user',
                    message_type='relay_recovery_review',
                    tokens_used=0,
                )

        update_chat_relay_recovery_status(
            recovery_id,
            'reviewed',
            summary='; '.join(outputs)[:1000],
        )
        reviewed.append(recovery_id)

    return f'Reviewed {len(reviewed)} relay recoveries: {", ".join(reviewed)}'


def _tasker_in_idle_window(window, now=None):
    """Return whether local time is inside an HH:MM-HH:MM idle window."""
    window = str(window or '').strip()
    if not window or '-' not in window:
        return True
    start_raw, end_raw = [part.strip() for part in window.split('-', 1)]
    try:
        start_h, start_m = [int(part) for part in start_raw.split(':', 1)]
        end_h, end_m = [int(part) for part in end_raw.split(':', 1)]
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
    except Exception:
        return True
    if not (0 <= start < 1440 and 0 <= end < 1440):
        return True
    now = now or datetime.now()
    minute = int(now.hour) * 60 + int(now.minute)
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end


def _relay_recovery_agent_prompt(recovery, thread_tail, stage_trace):
    lines = [
        'You are reviewing a stalled chat relay recovery card.',
        f"Recovery ID: {recovery.get('recovery_id')}",
        f"Conversation: #{recovery.get('conversation_id')}",
        f"Stalled agent: {recovery.get('stalled_agent')}",
        f"Summary: {recovery.get('summary')}",
        '',
        'Last stage trace:',
    ]
    for item in (stage_trace or [])[-6:]:
        text = item.get('text') if isinstance(item, dict) else item
        if text:
            lines.append(f'- {str(text)[:180]}')
    lines.append('')
    lines.append('Thread tail:')
    for msg in (thread_tail or [])[-6:]:
        if not isinstance(msg, dict):
            continue
        sender = str(msg.get('from_agent') or 'unknown')
        target = str(msg.get('to_agent') or '')
        content = ' '.join(str(msg.get('content') or '').split())[:260]
        if content:
            lines.append(f'- {sender} -> {target}: {content}')
    lines.append('')
    lines.append('Return concise recovery notes: intended next step, risks, missing evidence, and who should continue. Do not expose private chain-of-thought.')
    return '\n'.join(lines)


@register('knowledge_seed', 'Seed knowledge library (args: collection name or "all")', 'knowledge')
def _task_knowledge_seed(**kwargs):
    args = kwargs.get('args', 'all').strip() or 'all'
    from lib.knowledge.seed import seed_collection
    added, skipped = seed_collection(args)
    return f'Seeded {args}: {added} added, {skipped} skipped'


@register('knowledge_reindex', 'Re-embed all knowledge chunks (full reindex)', 'knowledge')
def _task_knowledge_reindex(**kwargs):
    from lib.knowledge.store import list_sources, get_source
    from lib.knowledge.ingest import process_source
    sources = list_sources()
    count = 0
    for src in sources:
        try:
            full = get_source(src['source_id'])
            if full and full.get('raw_text'):
                process_source(src['source_id'], full['raw_text'])
                count += 1
        except Exception as e:
            logger.warning(f'[TaskRunner] reindex source {src["source_id"]}: {e}')
    return f'Re-indexed {count}/{len(sources)} sources'


@register('idle_research', 'Pick an active topic from user_interests and run Scholar research on it', 'knowledge')
def _task_idle_research(**kwargs):
    """
    Idle research rotation — weighted random draw from active user_interests rows.
    Optional args (space-separated): username=<name> depth=<standard|deep> category=<cat>
    Defaults: username=ghost depth=deep (no category filter).
    """
    import random
    from database import get_connection

    # Parse args
    opts = {'username': 'ghost', 'depth': 'deep', 'category': None}
    for tok in (kwargs.get('args') or '').split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            k = k.strip().lower()
            if k in opts:
                opts[k] = v.strip()

    sql = ("SELECT id, topic, score FROM user_interests "
           "WHERE active=1 AND username=?")
    params = [opts['username']]
    if opts['category']:
        sql += " AND category=?"
        params.append(opts['category'])

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return 'No active research topics — nothing to do.'

    weights = [float(r['score'] or 1.0) for r in rows]
    pick = random.choices(list(rows), weights=weights, k=1)[0]
    topic = pick['topic']
    logger.info(f'[idle_research] picked topic_id={pick["id"]} score={pick["score"]} topic={topic!r}')

    from fridays.research_workflow import run_research
    sid = run_research(topic, depth=opts['depth'], requesting_agent='scholar')
    return f'Started research session {sid} on {topic!r} (depth={opts["depth"]})'


@register('interest_research_update', 'Research one watched topic and email Ghost when new evidence appears', 'knowledge')
def _task_interest_research_update(**kwargs):
    """
    Topic watch research.

    Args are shell-style key/value pairs:
      topic="SAP payroll Australia" depth=standard agent=eight email=ghost

    The task compares evidence fingerprints from earlier sessions for the same
    topic. It sends email only when the new run finds unseen URLs/snippets.
    """
    import shlex
    from utils.db._connection import get_connection

    opts = {
        'topic': '',
        'depth': 'standard',
        'agent': 'eight',
        'email': 'ghost',
    }
    for tok in shlex.split(kwargs.get('args') or ''):
        if '=' not in tok:
            continue
        k, v = tok.split('=', 1)
        k = k.strip().lower()
        if k in opts:
            opts[k] = v.strip()

    topic = opts['topic']
    if not topic:
        return 'No topic supplied. Use: interest_research_update topic="SAP payroll Australia"'
    if opts['depth'] not in ('quick', 'standard', 'deep'):
        opts['depth'] = 'standard'

    before = _evidence_fingerprints_for_topic(topic)

    from fridays.research_workflow import run_research
    sid, summary = run_research(topic, depth=opts['depth'], requesting_agent=opts['agent'])

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT title, source_url, snippet, snippet_hash
               FROM research_evidence
               WHERE session_id=?
               ORDER BY id ASC""",
            (sid,),
        ).fetchall()

    novel = []
    for row in rows:
        fingerprint = _evidence_fingerprint(row['source_url'], row['snippet_hash'])
        if fingerprint not in before:
            novel.append(row)

    if not novel:
        return f'Research session {sid} found no new evidence for {topic!r}; no email sent.'

    sent = _email_research_update(
        topic=topic,
        session_id=sid,
        summary=summary,
        evidence=novel,
        recipient=opts['email'],
        agent=opts['agent'],
    )
    status = 'email sent' if sent else 'email failed'
    return f'Research session {sid} found {len(novel)} new evidence item(s) for {topic!r}; {status}.'


def _evidence_fingerprints_for_topic(topic):
    """Return evidence fingerprints from completed earlier sessions for topic."""
    from utils.db._connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT e.source_url, e.snippet_hash
               FROM research_evidence e
               JOIN research_sessions s ON s.id=e.session_id
               WHERE lower(s.topic)=lower(?)""",
            (topic,),
        ).fetchall()
    return {
        _evidence_fingerprint(row['source_url'], row['snippet_hash'])
        for row in rows
    }


def _evidence_fingerprint(source_url, snippet_hash):
    """Prefer stable source URLs; fall back to snippet hash for URL-less results."""
    source_url = (source_url or '').strip().lower()
    if source_url:
        return f'url:{source_url}'
    return f'snippet:{(snippet_hash or "").strip()}'


def _email_research_update(*, topic, session_id, summary, evidence, recipient, agent):
    """Send a concise research update email. Returns True/False."""
    try:
        from config import GHOST_EMAIL
        to_address = GHOST_EMAIL if recipient in ('', 'ghost') else recipient
        lines = [
            f'Watched topic: {topic}',
            f'Research session: {session_id}',
            f'Collecting agent: {agent}',
            '',
            'New evidence:',
        ]
        for i, row in enumerate(evidence[:10], 1):
            title = (row['title'] or 'Untitled').strip()
            url = (row['source_url'] or '').strip()
            snippet = (row['snippet'] or '').strip().replace('\n', ' ')[:300]
            lines.append(f'{i}. {title}')
            if url:
                lines.append(f'   {url}')
            if snippet:
                lines.append(f'   {snippet}')
        lines.extend(['', 'Summary:', (summary or '').strip()[:3000]])

        from lib.email.email_handler import send_reply
        return bool(send_reply(
            to_address=to_address,
            subject=f'[Swarm Research] New findings: {topic}',
            body='\n'.join(lines),
        ))
    except Exception as e:
        logger.warning(f'[interest_research_update] email failed: {e}')
        return False


@register('landscape_refresh', 'Regenerate system index and landscape JSON', 'maintenance')
def _task_landscape_refresh(**kwargs):
    try:
        from scripts.generate_system_index import generate as gen_md
        from scripts.generate_landscape_json import generate as gen_json
        from scripts.update_docs import generate as gen_ref
        gen_md()
        _, count = gen_json()
        ref = gen_ref()
        return (
            f"Landscape refreshed ({count} entries; "
            f"{ref['routes']} routes → {ref['api_doc']}, "
            f"{ref['shortcuts_doc']})"
        )
    except Exception as e:
        return f'Landscape refresh partial: {e}'


# ── Execution ─────────────────────────────────────────────────────────────────

def run_task(name, args=''):
    """
    Execute a registered task by name.
    Returns (success: bool, output: str).
    """
    entry = TASK_REGISTRY.get(name)
    if not entry:
        known = ', '.join(sorted(TASK_REGISTRY.keys()))
        return False, f'Unknown task: {name!r}. Registered: {known}'

    start = time.time()
    try:
        result = entry['fn'](args=args)
        elapsed = time.time() - start
        output = f'{result} ({elapsed:.1f}s)'
        logger.info(f'[TaskRunner] {name}: {output}')
        _log_run(name, 'ok', output)
        return True, output
    except Exception as e:
        elapsed = time.time() - start
        output = f'Error: {e} ({elapsed:.1f}s)'
        logger.error(f'[TaskRunner] {name}: {output}')
        _log_run(name, 'error', output)
        return False, output


def list_registered():
    """Return list of registered tasks with metadata."""
    return [
        {'name': k, 'description': v['description'], 'category': v['category']}
        for k, v in sorted(TASK_REGISTRY.items())
    ]


def _log_run(task_name, status, output):
    """Write task execution to task_run_log table."""
    try:
        from database import get_connection
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_connection() as conn:
            conn.execute(
                '''INSERT INTO task_run_log (task_name, status, output, run_at)
                   VALUES (?, ?, ?, ?)''',
                (task_name, status, output[:2000], now)
            )
    except Exception as e:
        logger.debug(f'[TaskRunner] log write failed: {e}')
