"""
db.chat — Conversations, messages, and chat job tracking.
"""
import json
import time
import uuid

from ._connection import get_connection


_RELAY_RECOVERY_AGENTS = ('librarian', 'duck', 'vortex')
_RELAY_RECOVERY_STATUSES = {'open', 'reviewed', 'ignored', 'escalated'}
_RELAY_RECOVERY_PROJECT_ID = 'P-CHAT-RELAY-RECOVERY'


def _ensure_relay_recovery_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            conversation_id INTEGER DEFAULT 0,
            job_id TEXT UNIQUE NOT NULL,
            stalled_agent TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            recovery_agents_json TEXT DEFAULT '[]',
            relay_context_json TEXT DEFAULT '{}',
            summary TEXT DEFAULT '',
            lease_owner TEXT DEFAULT '',
            lease_until TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    for col_ddl in (
        "ALTER TABLE chat_relay_recoveries ADD COLUMN lease_owner TEXT DEFAULT ''",
        "ALTER TABLE chat_relay_recoveries ADD COLUMN lease_until TEXT DEFAULT ''",
    ):
        try:
            conn.execute(col_ddl)
        except Exception:
            pass


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _relay_recovery_step_id(recovery_id):
    suffix = ''.join(ch for ch in str(recovery_id or '').upper() if ch.isalnum())
    suffix = suffix[-12:] or uuid.uuid4().hex[:12].upper()
    return f'S-RELAY-{suffix}'


def _ensure_relay_recovery_project_schema(conn):
    """Best-effort Studio task board bridge for recovery cards."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            methodology TEXT NOT NULL DEFAULT 'mixed',
            status TEXT NOT NULL DEFAULT 'active',
            owner TEXT NOT NULL DEFAULT 'seven',
            created_at REAL NOT NULL,
            updated_at REAL,
            priority INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]'
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_steps (
            step_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'todo',
            owner TEXT NOT NULL DEFAULT 'seven',
            order_idx INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL,
            residual_risk TEXT DEFAULT '',
            owner_route TEXT DEFAULT ''
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_step_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'task',
            source_ref TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_blackboard_notes (
            note_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'seven',
            kind TEXT NOT NULL DEFAULT 'note',
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at REAL NOT NULL,
            updated_at REAL
        )"""
    )
    now = time.time()
    conn.execute(
        """
        INSERT INTO projects
            (project_id, name, description, methodology, status, owner,
             created_at, updated_at, priority, tags)
        VALUES (?, ?, ?, 'agile', 'active', 'watchdog', ?, ?, 80, ?)
        ON CONFLICT(project_id) DO UPDATE SET
            description=excluded.description,
            status='active',
            updated_at=excluded.updated_at,
            tags=excluded.tags
        """,
        (
            _RELAY_RECOVERY_PROJECT_ID,
            'Chat Relay Recovery Watchdog',
            (
                'One-at-a-time board for stalled chat jobs, silent threads, '
                'and watchdog recovery cards. Every timeout gets a visible '
                'Studio step, prompt, evidence trail, and completion status.'
            ),
            now,
            now,
            json.dumps(['watchdog', 'chat', 'relay-recovery'], ensure_ascii=True),
        ),
    )


