"""Which agent is the single local worker, and which model it runs.

Defaults to fred on mistral-small:24b. To plug in another agent, set SWARM_WORKER_AGENT / SWARM_WORKER_MODEL
or write runtime/worker_agent.txt and runtime/worker_model.txt (scripts/swap_worker.py does this).
Delete the two files to go back. This module must stay free of project imports: low-level modules load it.
"""
import os
import re

_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WORKER = 'fred'
_NAME_RE = re.compile(r'[a-z][a-z0-9_]{1,23}')


def _setting(env_name: str, file_name: str) -> str:
    value = os.environ.get(env_name, '').strip()
    if not value:
        try:
            with open(os.path.join(_ROOT, 'runtime', file_name), encoding='utf-8') as handle:
                value = handle.read().strip()
        except OSError:
            value = ''
    return value


def _worker_name() -> str:
    name = _setting('SWARM_WORKER_AGENT', 'worker_agent.txt').lower()
    return name if _NAME_RE.fullmatch(name) else DEFAULT_WORKER


WORKER_AGENT = _worker_name()
WORKER_MODEL = _setting('SWARM_WORKER_MODEL', 'worker_model.txt') if WORKER_AGENT != DEFAULT_WORKER else ''


def _num_ctx() -> int:
    raw = _setting('SWARM_WORKER_NUM_CTX', 'worker_num_ctx.txt')
    try:
        return max(2048, min(int(raw), 32768)) if raw else 8192
    except ValueError:
        return 8192


# The worker's prompt alone is about 3,800 tokens, so the old 4096 window left no room for history or skill output.
WORKER_NUM_CTX = _num_ctx()


def is_worker_agent(name) -> bool:
    return str(name or '').strip().lower() == WORKER_AGENT


def worker_display_name() -> str:
    return WORKER_AGENT.replace('_', ' ').title()
