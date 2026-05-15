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
import os
import sys
import time
import multiprocessing as _mp
from datetime import datetime

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)

logger = logging.getLogger('seven.task_runner')


def _ask_agent_worker(queue, agent, prompt):
    try:
        try:
            import orchestrator
        except Exception:
            from core.pipeline import orchestrator
        answer = orchestrator.ask_agent(agent, prompt)
        queue.put(('ok', str(answer or '').strip()))
    except Exception as exc:
        queue.put(('error', f'{type(exc).__name__}: {exc}'))


def _ask_agent_with_timeout(agent, prompt, timeout_seconds=240):
    """Ask one agent in a killable child process so Tasker cannot hang forever."""
    try:
        timeout_seconds = max(30, min(int(timeout_seconds or 240), 1800))
    except Exception:
        timeout_seconds = 240
    ctx = _mp.get_context('fork')
    queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_ask_agent_worker, args=(queue, agent, prompt))
    proc.start()
    proc.join(timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
        return False, f'[{agent}] timed out after {timeout_seconds}s during relay recovery'
    try:
        status, payload = queue.get_nowait()
    except Exception:
        status, payload = ('error', f'[{agent}] exited without returning recovery notes')
    return status == 'ok', payload


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


@register('relay_recovery_sweep', 'Recover stalled chat relay cards one at a time with Librarian and Duck', 'agents')
def _task_relay_recovery_sweep(**kwargs):
    """
    Sweep open chat relay recovery cards.

    Args:
      limit=1             max cards to inspect; keep this at 1 on this machine
      run_agents=0        set to 1 to actually ask Librarian and Duck
      agents=librarian,duck
      lease_minutes=30    active-review lease duration
      conversation_id=0    optional single thread to recover first
      agent_timeout_seconds=240
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
        'limit': '1',
        'run_agents': '0',
        'agents': 'librarian,duck',
        'lease_minutes': '30',
        'conversation_id': '0',
        'agent_timeout_seconds': '240',
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
    try:
        conversation_id = int(opts.get('conversation_id') or 0) or None
    except Exception:
        conversation_id = None
    try:
        agent_timeout_seconds = max(30, min(int(opts.get('agent_timeout_seconds') or 240), 1800))
    except Exception:
        agent_timeout_seconds = 240

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

    recoveries = lease_chat_relay_recoveries(
        'tasker:relay_recovery_sweep',
        limit=limit,
        lease_seconds=lease_seconds,
        conversation_id=conversation_id,
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
        had_failure = False
        for agent in agents:
            ok, answer = _ask_agent_with_timeout(
                agent,
                prompt,
                timeout_seconds=agent_timeout_seconds,
            )
            if not ok:
                had_failure = True
            outputs.append(f'{agent}: {str(answer or "").strip()[:1200]}')
            if conv_id:
                try:
                    log_message(
                        conv_id,
                        agent,
                        str(answer or '').strip() or f'[{agent}] no recovery review returned',
                        to_agent='user',
                        message_type='relay_recovery_review',
                        tokens_used=0,
                    )
                except Exception as exc:
                    outputs.append(f'{agent}: conversation log skipped: {type(exc).__name__}: {exc}')

        update_chat_relay_recovery_status(
            recovery_id,
            'escalated' if had_failure else 'reviewed',
            summary='; '.join(outputs)[:1000],
        )
        reviewed.append(recovery_id)

    return f'Reviewed {len(reviewed)} relay recoveries: {", ".join(reviewed)}'


@register('watchdog_stall_detection', 'Auto-detect stuck processing tasks, auto-pause them, and create watchdog repair lessons. Run every 5-10 minutes.', 'monitoring')
def _task_watchdog_stall_detection(**kwargs):
    """Periodic stall detector with optional auto-recovery."""
    import shlex
    from utils.db.watchdog_lessons import detect_and_record_stalls

    opts = {'max_age_minutes': '15', 'limit': '20', 'auto_recover': 'true'}
    for tok in shlex.split(kwargs.get('args') or ''):
        if '=' not in tok:
            continue
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
    auto_recover = str(opts.get('auto_recover', 'true')).strip().lower() in {'true', '1', 'yes', 'on'}

    lessons = detect_and_record_stalls(
        max_age_minutes=max_age,
        limit=lim,
        auto_recover=auto_recover,
    )
    count = len(lessons)
    if count == 0:
        return f'No stalled tasks detected (>{max_age} min)'
    action = 'created repair lessons and attempted recovery' if auto_recover else 'created repair lessons'
    return f'{action} for {count} stalled task(s) (>{max_age} min)'


@register('watchdog_deos_cycle', 'Run Watchdog/Seven DEOS control-plane cycle: decide, execute, operate, sustain.', 'monitoring')
def _task_watchdog_deos_cycle(**kwargs):
    from utils.watchdog_deos import run_deos_cycle_summary
    return run_deos_cycle_summary(kwargs.get('args') or '')


@register('local_agent_work_cycle', 'Let one local agent claim and execute one Studio step with bounded runtime.', 'agents')
def _task_local_agent_work_cycle(**kwargs):
    from utils.watchdog_deos import run_deos_cycle_summary
    args = str(kwargs.get('args') or '').strip()
    merged = (
        'prewarm=1 warm_timeout_seconds=60 execute_recovery=0 '
        'execute_work=1 work_timeout_seconds=900 '
        + args
    ).strip()
    return run_deos_cycle_summary(merged)


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
        'You are recovering a stalled chat relay card. Treat this as an active task board item, not a passive review.',
        f"Recovery ID: {recovery.get('recovery_id')}",
        f"Conversation: #{recovery.get('conversation_id')}",
        f"Stalled agent: {recovery.get('stalled_agent')}",
        f"Summary: {recovery.get('summary')}",
        '',
        'Operating rules:',
        '- Work one recovery at a time; finish this card or name the blocker before moving on.',
        '- Continue from the visible thread tail and stage trace. Do not restart the task from scratch.',
        '- If the original request asked for a simple code/config/doc change, identify the exact next patch and verification command.',
        '- Write back where recovery falls over: missing context, runtime timeout, model failure, unsafe action, or test failure.',
        '- Keep notes concise and user-visible. Do not expose private chain-of-thought.',
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
    lines.append('Return concise recovery notes with: current state, exact next action, proof to run, blocker if any, and who should continue.')
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


@register('documentation_governance_sweep', 'Audit loose docs/data files and publish findings to Studio/KC', 'knowledge')
def _task_documentation_governance_sweep(**kwargs):
    from scripts.studio_data_governance import apply_governance
    result = apply_governance()
    counts = result.get('inventory_counts') or {}
    project_id = result.get('project_id') or '?'
    proposal_id = result.get('proposal_id') or '?'
    return (
        f"Governance sweep updated {project_id}/{proposal_id}: "
        f"{counts.get('loose_document', 0)} loose docs, "
        f"{counts.get('sandpit_working_note', 0)} sandpit notes, "
        f"{counts.get('duplicate_or_legacy_db', 0)} legacy DBs"
    )


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
        'min_quality': '0.45',
        'min_novelty': '0.35',
        'min_score': '0.50',
        'max_items': '10',
        'historical_years': '5',
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
    try:
        min_quality = max(0.0, min(float(opts.get('min_quality') or 0.45), 1.0))
    except Exception:
        min_quality = 0.45
    try:
        min_novelty = max(0.0, min(float(opts.get('min_novelty') or 0.35), 1.0))
    except Exception:
        min_novelty = 0.35
    try:
        min_score = max(0.0, min(float(opts.get('min_score') or 0.50), 1.0))
    except Exception:
        min_score = 0.50
    try:
        max_items = max(1, min(int(opts.get('max_items') or 10), 25))
    except Exception:
        max_items = 10
    try:
        historical_years = max(1, min(int(opts.get('historical_years') or 5), 50))
    except Exception:
        historical_years = 5

    prior_context = _watched_topic_prior_context(topic)

    from fridays.research_workflow import run_research
    sid, summary = run_research(topic, depth=opts['depth'], requesting_agent=opts['agent'])

    with get_connection() as conn:
        _ensure_watched_topic_schema(conn)
        rows = conn.execute(
            """SELECT title, source_url, snippet, snippet_hash
               FROM research_evidence
               WHERE session_id=?
               ORDER BY id ASC""",
            (sid,),
        ).fetchall()

        assessed = _rank_watched_topic_evidence(
            topic,
            rows,
            prior_context=prior_context,
            min_quality=min_quality,
            min_novelty=min_novelty,
            min_score=min_score,
            historical_years=historical_years,
        )
        _record_watched_topic_assessments(
            conn,
            topic=topic,
            session_id=sid,
            assessed=assessed,
        )

    qualified = [item for item in assessed if item.get('qualified')]
    if not qualified:
        new_count = sum(1 for item in assessed if item.get('is_new'))
        return (
            f'Research session {sid} found {new_count} new evidence item(s) for {topic!r}, '
            f'but none met quality/novelty thresholds; no email sent.'
        )

    historical_refs = [
        item for item in assessed
        if item.get('is_new') and item.get('is_historical')
    ][:3]
    sent = _email_research_update(
        topic=topic,
        session_id=sid,
        summary=summary,
        evidence=qualified[:max_items],
        historical_refs=historical_refs,
        recipient=opts['email'],
        agent=opts['agent'],
    )
    if sent:
        with get_connection() as conn:
            _mark_watched_topic_notified(conn, topic, sid, qualified[:max_items])
    status = 'email sent' if sent else 'email failed'
    return (
        f'Research session {sid} found {len(qualified)} qualified new evidence item(s) '
        f'for {topic!r}; {status}.'
    )


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


def _watched_topic_prior_context(topic):
    """Return known fingerprints and snippets before a watched-topic run."""
    from utils.db._connection import get_connection

    with get_connection() as conn:
        _ensure_watched_topic_schema(conn)
        evidence_rows = conn.execute(
            """SELECT e.source_url, e.snippet_hash, e.snippet
               FROM research_evidence e
               JOIN research_sessions s ON s.id=e.session_id
               WHERE lower(s.topic)=lower(?)
               ORDER BY e.id DESC
               LIMIT 300""",
            (topic,),
        ).fetchall()
        watched_rows = conn.execute(
            """SELECT evidence_fingerprint, snippet
               FROM watched_topic_evidence
               WHERE topic_key=?
               ORDER BY updated_at DESC
               LIMIT 300""",
            (_watched_topic_key(topic),),
        ).fetchall()

    fingerprints = {
        _evidence_fingerprint(row['source_url'], row['snippet_hash'])
        for row in evidence_rows
    }
    fingerprints.update(
        str(row['evidence_fingerprint'] or '').strip()
        for row in watched_rows
        if str(row['evidence_fingerprint'] or '').strip()
    )
    snippets = [
        str(row['snippet'] or '')
        for row in evidence_rows
        if str(row['snippet'] or '').strip()
    ]
    snippets.extend(
        str(row['snippet'] or '')
        for row in watched_rows
        if str(row['snippet'] or '').strip()
    )
    return {'fingerprints': fingerprints, 'snippets': snippets[:300]}


def _evidence_fingerprint(source_url, snippet_hash):
    """Prefer stable source URLs; fall back to snippet hash for URL-less results."""
    source_url = (source_url or '').strip().lower()
    if source_url:
        return f'url:{source_url}'
    return f'snippet:{(snippet_hash or "").strip()}'


def _watched_topic_key(topic):
    import re
    return re.sub(r'\s+', ' ', str(topic or '').strip().lower())


def _ensure_watched_topic_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watched_topic_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            session_id INTEGER DEFAULT 0,
            source_url TEXT DEFAULT '',
            title TEXT DEFAULT '',
            snippet TEXT DEFAULT '',
            quality_score REAL DEFAULT 0,
            novelty_score REAL DEFAULT 0,
            combined_score REAL DEFAULT 0,
            qualified INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0,
            review_status TEXT DEFAULT '',
            review_note TEXT DEFAULT '',
            evidence_date TEXT DEFAULT '',
            recency_score REAL DEFAULT 0,
            recency_label TEXT DEFAULT '',
            is_historical INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(topic_key, evidence_fingerprint)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watched_topic_evidence_topic ON watched_topic_evidence(topic_key, updated_at)"
    )
    for col_ddl in [
        "ALTER TABLE watched_topic_evidence ADD COLUMN review_status TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN review_note TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN evidence_date TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN recency_score REAL DEFAULT 0",
        "ALTER TABLE watched_topic_evidence ADD COLUMN recency_label TEXT DEFAULT ''",
        "ALTER TABLE watched_topic_evidence ADD COLUMN is_historical INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(col_ddl)
        except Exception:
            pass


def _rank_watched_topic_evidence(
    topic,
    rows,
    *,
    prior_context,
    min_quality,
    min_novelty,
    min_score,
    historical_years=5,
):
    assessed = []
    seen = set()
    for row in rows:
        item = dict(row)
        fingerprint = _evidence_fingerprint(item.get('source_url'), item.get('snippet_hash'))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        quality = _source_quality_score(item, topic)
        novelty = _novelty_score(item, fingerprint, prior_context)
        date_meta = _evidence_date_metadata(item, historical_years=historical_years)
        recency = float(date_meta.get('recency_score') or 0.0)
        combined = round((quality * 0.40) + (novelty * 0.40) + (recency * 0.20), 3)
        is_new = fingerprint not in prior_context.get('fingerprints', set())
        qualified = bool(
            is_new
            and not date_meta.get('is_historical')
            and quality >= min_quality
            and novelty >= min_novelty
            and combined >= min_score
        )
        item.update({
            'fingerprint': fingerprint,
            'quality_score': round(quality, 3),
            'novelty_score': round(novelty, 3),
            'combined_score': combined,
            'evidence_date': date_meta.get('evidence_date', ''),
            'recency_score': round(recency, 3),
            'recency_label': date_meta.get('recency_label', ''),
            'is_historical': bool(date_meta.get('is_historical')),
            'is_new': is_new,
            'qualified': qualified,
            'reason': _watched_topic_score_reason(
                is_new,
                quality,
                novelty,
                combined,
                qualified,
                recency=recency,
                recency_label=date_meta.get('recency_label', ''),
                is_historical=bool(date_meta.get('is_historical')),
            ),
        })
        assessed.append(item)
    assessed.sort(key=lambda item: (
        not item.get('qualified'),
        item.get('is_historical', False),
        -item.get('combined_score', 0),
        -item.get('recency_score', 0),
        -item.get('quality_score', 0),
    ))
    return assessed


def _source_quality_score(row, topic=''):
    from urllib.parse import urlparse

    url = str(row.get('source_url') or '').strip()
    title = str(row.get('title') or '').strip()
    snippet = str(row.get('snippet') or '').strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    path = parsed.path.lower()
    score = 0.25
    if url.startswith('https://'):
        score += 0.08
    if host:
        score += 0.12
    if host.endswith(('.gov', '.gov.au', '.edu', '.edu.au')):
        score += 0.35
    if any(part in host for part in ('sap.com', 'ato.gov.au', 'fairwork.gov.au', 'servicesaustralia.gov.au')):
        score += 0.25
    topic_tokens = {
        token
        for token in str(topic or '').lower().replace('-', ' ').split()
        if len(token) >= 4
    }
    if topic_tokens and any(token in host for token in topic_tokens):
        score += 0.12
    if any(part in path for part in ('/docs', '/documentation', '/help', '/support', '/news', '/media', '/law', '/payroll')):
        score += 0.08
    if len(title) >= 12:
        score += 0.06
    if len(snippet) >= 80:
        score += 0.08
    if any(part in host for part in ('reddit.', 'facebook.', 'x.com', 'twitter.', 'quora.', 'medium.')):
        score -= 0.18
    if not url and len(snippet) < 120:
        score -= 0.12
    return max(0.0, min(round(score, 3), 1.0))


def _novelty_score(row, fingerprint, prior_context):
    if fingerprint in prior_context.get('fingerprints', set()):
        return 0.0
    current = _text_tokens(' '.join([
        str(row.get('title') or ''),
        str(row.get('snippet') or ''),
    ]))
    prior_snippets = prior_context.get('snippets') or []
    if not current or not prior_snippets:
        return 1.0
    max_similarity = 0.0
    for snippet in prior_snippets[:80]:
        prior = _text_tokens(snippet)
        if not prior:
            continue
        union = current | prior
        if not union:
            continue
        similarity = len(current & prior) / len(union)
        if similarity > max_similarity:
            max_similarity = similarity
    return max(0.0, min(round(1.0 - max_similarity, 3), 1.0))


def _text_tokens(text):
    import re
    stop = {'about', 'after', 'also', 'and', 'are', 'from', 'into', 'that', 'the', 'this', 'with', 'your'}
    return {
        token
        for token in re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).split()
        if len(token) >= 3 and token not in stop
    }


def _evidence_date_metadata(row, *, historical_years=5):
    """Extract a rough evidence date and recency score from title/snippet/URL."""
    import re
    from datetime import datetime

    current_year = datetime.now().year
    text = ' '.join([
        str(row.get('title') or ''),
        str(row.get('snippet') or ''),
        str(row.get('source_url') or ''),
    ])
    exact_match = re.search(r'\b((?:19|20)\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b', text)
    years = [
        int(match)
        for match in re.findall(r'\b((?:19|20)\d{2})\b', text)
        if 1990 <= int(match) <= current_year + 1
    ]
    if not years:
        return {
            'evidence_date': '',
            'recency_score': 0.65,
            'recency_label': 'undated',
            'is_historical': False,
        }

    year = max(years)
    evidence_date = str(year)
    if exact_match and int(exact_match.group(1)) == year:
        evidence_date = (
            f"{int(exact_match.group(1)):04d}-"
            f"{int(exact_match.group(2)):02d}-"
            f"{int(exact_match.group(3)):02d}"
        )
    age = max(0, current_year - year)
    if age <= 0:
        recency = 0.98
        label = f'current {year}'
    elif age == 1:
        recency = 0.90
        label = f'last year {year}'
    elif age <= 3:
        recency = 0.78
        label = f'recent {year}'
    elif age <= historical_years:
        recency = 0.58
        label = f'aging {year}'
    elif age <= 10:
        recency = 0.32
        label = f'historical {year}'
    else:
        recency = 0.12
        label = f'long-ago {year}'
    return {
        'evidence_date': evidence_date,
        'recency_score': recency,
        'recency_label': label,
        'is_historical': age > historical_years,
    }


def _watched_topic_score_reason(
    is_new,
    quality,
    novelty,
    combined,
    qualified,
    *,
    recency=0.0,
    recency_label='',
    is_historical=False,
):
    if qualified:
        return (
            f'qualified: quality={quality:.2f} novelty={novelty:.2f} '
            f'recency={recency:.2f} score={combined:.2f} date={recency_label or "unknown"}'
        )
    if not is_new:
        return 'duplicate: already known fingerprint'
    if is_historical:
        return (
            f'historical reference: quality={quality:.2f} novelty={novelty:.2f} '
            f'recency={recency:.2f} score={combined:.2f} date={recency_label or "unknown"}'
        )
    return (
        f'filtered: quality={quality:.2f} novelty={novelty:.2f} '
        f'recency={recency:.2f} score={combined:.2f} date={recency_label or "unknown"}'
    )


def _record_watched_topic_assessments(conn, *, topic, session_id, assessed):
    _ensure_watched_topic_schema(conn)
    topic_key = _watched_topic_key(topic)
    for item in assessed:
        conn.execute(
            """
            INSERT INTO watched_topic_evidence
                (topic_key, topic, evidence_fingerprint, session_id, source_url,
                 title, snippet, quality_score, novelty_score, combined_score,
                 qualified, notified, evidence_date, recency_score, recency_label,
                 is_historical, reason, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(topic_key, evidence_fingerprint) DO UPDATE SET
                session_id=excluded.session_id,
                source_url=excluded.source_url,
                title=excluded.title,
                snippet=excluded.snippet,
                quality_score=excluded.quality_score,
                novelty_score=excluded.novelty_score,
                combined_score=excluded.combined_score,
                qualified=excluded.qualified,
                evidence_date=excluded.evidence_date,
                recency_score=excluded.recency_score,
                recency_label=excluded.recency_label,
                is_historical=excluded.is_historical,
                reason=excluded.reason,
                updated_at=datetime('now')
            """,
            (
                topic_key,
                topic,
                item.get('fingerprint') or '',
                int(session_id or 0),
                str(item.get('source_url') or '')[:1000],
                str(item.get('title') or '')[:500],
                str(item.get('snippet') or '')[:1000],
                float(item.get('quality_score') or 0),
                float(item.get('novelty_score') or 0),
                float(item.get('combined_score') or 0),
                1 if item.get('qualified') else 0,
                str(item.get('evidence_date') or '')[:32],
                float(item.get('recency_score') or 0),
                str(item.get('recency_label') or '')[:80],
                1 if item.get('is_historical') else 0,
                str(item.get('reason') or '')[:500],
            ),
        )
    conn.commit()


def _mark_watched_topic_notified(conn, topic, session_id, evidence):
    _ensure_watched_topic_schema(conn)
    topic_key = _watched_topic_key(topic)
    for item in evidence:
        fingerprint = item.get('fingerprint') or _evidence_fingerprint(item.get('source_url'), item.get('snippet_hash'))
        conn.execute(
            """
            UPDATE watched_topic_evidence
            SET notified=1, session_id=?, updated_at=datetime('now')
            WHERE topic_key=? AND evidence_fingerprint=?
            """,
            (int(session_id or 0), topic_key, fingerprint),
        )
    conn.commit()


def _row_value(row, key, default=''):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _email_research_update(*, topic, session_id, summary, evidence, recipient, agent, historical_refs=None):
    """Send a concise research update email. Returns True/False."""
    try:
        from config import GHOST_EMAIL
        to_address = GHOST_EMAIL if recipient in ('', 'ghost') else recipient
        historical_refs = historical_refs or []
        review_url = _tasker_review_url(topic)
        lines = [
            f'Watched topic: {topic}',
            f'Research session: {session_id}',
            f'Collecting agent: {agent}',
            f'Review in Studio: {review_url}',
            '',
            'Why this email:',
            '- These findings passed the current quality/novelty/date gate.',
            '- Older material is kept in Knowledge/Studio evidence review as historical reference.',
            '- Use Studio Tasker evidence review to promote, ignore, or mark findings as emailed.',
            '',
            'Current and relevant evidence:',
        ]
        for i, row in enumerate(evidence[:10], 1):
            title = (_row_value(row, 'title') or 'Untitled').strip()
            url = (_row_value(row, 'source_url') or '').strip()
            snippet = (_row_value(row, 'snippet') or '').strip().replace('\n', ' ')[:300]
            lines.append(f'{i}. {title}')
            if _row_value(row, 'combined_score', None) is not None:
                lines.append(
                    '   '
                    f"score={float(_row_value(row, 'combined_score', 0)):.2f} "
                    f"quality={float(_row_value(row, 'quality_score', 0)):.2f} "
                    f"novelty={float(_row_value(row, 'novelty_score', 0)):.2f} "
                    f"recency={float(_row_value(row, 'recency_score', 0)):.2f} "
                    f"date={_row_value(row, 'recency_label', 'undated') or 'undated'}"
                )
            if url:
                lines.append(f'   {url}')
            if snippet:
                lines.append(f'   {snippet}')
        if historical_refs:
            lines.extend(['', 'Historical reference / fun fact from long ago:'])
            for i, row in enumerate(historical_refs[:3], 1):
                title = (_row_value(row, 'title') or 'Untitled').strip()
                url = (_row_value(row, 'source_url') or '').strip()
                label = _row_value(row, 'recency_label', '') or _row_value(row, 'evidence_date', '') or 'older reference'
                lines.append(f'{i}. {title} ({label})')
                if url:
                    lines.append(f'   {url}')
        lines.extend(['', 'Summary:', (summary or '').strip()[:3000]])

        from lib.email.email_handler import send_reply
        return bool(send_reply(
            to_address=to_address,
            subject=f'[Swarm Research] Current update: {topic}',
            body='\n'.join(lines),
        ))
    except Exception as e:
        logger.warning(f'[interest_research_update] email failed: {e}')
        return False


def _tasker_review_url(topic):
    import os
    from urllib.parse import quote
    base = os.environ.get('SWARM_UI_URL', 'http://127.0.0.1:5050/ui').rstrip('/')
    return f'{base}?view=tasker&watch_topic={quote(str(topic or ""))}'


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


# ── PACKET-10B: Curiosity organ ──────────────────────────────────────────────

@register('curiosity_digest', 'PACKET-10B: prune old curiosity questions and summarise open ones', 'memory')
def _task_curiosity_digest(**kwargs):
    """Daily curiosity housekeeping.

    1. Prune `open` questions older than 30 days → `expired`.
    2. Return a single-line summary of the current open backlog.

    No external delivery yet — the answer surface lives in chat / Studio.
    Keeps the organ self-maintaining so the queue can't grow unbounded.
    """
    from core import curiosity
    pruned = curiosity.prune(max_age_days=30)
    s = curiosity.stats()
    top = s.get('top_open') or []
    head = ''
    if top:
        h0 = top[0]
        head = f" · top: q#{h0['id']} ({h0['asked_by']}) sal={h0['salience']:.2f}"
    return (
        f"curiosity_digest ok · open={s.get('open', 0)} "
        f"answered={s.get('answered', 0)} "
        f"dismissed={s.get('dismissed', 0)} "
        f"expired={s.get('expired', 0)} "
        f"pruned={pruned}{head}"
    )


@register('seven_daily_brief', "Seven's daily prose narrative — beliefs, callouts, curiosity, hygiene", 'memory')
def _task_seven_daily_brief(**kwargs):
    """Compose a real prose narrative of Seven's day.

    Pulls from seven_episodes, seven_beliefs, curiosity_questions,
    seven_learnings, seven_callouts and the bullshit detector.
    Writes audit/seven_daily_<date>.md and returns a one-line summary.
    """
    from agents.seven import daily_brief
    out = daily_brief.compose_daily()
    return f"seven_daily_brief ok · {out['date']} · {out['summary']} · path={out['path']}"


@register('money_hub_daily_newsletter', 'Money Hub daily newsletter into Knowledge Center', 'finance')
def _task_money_hub_daily_newsletter(**kwargs):
    from core import market_watch
    return market_watch.run()


# ── PACKET-10A: Backup & Trace Hardening ─────────────────────────────────────

@register('vortex_heartbeat', 'PACKET-10A Vortex liveness: emit a workflow checkpoint so time_checkpoints stays fresh', 'maintenance')
def _task_vortex_heartbeat(**kwargs):
    """Periodic Vortex tick.

    Vortex is otherwise event-driven (proposal transitions, alm actions).
    On quiet days it can go silent for >24h, which makes 'has Vortex died?'
    indistinguishable from 'is the swarm just idle?'. This task forces a
    known cadence so the freshness invariant has real signal.
    """
    from datetime import UTC, datetime
    import json
    from core.time_machine import _vortex_maybe_git_sync, time_wizard

    full_state = time_wizard.capture_workflow_state()
    safe_name = f"vortex-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-heartbeat"
    checkpoint_id = time_wizard.create_checkpoint(
        safe_name,
        'tasker',
        'Periodic Vortex liveness checkpoint (PACKET-10A).',
        full_state,
    )
    time_wizard.record_event(
        agent='tasker',
        action='vortex_heartbeat',
        event_type='checkpoint',
        target=safe_name,
        details={'checkpoint_id': checkpoint_id, 'counts': full_state.get('counts', {})},
    )
    time_wizard._write_activity_log(
        'checkpoint_created',
        f'{safe_name} | agent=tasker | counts={json.dumps(full_state.get("counts", {}), ensure_ascii=True)}',
    )
    git_sync = _vortex_maybe_git_sync(agent='tasker', reason='vortex_heartbeat')
    if git_sync.get('status') in {'synced', 'commit-only', 'blocked'}:
        time_wizard._write_activity_log(
            'git_sync',
            json.dumps(git_sync, ensure_ascii=True),
        )
    r = {
        'checkpoint_id': checkpoint_id,
        'checkpoint_name': safe_name,
        'counts': full_state.get('counts', {}),
        'git_tags': {},
        'git_sync': git_sync,
    }
    counts = r.get('counts', {})
    sync = r.get('git_sync') or {}
    return (
        f"vortex_heartbeat ok · {r.get('checkpoint_name')} · "
        f"props={counts.get('work_proposals', '?')} "
        f"decisions={counts.get('decisions', '?')} "
        f"queue={counts.get('queue', '?')} · "
        f"git_sync={sync.get('status', 'unknown')} "
        f"{sync.get('change_count', 0)}/{sync.get('threshold', '?')}"
    )


@register('swarm_backup', 'PACKET-10A backup: tarball to local + NTFS + USB (skips unreachable)', 'maintenance')
def _task_swarm_backup(**kwargs):
    """Run scripts/backup_swarm.sh against one or all targets.

    Args (whitespace-separated key=value):
      target=all|local|ntfs|usb   (default: all)
    """
    import shlex
    import subprocess

    target = 'all'
    for tok in shlex.split(kwargs.get('args') or ''):
        if '=' in tok:
            k, v = tok.split('=', 1)
            if k.strip().lower() == 'target' and v.strip() in ('all', 'local', 'ntfs', 'usb'):
                target = v.strip()

    proc = subprocess.run(
        ['/usr/bin/env', 'bash', os.path.join(_SWARM_ROOT, 'scripts/backup_swarm.sh'), target],
        capture_output=True,
        text=True,
        timeout=900,
    )
    out = (proc.stdout or '') + (proc.stderr or '')
    tail = '\n'.join(out.strip().splitlines()[-12:])
    if proc.returncode == 0:
        return f'swarm_backup ok (target={target})\n{tail}'
    return f'swarm_backup FAILED rc={proc.returncode} (target={target})\n{tail}'


@register('swarm_backup_verify', 'PACKET-10A backup: verify newest local tarball (extract + integrity_check)', 'maintenance')
def _task_swarm_backup_verify(**kwargs):
    import subprocess

    proc = subprocess.run(
        ['/usr/bin/env', 'python3', os.path.join(_SWARM_ROOT, 'scripts/backup_verify.py'), 'extract'],
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = (proc.stdout or '') + (proc.stderr or '')
    tail = '\n'.join(out.strip().splitlines()[-10:])
    if proc.returncode == 0:
        return f'swarm_backup_verify ok\n{tail}'
    return f'swarm_backup_verify FAILED rc={proc.returncode}\n{tail}'


@register('chat_smoke_probe',
          'Periodic chat+AI round-trip smoke probe (S-1D88D439EE05): pings the local LLM and verifies a non-empty reply',
          'monitoring')
def _task_chat_smoke_probe(**kwargs):
    """Smoke-test the chat pipeline end-to-end without hitting Gmail.

    Args (all optional):
      prompt=...      override prompt (default: "ping; reply with the word OK only")
      agent=llama     which agent to ping (default: llama)
      timeout=15      seconds to wait for a reply
    """
    import time as _t

    prompt = kwargs.get('prompt') or 'ping; reply with the word OK only'
    agent = (kwargs.get('agent') or 'llama').strip().lower()
    try:
        timeout = max(2, min(int(kwargs.get('timeout', 15)), 120))
    except (TypeError, ValueError):
        timeout = 15

    started = _t.time()
    reply = ''
    err = ''
    try:
        try:
            from fridays import orchestrator as _orch
        except ImportError:
            from core.pipeline import orchestrator as _orch
        reply = _orch.ask_agent(agent, prompt) or ''
    except Exception as exc:
        err = f'{type(exc).__name__}: {exc}'
    elapsed_ms = int((_t.time() - started) * 1000)

    ok = bool(reply.strip()) and not err
    try:
        from utils.db._connection import get_connection
        with get_connection() as _c:
            _c.execute(
                "INSERT INTO task_run_log (task_name, status, output, run_at, duration_ms) "
                "VALUES (?, ?, ?, datetime('now'), ?)",
                ('chat_smoke_probe', 'ok' if ok else 'error',
                 (reply or err)[:500], elapsed_ms),
            )
            _c.commit()
    except Exception:
        pass

    # Emit a CHAT spine event so Traced surfaces historical latency at a glance
    # (MD-FEATURE-B13F80E2C988). Best-effort; never blocks the probe result.
    try:
        from core import spine as _spine
        _spine.log(
            _spine.EventKind.CHAT,
            f'chat_smoke_probe {"ok" if ok else "FAILED"} agent={agent} {elapsed_ms}ms',
            severity=_spine.Severity.INFO if ok else _spine.Severity.WARN,
            source='chat_smoke_probe',
            agent=agent,
            payload={
                'ok': bool(ok),
                'agent': agent,
                'latency_ms': elapsed_ms,
                'reply_len': len(reply or ''),
                'err': (err or '')[:200],
            },
        )
    except Exception:
        pass

    if ok:
        return f'chat_smoke_probe ok agent={agent} latency_ms={elapsed_ms} reply={reply[:80]!r}'
    return f'chat_smoke_probe FAILED agent={agent} elapsed_ms={elapsed_ms} err={err or "empty reply"}'


# ── Execution ─────────────────────────────────────────────────────────────────

def run_task(name, args=''):
    """
    Execute a registered task by name.
    Returns (success: bool, output: str).

    2026-05-02 (S-F4DC817B17) — if the calling scheduled_tasks row is
    linked to a project step (project_id + project_step_id), an evidence
    row is auto-created in project_step_evidence after the run.
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
        _log_run(name, 'ok', output, duration_ms=int(elapsed * 1000),
                 details={'category': entry.get('category', ''), 'args': args})
        _record_step_evidence(name, args, 'ok', output)
        _record_scorecard_outcome(name, args, True, output, entry.get('category', ''))
        return True, output
    except Exception as e:
        elapsed = time.time() - start
        output = f'Error: {e} ({elapsed:.1f}s)'
        logger.error(f'[TaskRunner] {name}: {output}')
        _log_run(name, 'error', output, duration_ms=int(elapsed * 1000),
                 details={'category': entry.get('category', ''), 'args': args,
                          'exception': type(e).__name__})
        _record_step_evidence(name, args, 'error', output)
        _record_scorecard_outcome(name, args, False, output, entry.get('category', ''))
        return False, output


def list_registered():
    """Return list of registered tasks with metadata.

    2026-05-02 (S-4A136CB7F8) — each entry now includes the function's
    inspectable parameters so the Tasker UI can show what `args=` is expected.
    """
    import inspect as _inspect
    out = []
    for name, v in sorted(TASK_REGISTRY.items()):
        params = []
        try:
            sig = _inspect.signature(v['fn'])
            for pname, p in sig.parameters.items():
                params.append({
                    'name': pname,
                    'kind': str(p.kind),
                    'default': (None if p.default is _inspect.Parameter.empty
                                else repr(p.default)),
                    'has_default': p.default is not _inspect.Parameter.empty,
                })
        except Exception:
            params = []
        out.append({
            'name': name,
            'description': v.get('description', ''),
            'category': v.get('category', ''),
            'params': params,
        })
    return out


def _log_run(task_name, status, output, duration_ms=0, details=None):
    """Write task execution to task_run_log table.
    duration_ms (S-5E508B5488) and details_json (S-15087BF900) are persisted
    when the columns exist; older DBs gracefully ignore them."""
    try:
        from database import get_connection
        import json as _json
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details_str = ''
        if details:
            try:
                details_str = _json.dumps(details, default=str)[:4000]
            except Exception:
                details_str = ''
        with get_connection() as conn:
            cols = {row[1] for row in conn.execute(
                "PRAGMA table_info(task_run_log)").fetchall()}
            if 'duration_ms' in cols and 'details_json' in cols:
                conn.execute(
                    'INSERT INTO task_run_log '
                    '(task_name, status, output, run_at, duration_ms, details_json) '
                    'VALUES (?, ?, ?, ?, ?, ?)',
                    (task_name, status, output[:2000], now,
                     int(duration_ms or 0), details_str)
                )
            else:
                conn.execute(
                    'INSERT INTO task_run_log (task_name, status, output, run_at) '
                    'VALUES (?, ?, ?, ?)',
                    (task_name, status, output[:2000], now)
                )
    except Exception as e:
        logger.debug(f'[TaskRunner] log write failed: {e}')


def _record_step_evidence(task_name, args, status, output):
    """If the most recent matching scheduled_tasks row is linked to a
    project step, write a project_step_evidence row.
    Best-effort only; never raises into the caller.

    2026-05-02 (S-F4DC817B17)."""
    try:
        try:
            from utils.db._connection import get_connection
        except Exception:
            from database import get_connection
        with get_connection() as conn:
            cols = {row[1] for row in conn.execute(
                "PRAGMA table_info(scheduled_tasks)").fetchall()}
            if 'project_id' not in cols or 'project_step_id' not in cols:
                return
            row = conn.execute(
                "SELECT project_id, project_step_id FROM scheduled_tasks "
                "WHERE action_type='python' AND action_data=? AND project_id != '' "
                "ORDER BY id DESC LIMIT 1",
                (f'{task_name} {args}'.strip(),)
            ).fetchone()
            if not row and args:
                row = conn.execute(
                    "SELECT project_id, project_step_id FROM scheduled_tasks "
                    "WHERE action_type='python' AND action_data LIKE ? "
                    "AND project_id != '' ORDER BY id DESC LIMIT 1",
                    (f'{task_name}%',)
                ).fetchone()
            if not row:
                return
            project_id, step_id = row
            if not (project_id and step_id):
                return
            summary = (output or '')[:500]
            conn.execute(
                "INSERT INTO project_step_evidence "
                "(project_id, step_id, source_type, source_ref, summary, status) "
                "VALUES (?, ?, 'task', ?, ?, ?)",
                (project_id, step_id, task_name, summary, status)
            )
    except Exception as e:
        logger.debug(f'[TaskRunner] step evidence skipped: {e}')


def _record_scorecard_outcome(task_name, args, success, output, category=''):
    """Best-effort learning hook for meaningful Tasker runs."""
    try:
        from core.agent_scorecards import record_task_outcome
        updates = record_task_outcome(
            task_name,
            args=args,
            success=success,
            output=output,
            category=category,
        )
        if updates:
            logger.info(f'[TaskRunner] scorecard updates from {task_name}: {updates}')
    except Exception as e:
        logger.debug(f'[TaskRunner] scorecard outcome skipped for {task_name}: {e}')
