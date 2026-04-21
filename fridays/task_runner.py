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


@register('landscape_refresh', 'Regenerate system index and landscape JSON', 'maintenance')
def _task_landscape_refresh(**kwargs):
    try:
        from scripts.generate_system_index import generate as gen_md
        from scripts.generate_landscape_json import generate as gen_json
        gen_md()
        _, count = gen_json()
        return f'Landscape refreshed ({count} entries)'
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
