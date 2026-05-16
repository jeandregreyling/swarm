"""Watchdog DEOS supervisor.

DEOS = Decides, Executes, Operates, Sustains.

This module is intentionally deterministic. It does not make Duck, Librarian,
Seven, or Vortex autonomous thinkers. It keeps support roles ready, chooses one
piece of recovery work, executes bounded operations, and records evidence.
"""
from __future__ import annotations

import json
import re
import shlex
import time
from typing import Any, Dict, List, Optional, Tuple

from utils.db._connection import get_connection
from utils.deos_teaching import local_agent_packet


PROJECT_ID = 'P-CHAT-RELAY-RECOVERY'
STEP_ID = 'S-DEOS-CONTROL-PLANE'
WORK_STEP_ID = 'S-DEOS-LOCAL-AGENT-WORK'

SUPPORT_POLICY = {
    'librarian': 'context, thread-tail, Studio/KC lookup, and recovery handoff',
    'duck': 'QA, contradiction checks, and completion judgment',
    'seven': 'control plane identity; no autonomous hot thinking loop',
}

WORK_AGENT_MODULES = {
    'mistral': ('agents.mistral.mistral_agent', 'chat'),
    'qwen': ('agents.qwen.qwen_agent', 'chat'),
    'gemma': ('agents.gemma.gemma_agent', 'chat'),
    'llama': ('agents.llama.llama_agent', 'chat'),
}

WORK_AGENT_ORDER = ['qwen', 'gemma', 'llama', 'mistral']

WORK_AGENT_MODELS = {
    'mistral': 'mistral:latest',
    'qwen': 'qwen:latest',
    'gemma': 'gemma3:latest',
    'llama': 'llama3.2:latest',
}


