"""Verified facts per conversation thread, recorded from real skill results.

A fact exists only if a skill returned it, so carry-over never contains guesses.
All functions are best-effort: a failure here must never break a chat turn.
"""
import contextvars
import logging
import os
import re
import sqlite3

logger = logging.getLogger(__name__)

# The model's own database. Nothing else writes to it.
MIND_DB_PATH = os.environ.get(
    'SWARM_MIND_DB',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mind.db'),
)


def _conn():
    conn = sqlite3.connect(MIND_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

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
    conn.execute(_NOTES_SCHEMA)
    conn.execute(_EXCHANGES_SCHEMA)


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
        conn = _conn()
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


def carry_over_block(agent, conversation_id, message=''):
    """Prompt block: latest saved state plus the few notes most relevant to this message."""
    try:
        conn = _conn()
        try:
            ensure_tables(conn)
            seed_notes(conn)
            row = conn.execute(
                'SELECT conversation_id, summary, open_tasks, updated_at FROM thread_state '
                'WHERE agent=? ORDER BY updated_at DESC, rowid DESC LIMIT 1',
                (str(agent),),
            ).fetchone()
            notes = relevant_notes(conn, message)
        finally:
            conn.close()
        if not row and not notes:
            return ''
        lines = ['=== CARRY-OVER (your own saved memory, mind.db; background only) ===']
        if row:
            source = 'this thread' if str(row['conversation_id']) == str(conversation_id) else f"thread {row['conversation_id']}"
            lines.append(f"Last work ({source}, {row['updated_at']}): {row['summary']}")
            if row['open_tasks']:
                lines.append(f"Still open: {row['open_tasks']}")
        for note in notes:
            lines.append(f"- [{note['kind']}] {_clip(note['text'], 260)}")
        lines.append('Do not repeat this back unless asked. Facts from skills are verified; notes are what the operator decided.')
        lines.append('=== END CARRY-OVER ===\n\n')
        return '\n'.join(lines)
    except Exception as exc:
        logger.warning('thread_memory: could not build carry-over: %s', exc)
        return ''


_current_conversation = contextvars.ContextVar('mind_conversation', default=None)


def run_in_conversation(conversation_id, fn, *args, **kwargs):
    """Run fn with the conversation ID visible to fact recording (works in worker threads)."""
    token = _current_conversation.set(conversation_id)
    try:
        return fn(*args, **kwargs)
    finally:
        _current_conversation.reset(token)


_NOTES_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_EXCHANGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    user_message TEXT NOT NULL,
    reply TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# What the operator decided, so the one model starts with the same context.
_SEED_NOTES = (
    ('principle', 'Operator mantra, in order: 1 honesty, 2 kindness, 3 extreme logic.'),
    ('decision', 'One local model (mistral-small:24b on the 16 GB RX 6800) wears every hat. Gemma is director, Mistral coder and analyst, Duck reviewer. Llama, Qwen, Eight, Librarian, Sniffles, Thirteen, Nineteen and Twenty are parked, not deleted; Mistral may later adopt one as a pet.'),
    ('decision', 'Write skills (fs_patch, fs_patch_lines, fs_write, file_write) are revoked. Agents read files and raise proposals only. An agent patch once broke fridays/task_runner.py.'),
    ('correction', 'Do not report a proposal ID or file result unless a skill returned it; otherwise say it is unverified.'),
    ('correction', 'Do not invent who or what you are. You are the local model named in your self-awareness block, hosted by Ollama.'),
    ('preference', 'Operator wants one step at a time, asked before anything big. Think twice, build once. Be kind and concise, never shout at agents.'),
    ('design', 'mind.db is your own memory: exchanges (full text), thread_facts (skill results), thread_state (per-thread summary), notes (decisions and corrections). Only relevant notes are loaded into each prompt.'),
)


def seed_notes(conn):
    if conn.execute('SELECT COUNT(*) FROM notes').fetchone()[0]:
        return
    conn.executemany('INSERT INTO notes (kind, text) VALUES (?, ?)', _SEED_NOTES)
    conn.commit()


def add_note(kind, text):
    try:
        conn = _conn()
        try:
            ensure_tables(conn)
            seed_notes(conn)
            conn.execute('INSERT INTO notes (kind, text) VALUES (?, ?)', (str(kind), str(text)))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        logger.warning('thread_memory: could not add note: %s', exc)
        return False


_WORD_RE = re.compile(r'[a-z0-9_]{4,}')


def relevant_notes(conn, message, limit=5):
    """Principles always; the rest ranked by word overlap with the message, newest on ties."""
    rows = conn.execute('SELECT kind, text FROM notes ORDER BY id DESC').fetchall()
    words = set(_WORD_RE.findall(str(message or '').lower()))
    always = [r for r in rows if r['kind'] in ('principle', 'correction')]
    scored = sorted(
        (r for r in rows if r['kind'] not in ('principle', 'correction')),
        key=lambda r: -len(words & set(_WORD_RE.findall(r['text'].lower()))),
    )
    return (always + scored)[: max(limit, len(always))]


def record_exchange(conversation_id, agent, user_message, reply):
    """Full text of the exchange, uncut."""
    if not conversation_id:
        return False
    try:
        conn = _conn()
        try:
            ensure_tables(conn)
            conn.execute(
                'INSERT INTO exchanges (conversation_id, agent, user_message, reply) VALUES (?, ?, ?, ?)',
                (str(conversation_id), str(agent), str(user_message or ''), str(reply or '')),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:
        logger.warning('thread_memory: could not record exchange: %s', exc)
        return False


def mind_overview():
    """Short line for the self-awareness block: where the memory is and how big it is."""
    try:
        conn = _conn()
        try:
            ensure_tables(conn)
            counts = {
                t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                for t in ('exchanges', 'thread_facts', 'thread_state', 'notes')
            }
        finally:
            conn.close()
        return (
            f'Your own memory is mind.db ({MIND_DB_PATH}): '
            + ', '.join(f'{n} {t}' for t, n in counts.items()) + '.'
        )
    except Exception:
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
    conversation_id = conversation_id or _current_conversation.get()
    if not conversation_id:
        return False
    try:
        conn = _conn()
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
        conn = _conn()
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
