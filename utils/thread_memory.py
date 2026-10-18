"""Verified facts per conversation thread, recorded from real skill results.

A fact exists only if a skill returned it, so carry-over never contains guesses.
All functions are best-effort: a failure here must never break a chat turn.
"""
import logging
import re

logger = logging.getLogger(__name__)

_MAX_ARGS_CHARS = 200
_MAX_RESULT_CHARS = 300
_PROPOSAL_ID_RE = re.compile(r'proposal_id=([A-Za-z0-9_\-]+)')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    skill TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '',
    ok INTEGER NOT NULL,
    result TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_INDEX = "CREATE INDEX IF NOT EXISTS idx_thread_facts_conv ON thread_facts(conversation_id, id)"


def ensure_tables(conn):
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)
    conn.execute(_STATE_SCHEMA)


_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_state (
    conversation_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    summary TEXT NOT NULL,
    open_tasks TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, agent)
)
"""
_MAX_BLOCK_CHARS = 1400
_HAT_AGENTS = frozenset({'gemma', 'mistral', 'duck'})


def _clip(text, limit):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[: limit - 1] + '…'


def update_thread_state(conversation_id, agent, user_message, reply):
    """Rebuild the carry-over summary from the last exchange and the verified facts."""
    if not conversation_id:
        return False
    try:
        facts = recent_facts(conversation_id, limit=10)
        done = []
        proposals = []
        for fact in facts:
            if not fact['ok']:
                continue
            if fact['skill'] == 'alm_create_proposal' and fact['ref']:
                proposals.append(fact['ref'])
            elif fact['skill'] == 'fs_readonly' and fact['ref']:
                done.append(f"read {fact['ref']}")
        if proposals:
            done.append('created ' + ', '.join(proposals))
        summary = (
            f"Asked: {_clip(user_message, 220)} | "
            f"Verified done: {'; '.join(dict.fromkeys(done)) or 'nothing run'} | "
            f"Last reply: {_clip(reply, 260)}"
        )
        open_tasks = ', '.join(f'proposal {p} awaiting execution' for p in dict.fromkeys(proposals))
        from utils.db import get_connection
        conn = get_connection()
        try:
            ensure_tables(conn)
            conn.execute(
                'INSERT INTO thread_state (conversation_id, agent, summary, open_tasks, updated_at) '
                'VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) '
                'ON CONFLICT(conversation_id, agent) DO UPDATE SET '
                'summary=excluded.summary, open_tasks=excluded.open_tasks, updated_at=CURRENT_TIMESTAMP',
                (str(conversation_id), str(agent), summary, open_tasks),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        logger.warning('thread_memory: could not update state: %s', exc)
        return False


def carry_over_block(agent, conversation_id):
    """Small prompt block from this agent's latest saved state; '' when there is none."""
    try:
        from utils.db import get_connection
        conn = get_connection()
        try:
            ensure_tables(conn)
            row = conn.execute(
                'SELECT conversation_id, summary, open_tasks, updated_at FROM thread_state '
                'WHERE agent=? ORDER BY updated_at DESC, rowid DESC LIMIT 1',
                (str(agent),),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return ''
        source = 'this thread' if str(row['conversation_id']) == str(conversation_id) else f"thread {row['conversation_id']}"
        lines = [
            '=== CARRY-OVER (saved from earlier work; verified by skill results) ===',
            f"From {source}, {row['updated_at']}: {row['summary']}",
        ]
        if row['open_tasks']:
            lines.append(f"Still open: {row['open_tasks']}")
        lines.append('Use as background only; do not repeat it back unless asked.')
        lines.append('=== END CARRY-OVER ===\n\n')
        return '\n'.join(lines)
    except Exception as exc:
        logger.warning('thread_memory: could not build carry-over: %s', exc)
        return ''


def _fact_ref(skill, args, result):
    """The checkable handle for a fact: a proposal ID, or the path that was read."""
    if skill == 'alm_create_proposal':
        match = _PROPOSAL_ID_RE.search(result or '')
        return match.group(1) if match else ''
    first = str(args or '').strip().split()
    if skill == 'fs_readonly' and len(first) >= 2:
        return first[1]
    return ''


def record_fact(conversation_id, agent, skill, args, ok, result):
    if not conversation_id:
        return False
    try:
        from utils.db import get_connection
        conn = get_connection()
        try:
            ensure_tables(conn)
            conn.execute(
                'INSERT INTO thread_facts (conversation_id, agent, skill, args, ok, result, ref) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    str(conversation_id), str(agent), str(skill),
                    str(args or '')[:_MAX_ARGS_CHARS], 1 if ok else 0,
                    str(result or '')[:_MAX_RESULT_CHARS],
                    _fact_ref(skill, args, str(result or '')),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        logger.warning('thread_memory: could not record fact: %s', exc)
        return False


def recent_facts(conversation_id, limit=10):
    try:
        from utils.db import get_connection
        conn = get_connection()
        try:
            ensure_tables(conn)
            rows = conn.execute(
                'SELECT agent, skill, args, ok, ref, created_at FROM thread_facts '
                'WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
                (str(conversation_id), int(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception as exc:
        logger.warning('thread_memory: could not read facts: %s', exc)
        return []