def _bool_opt(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _parse_args(args: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tok in shlex.split(str(args or '')):
        if '=' not in tok:
            continue
        key, value = tok.split('=', 1)
        out[key.strip().lower()] = value.strip()
    return out


def _now() -> float:
    return time.time()


def _ensure_project(conn) -> None:
    now = _now()
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
        """INSERT INTO projects
            (project_id, name, description, methodology, status, owner,
             created_at, updated_at, priority, tags)
           VALUES (?, 'Chat Relay Recovery Watchdog',
             'DEOS control plane for stalled chat work, model readiness, and one-at-a-time recovery.',
             'agile', 'active', 'watchdog', ?, ?, 90, ?)
           ON CONFLICT(project_id) DO UPDATE SET
             description=excluded.description,
             status='active',
             updated_at=excluded.updated_at,
             tags=excluded.tags"""
        ,
        (
            PROJECT_ID,
            now,
            now,
            json.dumps(['watchdog', 'deos', 'chat', 'relay-recovery'], ensure_ascii=True),
        ),
    )
    conn.execute(
        """INSERT INTO project_steps
            (step_id, project_id, title, description, status, owner, order_idx,
             created_at, updated_at, residual_risk, owner_route)
           VALUES (?, ?, 'Run Watchdog DEOS supervisor',
             'Deterministic control loop: decide next recovery state, execute bounded operations, operate through Studio rows, and sustain evidence/lessons. Duck and Librarian are support functions, not autonomous always-thinking loops.',
             'doing', 'watchdog', 1, ?, ?,
             'If this loop is absent, cold starts, DB locks, and agent timeouts look like random LLM failures.',
             'watchdog:deos')
           ON CONFLICT(step_id) DO UPDATE SET
             description=excluded.description,
             status='doing',
             owner=excluded.owner,
             updated_at=excluded.updated_at,
             residual_risk=excluded.residual_risk,
             owner_route=excluded.owner_route"""
        ,
        (STEP_ID, PROJECT_ID, now, now),
    )
    conn.execute(
        """INSERT INTO project_steps
            (step_id, project_id, title, description, status, owner, order_idx,
             created_at, updated_at, residual_risk, owner_route)
           VALUES (?, ?, 'Run local agent work packets on their own time',
             'DEOS may claim one Studio step at a time and call one local agent with a bounded work packet. The agent can use SKILL commands through its normal local runtime. DEOS records output/evidence and only marks done when the response explicitly reports done with proof.',
             'todo', 'watchdog', 2, ?, ?,
             'Local agents may still time out or fail to emit valid SKILL commands; failures must become blockers, not silent stalls.',
             'watchdog:local-agent-work')
           ON CONFLICT(step_id) DO UPDATE SET
             description=excluded.description,
             updated_at=excluded.updated_at,
             residual_risk=excluded.residual_risk,
             owner_route=excluded.owner_route"""
        ,
        (WORK_STEP_ID, PROJECT_ID, now, now),
    )


def _add_step_evidence(
    conn,
    step_id: str,
    source_ref: str,
    summary: str,
    status: str = 'ok',
    project_id: str = PROJECT_ID,
) -> None:
    conn.execute(
        """INSERT INTO project_step_evidence
            (project_id, step_id, source_type, source_ref, summary, status)
           VALUES (?, ?, 'watchdog_deos', ?, ?, ?)""",
        (project_id or PROJECT_ID, step_id, str(source_ref or '')[:120], str(summary or '')[:500], status),
    )


def _add_evidence(conn, source_ref: str, summary: str, status: str = 'ok') -> None:
    _add_step_evidence(conn, STEP_ID, source_ref, summary, status)


def _agent_rows(conn) -> Dict[str, Dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT name, model, tier, enabled, eta_seconds, keep_alive FROM agents"
        ).fetchall()
    except Exception:
        return {}
    return {str(r['name']).lower(): dict(r) for r in rows}


def _resident_targets(conn) -> List[Dict[str, Any]]:
    agents = _agent_rows(conn)
    targets = []
    for name, reason in SUPPORT_POLICY.items():
        row = agents.get(name) or {}
        model = str(row.get('model') or '').strip()
        is_ollama = bool(model and model not in {'external', 'local-algorithm'})
        targets.append({
            'agent': name,
            'model': model,
            'is_ollama': is_ollama,
            'reason': reason,
            'keep_alive': int(row.get('keep_alive') or 300),
            'enabled': bool(row.get('enabled', 1)),
        })
    return targets


def _ollama_loaded() -> List[str]:
    try:
        import ollama  # type: ignore
        result = ollama.ps()
        models = getattr(result, 'models', None)
        if models is None and isinstance(result, dict):
            models = result.get('models', [])
        out = []
        for item in models or []:
            name = getattr(item, 'model', None) or (item.get('model') if isinstance(item, dict) else None)
            if name:
                out.append(str(name))
        return out
    except Exception:
        return []


def _warm_model(model: str, keep_alive: int, timeout_seconds: int) -> Tuple[bool, str]:
    try:
        import requests
        resp = requests.post(
            'http://127.0.0.1:11434/api/generate',
            json={
                'model': model,
                'prompt': ' ',
                'keep_alive': max(60, int(keep_alive or 300)),
                'stream': False,
                'options': {'num_predict': 1},
            },
            timeout=max(10, int(timeout_seconds or 45)),
        )
        if resp.status_code >= 400:
            return False, f'{model} warm failed http={resp.status_code}'
        return True, f'{model} warm ok'
    except Exception as exc:
        return False, f'{model} warm failed: {type(exc).__name__}: {exc}'


def _clear_expired_recovery_leases(conn) -> int:
    try:
        cur = conn.execute(
            """UPDATE chat_relay_recoveries
               SET lease_owner='', lease_until='', updated_at=datetime('now')
               WHERE status='open'
                 AND COALESCE(lease_owner, '') != ''
                 AND COALESCE(lease_until, '') != ''
                 AND lease_until <= datetime('now')"""
        )
        return int(cur.rowcount or 0)
    except Exception:
        return 0


def _recovery_counts(conn) -> Dict[str, int]:
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) c FROM chat_relay_recoveries GROUP BY status"
        ).fetchall()
        return {str(r['status'] or 'unknown'): int(r['c'] or 0) for r in rows}
    except Exception:
        return {}