def _sync_relay_recovery_task_board(conn, recovery, card='', status='todo', evidence_summary=''):
    """Create/update the Studio step that tracks one relay recovery card."""
    try:
        _ensure_relay_recovery_project_schema(conn)
        recovery = recovery or {}
        recovery_id = str(recovery.get('recovery_id') or '').strip()
        if not recovery_id:
            return ''
        step_id = _relay_recovery_step_id(recovery_id)
        conv_id = int(recovery.get('conversation_id') or 0)
        stalled_agent = str(recovery.get('stalled_agent') or 'agent').strip().lower() or 'agent'
        owner = _relay_recovery_owner(stalled_agent)
        job_id = str(recovery.get('job_id') or '').strip()
        summary = str(recovery.get('summary') or '').strip()
        title = f'Recover chat thread #{conv_id} after {stalled_agent} stalled'
        prompt = (
            'Recovery prompt for the next agent:\n'
            '- Work one recovery at a time; finish or escalate this card before claiming another.\n'
            '- Read the thread tail and stage trace. Continue the user-visible task, do not restart from scratch.\n'
            '- Write concise progress/results back to this Studio step and the conversation.\n'
            '- If the recovery fails, record exactly where it fell over and what proof is missing.\n'
            '- Do not expose private chain-of-thought.\n'
        )
        description = (
            f'Recovery ID: {recovery_id}\n'
            f'Conversation: #{conv_id}\n'
            f'Stalled job: {job_id}\n'
            f'Stalled agent: {stalled_agent}\n'
            f'Summary: {summary}\n\n'
            f'{prompt}\n'
            f'Relay recovery card:\n{str(card or "").strip()[:4000]}'
        )[:6000]
        now = time.time()
        conn.execute(
            """
            INSERT INTO project_steps
                (step_id, project_id, title, description, status, owner,
                 order_idx, created_at, updated_at, residual_risk, owner_route)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(step_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                status=excluded.status,
                owner=excluded.owner,
                updated_at=excluded.updated_at,
                residual_risk=excluded.residual_risk,
                owner_route=excluded.owner_route
            """,
            (
                step_id,
                _RELAY_RECOVERY_PROJECT_ID,
                title[:180],
                description,
                status,
                owner,
                int(now),
                now,
                now,
                'Open until an agent either completes the original user task or records an explicit blocker.',
                f'watchdog:{recovery_id}',
            ),
        )
        if evidence_summary:
            conn.execute(
                """
                INSERT INTO project_step_evidence
                    (project_id, step_id, source_type, source_ref, summary, status)
                VALUES (?, ?, 'watchdog_recovery', ?, ?, ?)
                """,
                (
                    _RELAY_RECOVERY_PROJECT_ID,
                    step_id,
                    recovery_id,
                    str(evidence_summary or '')[:500],
                    'ok' if status in {'todo', 'doing', 'done'} else 'warn',
                ),
            )
        note_id = f'BB-{step_id}'
        conn.execute(
            """
            INSERT INTO project_blackboard_notes
                (note_id, project_id, author, kind, content, status, created_at, updated_at)
            VALUES (?, ?, 'watchdog', 'handoff', ?, 'active', ?, ?)
            ON CONFLICT(note_id) DO UPDATE SET
                content=excluded.content,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                note_id,
                _RELAY_RECOVERY_PROJECT_ID,
                (
                    f'{title}\n\n'
                    f'{prompt}\n'
                    f'Latest status: {status}. Recovery ID: {recovery_id}.'
                )[:3000],
                now,
                now,
            ),
        )
        return step_id
    except Exception:
        return ''


def _relay_recovery_owner(stalled_agent):
    stalled = str(stalled_agent or '').strip().lower()
    order = ['qwen', 'gemma', 'mistral']
    for agent in order:
        if agent != stalled:
            return agent
    return 'qwen'


def new_conversation(title, source='email', sender=''):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO conversations (title,source,sender) VALUES (?,?,?)",
        (title[:100], source, sender)
    )
    conv_id = cursor.lastrowid
    conn.commit()
    conn.close()
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('thread', conv_id, actor='new_conversation')
    except Exception:
        pass
    return conv_id


def log_message(conv_id, from_agent, content, to_agent='', message_type='chat', tokens_used=0):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,?,?,?,?,?)",
        (conv_id, from_agent, to_agent, content, message_type, int(tokens_used or 0))
    )
    conn.commit()
    conn.close()
    try:
        from core.records import mirror as _records_mirror
        _records_mirror('thread', conv_id, actor='log_message')
    except Exception:
        pass


def get_ghost_history(limit=10):
    conn = get_connection()
    rows = conn.execute("""
        SELECT m.content, m.created_at, c.title
        FROM messages m JOIN conversations c ON m.conversation_id=c.id
        WHERE m.from_agent='Ghost'
        ORDER BY m.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return list(reversed(rows))


def persist_chat_job(job_id, conversation_id, agent, runtime_class, eta_seconds, started_at):
    """Record a new chat job. Best-effort — never raises."""
    stage_trace = json.dumps([{'text': 'queued'}], ensure_ascii=True)
    try:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO chat_jobs
                   (job_id, conversation_id, agent, status, runtime_class,
                    eta_seconds, started_at, updated_at, stage, stage_trace_json)
                   VALUES (?, ?, ?, 'running', ?, ?, ?, ?, 'queued', ?)""",
                (str(job_id), int(conversation_id or 0), str(agent or ''),
                 str(runtime_class or ''), int(eta_seconds or 60),
                 str(started_at or ''), str(started_at or ''), stage_trace)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def update_chat_job_db(job_id, status, stage='', error='', elapsed_ms=0, tokens=0, stage_trace_json=None):
    """Update a chat job record. Best-effort — never raises."""
    try:
        conn = get_connection()
        try:
            if stage_trace_json is not None:
                conn.execute(
                    """UPDATE chat_jobs
                       SET status=?, stage=?, error=?, elapsed_ms=?, tokens=?,
                           stage_trace_json=?, updated_at=datetime('now')
                       WHERE job_id=?""",
                    (str(status), str(stage or ''), str(error or '')[:500],
                     int(elapsed_ms or 0), int(tokens or 0),
                     str(stage_trace_json), str(job_id))
                )
            else:
                conn.execute(
                    """UPDATE chat_jobs
                       SET status=?, stage=?, error=?, elapsed_ms=?, tokens=?,
                           updated_at=datetime('now')
                       WHERE job_id=?""",
                    (str(status), str(stage or ''), str(error or '')[:500],
                     int(elapsed_ms or 0), int(tokens or 0), str(job_id))
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_chat_jobs_by_ids(job_ids):
    """Fetch chat_jobs rows for a set of job IDs. Returns list of dicts."""
    job_ids = [str(j) for j in (job_ids or []) if j]
    if not job_ids:
        return []
    try:
        conn = get_connection()
        try:
            placeholders = ','.join('?' for _ in job_ids)
            rows = conn.execute(
                f'SELECT * FROM chat_jobs WHERE job_id IN ({placeholders})',
                job_ids
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def ensure_chat_relay_recovery(
    job_id,
    conversation_id,
    stalled_agent,
    reason,
    stage_trace=None,
    recovery_agents=None,
    context_limit=8,
):
    """Create one durable recovery card for a stalled chat relay job.

    The card is intentionally concise: it preserves continuity and next-step
    instructions without asking agents to expose private chain-of-thought.
    Returns {created, recovery, message}.
    """
    job_id = str(job_id or '').strip()
    if not job_id:
        return {'created': False, 'recovery': None, 'message': ''}

    try:
        conv_id = int(conversation_id or 0)
    except Exception:
        conv_id = 0

    agent = str(stalled_agent or 'agent').strip().lower() or 'agent'
    reason = str(reason or 'chat job stalled').strip()[:700]
    agents = tuple(
        str(item or '').strip().lower()
        for item in (recovery_agents or _RELAY_RECOVERY_AGENTS)
        if str(item or '').strip()
    ) or _RELAY_RECOVERY_AGENTS
    agents_json = json.dumps(list(agents), ensure_ascii=True)

    try:
        conn = get_connection()
        try:
            _ensure_relay_recovery_schema(conn)
            existing = conn.execute(
                "SELECT * FROM chat_relay_recoveries WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if existing:
                return {'created': False, 'recovery': _row_to_dict(existing), 'message': ''}

            rows = conn.execute(
                """
                SELECT from_agent, to_agent, content, message_type, created_at
                FROM messages
                WHERE conversation_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conv_id, max(1, min(int(context_limit or 8), 20))),
            ).fetchall()
            thread_tail = [dict(row) for row in reversed(rows)]
            trace = stage_trace or []
            context = {
                'thread_tail': thread_tail,
                'stage_trace': trace,
                'recovery_agents': list(agents),
                'continuity_rule': (
                    'Resume from evidence, visible decisions, and next actions. '
                    'Do not expose private chain-of-thought; write concise working notes.'
                ),
            }
            summary = f'{agent} stalled in conversation #{conv_id}; relay recovery opened for Librarian, Duck, and Vortex.'
            recovery_id = f'recovery-{uuid.uuid4().hex[:12]}'
            card = _format_relay_recovery_card(
                recovery_id=recovery_id,
                conv_id=conv_id,
                job_id=job_id,
                stalled_agent=agent,
                reason=reason,
                stage_trace=trace,
                thread_tail=thread_tail,
                recovery_agents=agents,
            )
            conn.execute(
                """
                INSERT INTO chat_relay_recoveries
                    (recovery_id, conversation_id, job_id, stalled_agent, status,
                     recovery_agents_json, relay_context_json, summary)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    recovery_id,
                    conv_id,
                    job_id,
                    agent,
                    agents_json,
                    json.dumps(context, ensure_ascii=True),
                    summary,
                ),
            )
            pending_recovery = {
                'recovery_id': recovery_id,
                'conversation_id': conv_id,
                'job_id': job_id,
                'stalled_agent': agent,
                'summary': summary,
            }
            _sync_relay_recovery_task_board(
                conn,
                pending_recovery,
                card=card,
                status='todo',
                evidence_summary=f'Recovery opened: {reason}',
            )
            conn.execute(
                """
                INSERT INTO messages
                    (conversation_id, from_agent, to_agent, content, message_type, tokens_used)
                VALUES (?, 'watchdog', ?, ?, 'relay_recovery', 0)
                """,
                (conv_id, ','.join(agents), card),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM chat_relay_recoveries WHERE recovery_id=?",
                (recovery_id,),
            ).fetchone()
            return {'created': True, 'recovery': _row_to_dict(row), 'message': card}
        finally:
            conn.close()
    except Exception as exc:
        return {'created': False, 'recovery': None, 'message': '', 'error': str(exc)}


def ensure_silent_chat_thread_recovery(conversation_id, reason='chat thread has no visible agent reply'):
    """Open one recovery card when a thread goes quiet after failed/cancelled jobs.

    This catches the failure mode where watchdog has no live in-memory job to
    mark stalled, but the user-facing thread is still broken because the latest
    turn only contains user messages and cancelled/failed job rows.
    """
    try:
        conv_id = int(conversation_id or 0)
    except Exception:
        conv_id = 0
    if conv_id <= 0:
        return {'created': False, 'recovery': None, 'message': ''}

    try:
        conn = get_connection()
        try:
            _ensure_relay_recovery_schema(conn)
            existing = conn.execute(
                """
                SELECT * FROM chat_relay_recoveries
                WHERE conversation_id=? AND status='open'
                  AND job_id LIKE ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (conv_id, f'silent-thread-{conv_id}-%'),
            ).fetchone()
            if existing:
                return {'created': False, 'recovery': _row_to_dict(existing), 'message': ''}

            latest_user = conn.execute(
                """
                SELECT id, created_at, content
                FROM messages
                WHERE conversation_id=? AND from_agent='user'
                ORDER BY id DESC
                LIMIT 1
                """,
                (conv_id,),
            ).fetchone()
            if not latest_user:
                return {'created': False, 'recovery': None, 'message': ''}

            reply = conn.execute(
                """
                SELECT id
                FROM messages
                WHERE conversation_id=?
                  AND id > ?
                  AND from_agent NOT IN ('user', 'watchdog')
                  AND message_type NOT IN ('relay_recovery')
                LIMIT 1
                """,
                (conv_id, int(latest_user['id'])),
            ).fetchone()
            if reply:
                return {'created': False, 'recovery': None, 'message': ''}

            jobs = conn.execute(
                """
                SELECT job_id, agent, status, stage, error, started_at, updated_at
                FROM chat_jobs
                WHERE conversation_id=?
                ORDER BY updated_at DESC, started_at DESC
                LIMIT 5
                """,
                (conv_id,),
            ).fetchall()
            terminal_jobs = [
                dict(row) for row in jobs
                if str(row['status'] or '').lower() in {'failed', 'cancelled'}
            ]
            if not terminal_jobs:
                return {'created': False, 'recovery': None, 'message': ''}

            latest_job = terminal_jobs[0]
            agent = str(latest_job.get('agent') or 'agent').strip().lower() or 'agent'
            stage_trace = []
            for row in reversed(terminal_jobs):
                status = str(row.get('status') or 'unknown')
                stage = str(row.get('stage') or '').strip()
                error = str(row.get('error') or '').strip()
                text = f"{row.get('agent') or 'agent'} {status}"
                if stage:
                    text += f' - {stage}'
                if error:
                    text += f' - {error[:120]}'
                stage_trace.append({'text': text})

            return ensure_chat_relay_recovery(
                job_id=f"silent-thread-{conv_id}-{int(latest_user['id'])}",
                conversation_id=conv_id,
                stalled_agent=agent,
                reason=str(reason or 'chat thread has no visible agent reply')[:700],
                stage_trace=stage_trace,
                recovery_agents=_RELAY_RECOVERY_AGENTS,
            )
        finally:
            conn.close()
    except Exception as exc:
        return {'created': False, 'recovery': None, 'message': '', 'error': str(exc)}


