"""
agents/gemma/gemma_agent.py — Gemma (local Ollama)
Orchestrator agent. Powered by gemma3:latest via Ollama.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

_SWARM_ROOT = os.environ.get('SWARM_ROOT') or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _SWARM_ROOT not in sys.path:
    sys.path.insert(0, _SWARM_ROOT)
for _path in (
    os.path.join(_SWARM_ROOT, 'agents'),
    os.path.join(_SWARM_ROOT, 'utils'),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)

logger = logging.getLogger('seven.gemma')
AGENT_NAME = 'gemma'
MODEL = 'gemma3:latest'

_MAX_INPUT_TOKENS = 12_000
_MAX_RETRIES = 3
_CHUNK_KIND = 'quintum-chunk'
_SYNTH_KIND = 'quintum-synthesis'


def _estimate_tokens(text: str) -> int:
    return max(1, len(str(text or '')) // 4)


def _build_context(message):
    from database import get_agent_memory, get_connection

    lines = []
    try:
        from core.read_only_context import build_local_agent_context

        local_context = build_local_agent_context(AGENT_NAME, message)
        if local_context:
            lines.append("\n=== Read-only repository and Vortex context ===")
            lines.append(local_context)
    except Exception:
        logger.exception('[Gemma] read-only corpus retrieval failed')

    conn = get_connection()
    try:
        queued = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status='queued'"
        ).fetchone()[0]
        open_t = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE status='open'"
        ).fetchone()[0]
        wp = conn.execute(
            "SELECT COUNT(*) FROM work_proposals WHERE status='pending'"
        ).fetchone()[0]
        lines.append(
            f'Queue: {queued} queued | Open tickets: {open_t} | Pending proposals: {wp}'
        )
    except Exception:
        pass
    finally:
        conn.close()
    mems = get_agent_memory(AGENT_NAME, query=message, limit=5) or []
    if mems:
        lines.append("\n=== Gemma's memory ===")
        for m in mems:
            m = dict(m)
            lines.append(
                f"[{str(m.get('created_at', ''))[:16]}] "
                f"{m.get('subject', '')}: {str(m.get('content', ''))[:200]}"
            )
    return '\n'.join(lines)


def chat(message, conversation_history=None, stage_cb=None):
    def _emit(t):
        if callable(stage_cb):
            try:
                stage_cb(t, None)
            except Exception:
                pass

    from core import llm as _llm
    from config import GEMMA_SYSTEM_PROMPT

    _emit('loading context')
    context = _build_context(message)
    system = GEMMA_SYSTEM_PROMPT + f'\n\n{context}' if context else GEMMA_SYSTEM_PROMPT

    messages = [{'role': 'system', 'content': system}]
    if conversation_history:
        messages.extend(conversation_history[-8:])
    messages.append({'role': 'user', 'content': message})

    def _api_call(msgs):
        buf = []

        def _cb(piece):
            buf.append(piece)
            if len(buf) == 1 or len(buf) % 15 == 0:
                _emit(f'generating · {("".join(buf))[-300:]}')

        return _llm.chat_via_gateway(
            MODEL,
            msgs,
            stage_cb=stage_cb,
            on_chunk=_cb,
            temperature=0.7,
            response_format='json',
        )

    try:
        from agents.skill_intent import message_likely_needs_skills
        from agents.skills_loop import run_skill_loop
    except ImportError:
        from skill_intent import message_likely_needs_skills
        from skills_loop import run_skill_loop

    try:
        needs_skills = message_likely_needs_skills(message)
        answer, tokens = run_skill_loop(
            agent_name=AGENT_NAME,
            call_fn=_api_call,
            messages=messages,
            emit_fn=_emit,
            max_passes=2,
            nudge_if_no_skills=needs_skills,
        )
    except Exception as e:
        from utils.local_runtime_policy import normalize_read_only_response

        return normalize_read_only_response(AGENT_NAME, f'[gemma] error: {e}'), 0

    logger.info('[Gemma] model=%s tokens=%s', MODEL, tokens)
    return answer, tokens


def _ollama_available() -> bool:
    try:
        from core import llm as _llm

        _llm.list_models()
        return True
    except Exception as exc:
        logger.info('[watch_studio] Ollama unavailable: %s', exc)
        return False


def _blackboard_add(project_id: str, content: str, kind: str, step_id: str = '') -> None:
    try:
        from core.knowledge.projects import add_blackboard_note

        prefix = f'[step {step_id}]\n' if step_id else ''
        add_blackboard_note(
            project_id,
            prefix + content,
            author=AGENT_NAME,
            kind=kind,
        )
    except Exception as exc:
        logger.debug('[watch_studio] blackboard write failed: %s', exc)


def _probe_chunk(chunk: str, step_title: str) -> str:
    from core import llm as _llm

    msgs = [
        {
            'role': 'system',
            'content': (
                'You are a focused analyst. Read the excerpt below and produce '
                'a concise finding (3-8 sentences). Be specific; avoid padding.'
            ),
        },
        {
            'role': 'user',
            'content': f'Step: {step_title}\n\nExcerpt:\n{chunk}',
        },
    ]
    try:
        answer, _ = _llm.chat_via_gateway(MODEL, msgs, temperature=0.3)
        return (answer or '').strip()
    except Exception as exc:
        logger.warning('[watch_studio] probe_chunk error: %s', exc)
        return ''


def _synthesise(notes: list[str], step_title: str) -> str:
    from core import llm as _llm

    joined = '\n\n---\n\n'.join(notes)
    msgs = [
        {
            'role': 'system',
            'content': (
                'You are a synthesis engine. Merge the findings below into a '
                'coherent, actionable answer. Do not repeat yourself. Output '
                'plain prose.'
            ),
        },
        {
            'role': 'user',
            'content': f'Step: {step_title}\n\nFindings:\n{joined}',
        },
    ]
    try:
        answer, _ = _llm.chat_via_gateway(MODEL, msgs, temperature=0.4)
        return (answer or '').strip()
    except Exception as exc:
        logger.warning('[watch_studio] synthesise error: %s', exc)
        return ''


def _validate(synthesis: str, step_title: str) -> Optional[bool]:
    from core import llm as _llm

    msgs = [
        {
            'role': 'system',
            'content': (
                'You are a quality-gate validator. Reply with exactly one word: '
                'YES or NO. YES means the answer is accurate, complete, and '
                'actionable. NO means it is vague, wrong, or needs more work.'
            ),
        },
        {
            'role': 'user',
            'content': f'Step: {step_title}\n\nProposed answer:\n{synthesis}',
        },
    ]
    for validator_model in ('nine', 'eleven'):
        try:
            answer, _ = _llm.chat_via_gateway(validator_model, msgs, temperature=0.0)
            verdict = (answer or '').strip().upper().split()[0] if answer else 'YES'
            return verdict == 'YES'
        except Exception:
            continue
    return None


def watch_studio(max_steps: int = 3) -> list[dict[str, Any]]:
    """Work claimable Studio steps through the quintum loop."""
    if not _ollama_available():
        return []

    from core.chunk.quintum import chunk_split
    from core.knowledge.context_packs import build_project_context_block
    from core.knowledge.projects import (
        claim_step,
        list_open_steps,
        update_step,
        update_step_status,
    )

    results: list[dict[str, Any]] = []
    steps = list_open_steps(limit=max(1, int(max_steps or 1)))
    if not steps:
        logger.debug('[watch_studio] no open steps')
        return results

    for step in steps:
        step_id = str(step.get('step_id') or '')
        project_id = str(step.get('project_id') or '')
        title = str(step.get('title') or step_id)
        description = str(step.get('description') or '').strip()
        context = build_project_context_block(project_id=project_id, text=title)
        prompt_blob = '\n\n'.join(
            part for part in (f'Step: {title}', description, context) if part
        ).strip()

        if _estimate_tokens(prompt_blob) > _MAX_INPUT_TOKENS:
            update_step(step_id, owner='skip-too-large')
            results.append({'step_id': step_id, 'status': 'skip-too-large', 'retries': 0})
            continue

        if not claim_step(step_id, AGENT_NAME):
            logger.debug('[watch_studio] step %s already claimed', step_id)
            continue

        retries = 0
        final_status = 'blocked'
        chunks = chunk_split(prompt_blob or title, max_tokens=800) or [prompt_blob or title]

        while retries < _MAX_RETRIES:
            chunk_notes: list[str] = []
            for idx, chunk in enumerate(chunks, 1):
                finding = _probe_chunk(chunk, title)
                if not finding:
                    continue
                chunk_notes.append(finding)
                _blackboard_add(
                    project_id,
                    f'[chunk {idx}/{len(chunks)}]\n{finding}',
                    _CHUNK_KIND,
                    step_id=step_id,
                )

            if not chunk_notes:
                retries += 1
                continue

            synthesis = _synthesise(chunk_notes, title)
            if not synthesis:
                retries += 1
                continue

            _blackboard_add(project_id, synthesis, _SYNTH_KIND, step_id=step_id)
            verdict = _validate(synthesis, title)
            if verdict is True or verdict is None:
                final_status = 'done'
                break
            retries += 1

        update_step_status(step_id, final_status, owner=AGENT_NAME)
        results.append({'step_id': step_id, 'status': final_status, 'retries': retries})

    return results