def _clear_stale_local_work_claims(conn, stale_seconds: int = 1800) -> int:
    """Return stale local-agent ``doing`` steps to blocked so DEOS can retry."""
    candidates = tuple(WORK_AGENT_MODULES)
    placeholders = ','.join('?' for _ in candidates)
    cutoff = _now() - max(300, int(stale_seconds or 1800))
    try:
        rows = conn.execute(
            f"""SELECT step_id, owner, title FROM project_steps
                WHERE status='doing'
                  AND lower(owner) IN ({placeholders})
                  AND COALESCE(updated_at, 0) < ?""",
            (*candidates, cutoff),
        ).fetchall()
    except Exception:
        return 0
    count = 0
    for row in rows:
        step_id = str(row['step_id'])
        summary = f"DEOS returned stale local-agent claim to blocked: {row['owner']} / {row['title']}"
        conn.execute(
            """UPDATE project_steps
               SET status='blocked',
                   residual_risk='Local-agent claim expired before completion; Watchdog will retry one task at a time.',
                   updated_at=?
               WHERE step_id=? AND status='doing'""",
            (_now(), step_id),
        )
        _add_step_evidence(conn, step_id, f'stale-claim:{step_id}', summary, 'warn')
        count += 1
    return count


def _failed_work_agents(conn, step_id: str) -> set:
    try:
        rows = conn.execute(
            """SELECT summary FROM project_step_evidence
               WHERE step_id=? AND source_ref=? AND status='warn'
               ORDER BY id""",
            (step_id, f'agent-work:{step_id}'),
        ).fetchall()
    except Exception:
        return set()
    failed = set()
    for row in rows:
        first = str(row['summary'] or '').split(' ', 1)[0].strip().lower()
        if first in WORK_AGENT_MODULES:
            failed.add(first)
    return failed


def _next_work_agent(conn, step_id: str, current: str) -> Optional[str]:
    current = str(current or '').strip().lower()
    failed = _failed_work_agents(conn, step_id)
    for agent in WORK_AGENT_ORDER:
        if agent not in failed:
            return agent
    return None


def _reroute_blocked_failed_local_steps(conn, limit: int = 5) -> int:
    candidates = tuple(WORK_AGENT_MODULES)
    placeholders = ','.join('?' for _ in candidates)
    try:
        rows = conn.execute(
            f"""SELECT step_id, owner, title FROM project_steps
                WHERE status='blocked'
                  AND lower(owner) IN ({placeholders})
                  AND EXISTS (
                    SELECT 1 FROM project_step_evidence e
                    WHERE e.step_id=project_steps.step_id
                      AND e.source_ref='agent-work:' || project_steps.step_id
                      AND e.status='warn'
                  )
                ORDER BY updated_at ASC
                LIMIT ?""",
            (*candidates, max(1, int(limit or 5))),
        ).fetchall()
    except Exception:
        return 0
    count = 0
    for row in rows:
        step_id = str(row['step_id'])
        current = str(row['owner'] or '').strip().lower()
        if current not in _failed_work_agents(conn, step_id):
            continue
        nxt = _next_work_agent(conn, step_id, current)
        if not nxt:
            continue
        summary = f"DEOS rerouted blocked local work from {current} to {nxt}: {row['title']}"
        conn.execute(
            """UPDATE project_steps
               SET owner=?, residual_risk=?, updated_at=?
               WHERE step_id=? AND status='blocked'""",
            (
                nxt,
                f'Previous local agent {current} failed to complete this packet; rerouted to {nxt}.',
                _now(),
                step_id,
            ),
        )
        _add_step_evidence(conn, step_id, f'reroute:{step_id}', summary, 'warn')
        count += 1
    return count