def get_open_chat_relay_recoveries(conversation_id=None, limit=20):
    try:
        conn = get_connection()
        try:
            _ensure_relay_recovery_schema(conn)
            if conversation_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM chat_relay_recoveries
                    WHERE status='open' AND conversation_id=?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (int(conversation_id or 0), max(1, min(int(limit or 20), 100))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM chat_relay_recoveries
                    WHERE status='open'
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(limit or 20), 100)),),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    except Exception:
        return []


def lease_chat_relay_recoveries(owner, limit=3, lease_seconds=1800, conversation_id=None):
    """Claim open recovery cards for active review.

    Leases avoid two background loops asking agents to review the same card.
    The card remains status='open' so the UI can still show it; lease metadata
    tells other workers to skip it until the lease expires.
    """
    owner = str(owner or '').strip()[:120] or 'relay_recovery_worker'
    try:
        limit = max(1, min(int(limit or 3), 20))
    except Exception:
        limit = 3
    try:
        lease_seconds = max(60, min(int(lease_seconds or 1800), 7200))
    except Exception:
        lease_seconds = 1800

    try:
        conn = get_connection()
        try:
            _ensure_relay_recovery_schema(conn)
            params = []
            where = [
                "status='open'",
                "(lease_until IS NULL OR lease_until='' OR lease_until <= datetime('now'))",
            ]
            if conversation_id is not None:
                where.append("conversation_id=?")
                params.append(int(conversation_id or 0))
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT * FROM chat_relay_recoveries
                WHERE {' AND '.join(where)}
                ORDER BY created_at ASC
                LIMIT ?
                """,
                params,
            ).fetchall()

            claimed = []
            modifier = f'+{lease_seconds} seconds'
            for row in rows:
                recovery_id = row['recovery_id']
                cur = conn.execute(
                    """
                    UPDATE chat_relay_recoveries
                    SET lease_owner=?, lease_until=datetime('now', ?), updated_at=datetime('now')
                    WHERE recovery_id=?
                      AND status='open'
                      AND (lease_until IS NULL OR lease_until='' OR lease_until <= datetime('now'))
                    """,
                    (owner, modifier, recovery_id),
                )
                if cur.rowcount > 0:
                    fresh = conn.execute(
                        "SELECT * FROM chat_relay_recoveries WHERE recovery_id=?",
                        (recovery_id,),
                    ).fetchone()
                    if fresh:
                        fresh_dict = dict(fresh)
                        _sync_relay_recovery_task_board(
                            conn,
                            fresh_dict,
                            status='doing',
                            evidence_summary=f'Recovery leased to {owner}',
                        )
                        claimed.append(fresh_dict)
            conn.commit()
            return claimed
        finally:
            conn.close()
    except Exception:
        return []


def update_chat_relay_recovery_status(recovery_id, status, summary=None):
    recovery_id = str(recovery_id or '').strip()
    status = str(status or '').strip().lower()
    if not recovery_id or not status:
        return False
    if status not in _RELAY_RECOVERY_STATUSES:
        return False
    try:
        conn = get_connection()
        try:
            _ensure_relay_recovery_schema(conn)
            if summary is None:
                cur = conn.execute(
                    """
                    UPDATE chat_relay_recoveries
                    SET status=?, lease_owner='', lease_until='', updated_at=datetime('now')
                    WHERE recovery_id=?
                    """,
                    (status, recovery_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE chat_relay_recoveries
                    SET status=?, summary=?, lease_owner='', lease_until='', updated_at=datetime('now')
                    WHERE recovery_id=?
                    """,
                    (status, str(summary or '')[:1000], recovery_id),
                )
            if cur.rowcount > 0:
                fresh = conn.execute(
                    "SELECT * FROM chat_relay_recoveries WHERE recovery_id=?",
                    (recovery_id,),
                ).fetchone()
                if fresh:
                    step_status = {
                        'reviewed': 'done',
                        'ignored': 'skipped',
                        'escalated': 'blocked',
                        'open': 'todo',
                    }.get(status, 'todo')
                    _sync_relay_recovery_task_board(
                        conn,
                        dict(fresh),
                        status=step_status,
                        evidence_summary=summary or f'Recovery marked {status}',
                    )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception:
        return False