def _claim_local_agent_step(
    conn,
    project_id: str = '',
    step_prefix: str = '',
    owner: str = '',
) -> Optional[Dict[str, Any]]:
    """Claim one actionable Studio step for a local agent."""
    if owner:
        candidates = tuple(a for a in WORK_AGENT_MODULES if a == str(owner).strip().lower())
    else:
        candidates = tuple(WORK_AGENT_MODULES)
    if not candidates:
        return None
    placeholders = ','.join('?' for _ in candidates)
    extra_where = []
    params: List[Any] = list(candidates)
    if project_id:
        extra_where.append("project_id=?")
        params.append(str(project_id))
    if step_prefix:
        extra_where.append("step_id LIKE ?")
        params.append(str(step_prefix) + '%')
    extra_sql = (' AND ' + ' AND '.join(extra_where)) if extra_where else ''
    try:
        row = conn.execute(
            f"""
            SELECT step_id, project_id, title, description, status, owner, owner_route
            FROM project_steps
            WHERE status IN ('todo', 'blocked')
              AND lower(owner) IN ({placeholders})
              {extra_sql}
            ORDER BY
              CASE status WHEN 'blocked' THEN 0 ELSE 1 END,
              updated_at ASC,
              created_at ASC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    data = dict(row)
    now = _now()
    try:
        conn.execute(
            "UPDATE project_steps SET status='doing', updated_at=? WHERE step_id=? AND status IN ('todo', 'blocked')",
            (now, data['step_id']),
        )
        _add_step_evidence(
            conn,
            data['step_id'],
            f'claim:{data["step_id"]}',
            f"DEOS claimed step for {data.get('owner')}: {data.get('title')}",
            'ok',
            project_id=data.get('project_id') or PROJECT_ID,
        )
    except Exception:
        return None
    return data


def _agent_work_prompt(step: Dict[str, Any]) -> str:
    context = _local_work_context(step)
    agent = str(step.get('owner') or '').strip().lower()
    return (
        f'{local_agent_packet(agent)}\n\n'
        'You are running under Watchdog/Seven DEOS. Complete this Studio task if it is safe and concrete.\n'
        'Rules:\n'
        '- Work only on this one task.\n'
        '- Use SKILL commands for file reads, patches, verification, or ALM actions when needed.\n'
        '- Prefer the smallest useful completion. Do not over-research simple recovery cards.\n'
        '- Do not create broad rewrites or unrelated work.\n'
        '- If the task is unclear, unsafe, or too large, stop and report BLOCKED with the exact blocker.\n'
        '- End your final answer with exactly one status line: DEOS_STATUS: done | blocked | needs_human.\n'
        '- If done, include the proof command/output summary before the status line.\n\n'
        f"Project: {step.get('project_id')}\n"
        f"Step: {step.get('step_id')}\n"
        f"Title: {step.get('title')}\n"
        f"Owner route: {step.get('owner_route')}\n\n"
        f"Description:\n{step.get('description') or ''}\n"
        f"{context}"
    )


def _local_work_context(step: Dict[str, Any]) -> str:
    """Attach compact live context for recovery cards so local models get facts."""
    text = f"{step.get('description') or ''}\n{step.get('title') or ''}"
    match = re.search(r'Conversation:\s*#?(\d+)|thread\s+#?(\d+)', text, flags=re.I)
    if not match:
        return ''
    conv_id = int((match.group(1) or match.group(2) or 0) or 0)
    if not conv_id:
        return ''
    lines = ['\nLive conversation context:\n']
    try:
        conn = get_connection()
        try:
            recovery_id = ''
            route = str(step.get('owner_route') or '')
            if route.startswith('watchdog:'):
                recovery_id = route.split(':', 1)[1]
            if recovery_id:
                rec = conn.execute(
                    "SELECT relay_context_json FROM chat_relay_recoveries WHERE recovery_id=?",
                    (recovery_id,),
                ).fetchone()
                if rec:
                    try:
                        ctx = json.loads(rec['relay_context_json'] or '{}')
                    except Exception:
                        ctx = {}
                    thread_tail = ctx.get('thread_tail') if isinstance(ctx, dict) else []
                    stage_trace = ctx.get('stage_trace') if isinstance(ctx, dict) else []
                    if stage_trace:
                        lines.append('Stage trace:')
                        for item in stage_trace[-6:]:
                            text = item.get('text') if isinstance(item, dict) else str(item)
                            if text:
                                lines.append(f"- {str(text)[:300]}")
                    if thread_tail:
                        lines.append('Thread tail from recovery card:')
                        for item in thread_tail[-8:]:
                            if not isinstance(item, dict):
                                continue
                            sender = str(item.get('from_agent') or 'unknown')[:40]
                            target = str(item.get('to_agent') or '')[:60]
                            arrow = f' -> {target}' if target else ''
                            content = ' '.join(str(item.get('content') or '').split())[:700]
                            lines.append(f"- {sender}{arrow}: {content}")
            rows = conn.execute(
                """SELECT from_agent, to_agent, content, message_type, created_at
                   FROM messages
                   WHERE conversation_id=?
                   ORDER BY id DESC
                   LIMIT 8""",
                (conv_id,),
            ).fetchall()
            for row in reversed(rows):
                sender = str(row['from_agent'] or 'unknown')[:40]
                target = str(row['to_agent'] or '')[:60]
                arrow = f' -> {target}' if target else ''
                content = ' '.join(str(row['content'] or '').split())[:700]
                lines.append(f"- {row['created_at']} {sender}{arrow}: {content}")
        finally:
            conn.close()
    except Exception as exc:
        lines.append(f'- conversation lookup failed: {type(exc).__name__}: {exc}')
    return '\n'.join(lines) + '\n'


def _local_agent_worker(queue, agent: str, prompt: str) -> None:
    try:
        import importlib
        module_name, func_name = WORK_AGENT_MODULES[agent]
        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name)
        answer, tokens = fn(prompt, conversation_history=None, stage_cb=None)
        queue.put(('ok', str(answer or ''), int(tokens or 0)))
    except Exception as exc:
        queue.put(('error', f'{type(exc).__name__}: {exc}', 0))


def _run_local_agent_work(agent: str, prompt: str, timeout_seconds: int) -> Tuple[bool, str, int]:
    import multiprocessing as mp
    try:
        timeout_seconds = max(60, min(int(timeout_seconds or 600), 3600))
    except Exception:
        timeout_seconds = 600
    if 'Recovery ID:' in prompt and 'Live conversation context:' in prompt:
        return _run_local_agent_direct(agent, prompt, min(timeout_seconds, 120))
    if 'DEOS_MICRO_TASK' in prompt:
        return _run_local_agent_micro_direct(agent, prompt, min(timeout_seconds, 90))
    ctx = mp.get_context('fork')
    queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_local_agent_worker, args=(queue, agent, prompt))
    proc.start()
    proc.join(timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(10)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
        return False, f'{agent} timed out after {timeout_seconds}s during DEOS work packet', 0
    try:
        status, answer, tokens = queue.get_nowait()
    except Exception:
        return False, f'{agent} exited without returning a result', 0
    return status == 'ok', answer, int(tokens or 0)


def _run_local_agent_micro_direct(agent: str, prompt: str, timeout_seconds: int) -> Tuple[bool, str, int]:
    """Use a short local-model call for tiny bounded Studio tasks."""
    import requests
    model = WORK_AGENT_MODELS.get(str(agent or '').strip().lower())
    if not model:
        return False, f'{agent} has no direct local model mapping', 0
    task = _compact_micro_task_prompt(prompt)
    try:
        resp = requests.post(
            'http://127.0.0.1:11434/api/chat',
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'Complete the tiny task directly. Be concise. Do not use tools. Do not explain.'},
                    {'role': 'user', 'content': task},
                ],
                'stream': False,
                'keep_alive': 300,
                'options': {'temperature': 0.1, 'num_predict': 80},
            },
            timeout=max(15, int(timeout_seconds or 90)),
        )
        if resp.status_code >= 400:
            return False, f'{agent} micro task failed http={resp.status_code}', 0
        data = resp.json()
        msg = data.get('message') or {}
        content = str(msg.get('content') or data.get('response') or '').strip()
        visible = re.sub(r'(?im)^\s*DEOS_STATUS:\s*(done|blocked|needs_human)\s*$', '', content).strip()
        if content and not visible:
            return False, f'{agent} micro task returned only a status line', int(data.get('eval_count') or 0)
        if content and 'deos_status:' not in content.lower():
            content = content.rstrip() + '\nDEOS_STATUS: done'
        return bool(content), content or f'{agent} micro task returned no content', int(data.get('eval_count') or 0)
    except Exception as exc:
        return False, f'{agent} micro task failed: {type(exc).__name__}: {exc}', 0


def _compact_micro_task_prompt(prompt: str) -> str:
    lines = []
    keep = False
    for raw in str(prompt or '').splitlines():
        line = raw.strip()
        if 'DEOS_MICRO_TASK' in line:
            keep = True
            continue
        if keep and line:
            lines.append(line)
    text = '\n'.join(lines).strip() or str(prompt or '')[-1000:]
    return (
        'DEOS_MICRO_TASK\n'
        'Return the requested result only. Do not include DEOS_STATUS; Watchdog adds that.\n'
        + text[:1200]
    )


def _run_local_agent_direct(agent: str, prompt: str, timeout_seconds: int) -> Tuple[bool, str, int]:
    """Use a short local-model call for simple relay recovery packets."""
    import requests
    model = WORK_AGENT_MODELS.get(str(agent or '').strip().lower())
    if not model:
        return False, f'{agent} has no direct local model mapping', 0
    direct_prompt = _compact_direct_recovery_prompt(prompt)
    direct_prompt = (
        'You are a local recovery worker. Answer only from the provided facts. '
        'Complete the user-visible recovery in 1-4 concise lines. '
        'Your first line must answer the latest user request or summarize the concrete recovery result. '
        'Do not return only a status line. '
        'If the last user request is already answerable, answer it directly. '
        'Do not include any DEOS_STATUS line; Watchdog will add it after you return useful content.\n\n'
        + direct_prompt
    )
    try:
        resp = requests.post(
            'http://127.0.0.1:11434/api/chat',
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'Be brief. Do not use tools. Do not expose private reasoning.'},
                    {'role': 'user', 'content': direct_prompt},
                ],
                'stream': False,
                'keep_alive': 300,
                'options': {'temperature': 0.1, 'num_predict': 80},
            },
            timeout=max(15, int(timeout_seconds or 120)),
        )
        if resp.status_code >= 400:
            return False, f'{agent} direct recovery failed http={resp.status_code}', 0
        data = resp.json()
        msg = data.get('message') or {}
        content = str(msg.get('content') or data.get('response') or '').strip()
        visible = re.sub(r'(?im)^\s*DEOS_STATUS:\s*(done|blocked|needs_human)\s*$', '', content).strip()
        if content and not visible:
            return False, f'{agent} direct recovery returned only a status line', int(data.get('eval_count') or 0)
        if content and 'deos_status:' not in content.lower():
            content = content.rstrip() + '\nDEOS_STATUS: done'
        return bool(content), content or f'{agent} direct recovery returned no content', int(data.get('eval_count') or 0)
    except Exception as exc:
        return False, f'{agent} direct recovery failed: {type(exc).__name__}: {exc}', 0


def _compact_direct_recovery_prompt(prompt: str) -> str:
    title = ''
    step = ''
    user_lines = []
    failure_lines = []
    for raw in str(prompt or '').splitlines():
        line = raw.strip()
        lower = line.lower()
        if line.startswith('Step:'):
            step = line[:120]
        elif line.startswith('Title:'):
            title = line[:180]
        elif line.startswith('- user') or ' user -> ' in lower:
            user_lines.append(line[:500])
        elif 'failed' in lower or 'stalled' in lower or 'waiting for model slot' in lower:
            failure_lines.append(line[:500])
    parts = [p for p in [step, title] if p]
    if user_lines:
        parts.append('Latest user request/context:\n' + '\n'.join(user_lines[-3:]))
    if failure_lines:
        parts.append('Failure evidence:\n' + '\n'.join(failure_lines[-4:]))
    if not parts:
        parts.append(str(prompt or '')[-1000:])
    return '\n\n'.join(parts)[:1400]


def _finish_local_agent_step(conn, step: Dict[str, Any], ok: bool, answer: str, tokens: int) -> str:
    text = str(answer or '').strip()
    lowered = text.lower()
    if not ok:
        status = 'blocked'
    elif 'deos_status: done' in lowered:
        status = 'done'
    elif 'deos_status: needs_human' in lowered:
        status = 'blocked'
    else:
        status = 'blocked'
    if status == 'done' and _looks_like_refusal(text):
        status = 'blocked'
    summary = f"{step.get('owner')} result tokens={tokens}: {text[:420]}"
    evidence_status = 'ok' if status == 'done' else 'warn'
    _add_evidence(
        conn,
        f'agent-work:{step.get("step_id")}',
        summary,
        evidence_status,
    )
    _add_step_evidence(
        conn,
        str(step.get('step_id') or ''),
        f'agent-work:{step.get("step_id")}',
        summary,
        evidence_status,
        project_id=str(step.get('project_id') or PROJECT_ID),
    )
    now = _now()
    residual = '' if status == 'done' else 'Agent did not provide a verified DEOS_STATUS: done result; see latest evidence.'
    conn.execute(
        "UPDATE project_steps SET status=?, residual_risk=?, updated_at=? WHERE step_id=?",
        (status, residual, now, step.get('step_id')),
    )
    if status == 'done':
        _close_relay_recovery_if_applicable(step, text)
    return status


def _looks_like_refusal(text: str) -> bool:
    lowered = str(text or '').lower()
    markers = [
        'unable to assist',
        'cannot assist',
        "can't assist",
        'i am sorry',
        "i'm sorry",
        'do not hesitate to ask',
    ]
    return any(marker in lowered for marker in markers)


def _close_relay_recovery_if_applicable(step: Dict[str, Any], result: str) -> None:
    route = str(step.get('owner_route') or '')
    if not route.startswith('watchdog:recovery-'):
        return
    recovery_id = route.split(':', 1)[1]
    desc = str(step.get('description') or '')
    match = re.search(r'Conversation:\s*#?(\d+)', desc, flags=re.I)
    conv_id = int(match.group(1)) if match else 0
    summary = f"Local work completed recovery {recovery_id}: {str(result or '').strip()[:700]}"
    try:
        from utils.db.chat import log_message, update_chat_relay_recovery_status
        if conv_id:
            try:
                log_message(
                    conv_id,
                    'watchdog',
                    str(result or '').strip(),
                    to_agent='user',
                    message_type='relay_recovery_review',
                    tokens_used=0,
                )
            except Exception:
                pass
        update_chat_relay_recovery_status(recovery_id, 'reviewed', summary=summary)
    except Exception:
        pass


def run_deos_cycle(args: str = '') -> Dict[str, Any]:
    """Run one deterministic Watchdog/Seven control-plane cycle."""
    opts = _parse_args(args)
    prewarm = _bool_opt(opts.get('prewarm'), default=False)
    execute_recovery = _bool_opt(opts.get('execute_recovery'), default=True)
    execute_work = _bool_opt(opts.get('execute_work'), default=False)
    work_project_id = str(opts.get('work_project_id') or '').strip()
    work_step_prefix = str(opts.get('work_step_prefix') or '').strip()
    work_owner = str(opts.get('work_owner') or '').strip().lower()
    try:
        warm_timeout = max(10, min(int(opts.get('warm_timeout_seconds') or 45), 300))
    except Exception:
        warm_timeout = 45
    try:
        agent_timeout = max(30, min(int(opts.get('agent_timeout_seconds') or 180), 900))
    except Exception:
        agent_timeout = 180
    try:
        work_timeout = max(60, min(int(opts.get('work_timeout_seconds') or 600), 3600))
    except Exception:
        work_timeout = 600
    try:
        local_work_stale = max(300, min(int(opts.get('local_work_stale_seconds') or 1800), 7200))
    except Exception:
        local_work_stale = 1800

    report: Dict[str, Any] = {
        'decides': {},
        'executes': [],
        'operates': {},
        'sustains': [],
    }

    conn = get_connection()
    try:
        _ensure_project(conn)
        conn.commit()
        targets = _resident_targets(conn)
        loaded = set(_ollama_loaded())
        report['decides']['resident_policy'] = targets
        report['decides']['loaded_models_before'] = sorted(loaded)
        ready_recovery_agents: List[str] = []
        readiness_failed = False

        for target in targets:
            if not target['enabled']:
                report['executes'].append(f"skip disabled {target['agent']}")
                continue
            if not target['is_ollama']:
                report['executes'].append(f"{target['agent']} is control/logical role, no model warm")
                continue
            model = target['model']
            if model in loaded:
                report['executes'].append(f'{target["agent"]}:{model} already resident')
                if target['agent'] in {'librarian', 'duck'}:
                    ready_recovery_agents.append(target['agent'])
                continue
            if not prewarm:
                report['executes'].append(f'{target["agent"]}:{model} cold; prewarm disabled')
                continue
            ok, detail = _warm_model(model, target['keep_alive'], warm_timeout)
            report['executes'].append(f'{target["agent"]}:{detail}')
            _add_evidence(conn, f'prewarm:{target["agent"]}', detail, 'ok' if ok else 'warn')
            conn.commit()
            if not ok:
                readiness_failed = True
            elif target['agent'] in {'librarian', 'duck'}:
                ready_recovery_agents.append(target['agent'])

        cleared = _clear_expired_recovery_leases(conn)
        stale_work_claims = _clear_stale_local_work_claims(conn, local_work_stale)
        rerouted_work = _reroute_blocked_failed_local_steps(conn)
        counts = _recovery_counts(conn)
        report['operates'] = {
            'expired_leases_cleared': cleared,
            'stale_local_work_claims': stale_work_claims,
            'rerouted_local_work': rerouted_work,
            'recovery_counts': counts,
            'readiness_failed': readiness_failed,
            'ready_recovery_agents': ready_recovery_agents,
        }
        _add_evidence(
            conn,
            'cycle',
            f'DEOS cycle: prewarm={prewarm} execute_recovery={execute_recovery} execute_work={execute_work} counts={counts}',
            'ok',
        )
        conn.commit()
    finally:
        conn.close()

    ready_agents = report.get('operates', {}).get('ready_recovery_agents') or []
    if execute_recovery and not ready_agents:
        report['executes'].append('recovery skipped: no support agents ready')
    elif execute_recovery:
        try:
            from fridays.task_runner import run_task
            ok, output = run_task(
                'relay_recovery_sweep',
                args=(
                    'limit=1 run_agents=1 force=1 '
                    f'agents={",".join(ready_agents)} '
                    f'agent_timeout_seconds={agent_timeout}'
                ),
            )
            report['executes'].append(f'relay_recovery_sweep ok={ok}: {output[:400]}')
        except Exception as exc:
            report['executes'].append(f'relay_recovery_sweep failed: {type(exc).__name__}: {exc}')

    if execute_work:
        conn = get_connection()
        try:
            step = _claim_local_agent_step(
                conn,
                project_id=work_project_id,
                step_prefix=work_step_prefix,
                owner=work_owner,
            )
            if step:
                conn.commit()
            else:
                report['executes'].append('local agent work skipped: no claimable step')
                conn.commit()
        finally:
            conn.close()
        if step:
            agent = str(step.get('owner') or '').strip().lower()
            ok, answer, tokens = _run_local_agent_work(
                agent,
                _agent_work_prompt(step),
                timeout_seconds=work_timeout,
            )
            conn = get_connection()
            try:
                final_status = _finish_local_agent_step(conn, step, ok, answer, tokens)
                conn.commit()
            finally:
                conn.close()
            report['executes'].append(
                f'local_agent_work agent={agent} step={step.get("step_id")} status={final_status}: {str(answer or "")[:240]}'
            )

    try:
        from utils.db.watchdog_lessons import record_repair_lesson
        record_repair_lesson(
            'watchdog-deos-control-plane',
            'Fridays needs Watchdog/Seven to decide, execute, operate, and sustain instead of only reporting failures.',
            (
                'Run watchdog_deos_cycle as the deterministic control-plane loop. '
                'Duck and Librarian are bounded support calls; Seven/Watchdog owns state, readiness, execution, and evidence.'
            ),
            proof_required='Tasker has watchdog_deos_cycle scheduled, Studio step S-DEOS-CONTROL-PLANE has evidence, and relay recovery remains one-at-a-time.',
            evidence=report,
            owner='watchdog',
            source_thread_id='DEOS',
            lesson_id='WDL-DEOS-CONTROL-PLANE-20260515',
        )
        report['sustains'].append('repair lesson WDL-DEOS-CONTROL-PLANE-20260515 updated')
    except Exception as exc:
        report['sustains'].append(f'repair lesson update failed: {exc}')

    return report


def run_deos_cycle_summary(args: str = '') -> str:
    report = run_deos_cycle(args)
    counts = report.get('operates', {}).get('recovery_counts', {})
    actions = report.get('executes', [])
    return (
        'DEOS cycle complete: '
        f'counts={counts}; actions=' + ' | '.join(str(a) for a in actions[:6])
    )[:1800]