def _format_relay_recovery_card(
    recovery_id,
    conv_id,
    job_id,
    stalled_agent,
    reason,
    stage_trace,
    thread_tail,
    recovery_agents,
):
    trace_lines = []
    for item in (stage_trace or [])[-6:]:
        if isinstance(item, dict):
            text = str(item.get('text') or '').strip()
        else:
            text = str(item or '').strip()
        if text:
            trace_lines.append(f'- {text[:160]}')
    if not trace_lines:
        trace_lines.append('- No stage trace captured.')

    context_lines = []
    for msg in (thread_tail or [])[-5:]:
        sender = str(msg.get('from_agent') or 'unknown').strip()
        target = str(msg.get('to_agent') or '').strip()
        content = ' '.join(str(msg.get('content') or '').split())[:220]
        arrow = f' -> {target}' if target else ''
        if content:
            context_lines.append(f'- {sender}{arrow}: {content}')
    if not context_lines:
        context_lines.append('- No prior chat context found.')

    return (
        f'## Relay Recovery Card: {recovery_id}\n\n'
        f'Conversation: #{conv_id}\n'
        f'Stalled job: {job_id}\n'
        f'Stalled agent: {stalled_agent}\n'
        f'Reason: {reason}\n'
        f'Pickup agents: {", ".join(recovery_agents)}\n\n'
        '### Last Known Stages\n'
        + '\n'.join(trace_lines)
        + '\n\n### Thread Tail\n'
        + '\n'.join(context_lines)
        + '\n\n### Recovery Instructions\n'
        '- Librarian: preserve the relay context, identify the intended next agent, and summarize what still needs doing.\n'
        '- Duck: sanity-check assumptions and flag contradictions, missing evidence, or unsafe next actions.\n'
        '- Vortex: treat this card as the recovery checkpoint for the thread.\n'
        '- Next responder: continue from visible facts and decisions. Do not expose private chain-of-thought; use concise working notes and concrete next steps.\n'
    )


def mark_orphaned_chat_jobs():
    """Mark any 'running' chat_jobs rows as failed. Call once on server startup."""
    orphaned = []
    try:
        conn = get_connection()
        try:
            cur = conn.execute(
                """UPDATE chat_jobs
                   SET status='failed', stage='failed',
                       error='server restarted — job lost',
                       updated_at=datetime('now')
                   WHERE status='running'
                   RETURNING job_id, conversation_id, agent"""
            )
            orphaned = [dict(row) for row in cur.fetchall()]
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
    for row in orphaned:
        try:
            ensure_chat_relay_recovery(
                job_id=row.get('job_id'),
                conversation_id=row.get('conversation_id'),
                stalled_agent=row.get('agent'),
                reason='server restarted — job lost',
                stage_trace=[{'text': 'server restarted - runtime job was orphaned'}],
            )
        except Exception:
            pass


def sweep_stuck_jobs(max_age_minutes=120, no_progress_age_minutes=15, conversation_id=None):
    """Fail jobs stuck in running/dispatched/processing state beyond max_age_minutes.

    Designed to be called periodically (e.g. every 10 minutes) from a
    background thread. Returns the number of jobs swept.

    A second, shorter no-progress budget catches the thread #2583 failure mode:
    a DB job is created after a follow-up user turn, but the live runtime never
    records even its first stage trace. Healthy local jobs write a stage almost
    immediately; an empty trace after this grace period is an orphaned launch,
    not a slow model.
    """
    swept_rows = []
    try:
        conn = get_connection()
        try:
            where = [
                "status IN ('running', 'dispatched', 'processing')",
                """(
                       julianday(started_at) < julianday('now', ?)
                    OR (
                         COALESCE(stage, '') = ''
                     AND COALESCE(error, '') = ''
                     AND COALESCE(stage_trace_json, '[]') IN ('', '[]')
                     AND julianday(started_at) < julianday('now', ?)
                    )
                )""",
            ]
            params = [
                f'-{max_age_minutes} minutes',
                f'-{no_progress_age_minutes} minutes',
            ]
            if conversation_id is not None:
                where.append("conversation_id=?")
                params.append(int(conversation_id or 0))

            cur = conn.execute(
                f"""UPDATE chat_jobs
                   SET status='failed', stage='failed',
                       error=CASE
                         WHEN COALESCE(stage, '') = ''
                          AND COALESCE(error, '') = ''
                          AND COALESCE(stage_trace_json, '[]') IN ('', '[]')
                         THEN printf('no-progress job swept (>%d min without first stage)', ?)
                         ELSE printf('stuck job swept (>%d min in state: %s)', ?, status)
                       END,
                       stage_trace_json=CASE
                         WHEN COALESCE(stage_trace_json, '[]') IN ('', '[]')
                         THEN '[{{"text":"no progress recorded before watchdog sweep"}}]'
                         ELSE stage_trace_json
                       END,
                       updated_at=datetime('now')
                   WHERE {' AND '.join(where)}
                   RETURNING job_id, conversation_id, agent, status, stage, error, stage_trace_json""",
                (no_progress_age_minutes, max_age_minutes, *params),
            )
            swept_rows = [dict(row) for row in cur.fetchall()]
            if swept_rows:
                conn.commit()
            return len(swept_rows)
        except Exception:
            return 0
        finally:
            conn.close()
    except Exception:
        return 0
    finally:
        for row in swept_rows:
            try:
                trace = json.loads(row.get('stage_trace_json') or '[]')
            except Exception:
                trace = []
            try:
                ensure_chat_relay_recovery(
                    job_id=row.get('job_id'),
                    conversation_id=row.get('conversation_id'),
                    stalled_agent=row.get('agent'),
                    reason=row.get('error') or 'chat job swept by watchdog',
                    stage_trace=trace,
                )
            except Exception:
                pass
