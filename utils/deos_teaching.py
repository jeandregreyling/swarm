"""DEOS teaching packets for local worker agents.

These strings are deliberately compact. They are injected into bounded local
work packets so Gemma/Qwen/Mistral/llama learn the operating contract without
turning every job into a long philosophy prompt.
"""
from __future__ import annotations

import re
from typing import Iterable


DEOS_LOCAL_AGENT_PACKET = """DEOS LOCAL WORKER CONTRACT
DEOS = Decides, Executes, Operates, Sustains.
You are not the control plane. Watchdog owns state, timeout, fallback, and proof.
You own exactly one claimed task packet.
Decide: restate the concrete action you can safely take.
Execute: make the smallest useful change or answer.
Operate: report what happened, including blockers and runtime failures.
Sustain: include proof, affected files/records, and final status.
Never claim completion without visible proof.
Never hide a timeout, refusal, missing file, stale service, DB lock, or unsafe action.
End with exactly one status line: DEOS_STATUS: done | blocked | needs_human."""


ROLE_HINTS = {
    'qwen': 'Prefer concise recovery reasoning, contradiction checks, and exact next actions.',
    'gemma': 'Prefer code review, correction of bad assumptions, and practical implementation guidance.',
    'mistral': 'Prefer tiny bounded tasks and short factual completions; escalate if the prompt is too large.',
    'llama': 'Prefer simple relay continuations and plain-language summaries; avoid inventing file paths.',
}


def local_agent_packet(agent: str = '') -> str:
    """Return the compact DEOS packet for a local worker."""
    name = str(agent or '').strip().lower()
    hint = ROLE_HINTS.get(name, 'Prefer bounded local work with explicit proof and blockers.')
    return f'{DEOS_LOCAL_AGENT_PACKET}\nAgent role hint: {hint}'


def studio_seed_steps(project_id: str = 'P-DEOS-OPERATING-SYSTEM-20260516') -> list[dict]:
    """Task-board scaffolding for teaching local agents how to DEOS."""
    return [
        {
            'step_id': 'S-DEOS-13-LOCAL-AI-TEACHING-PACKETS',
            'project_id': project_id,
            'title': 'Local AI DEOS teaching packets',
            'description': (
                'Inject compact DEOS worker contracts into local agent work packets so Gemma/Qwen/Mistral/llama '
                'understand one-task-at-a-time execution, proof, blockers, and final DEOS_STATUS semantics.'
            ),
            'owner': 'watchdog',
            'owner_route': 'watchdog:local-ai-teacher',
        },
        {
            'step_id': 'S-DEOS-14-HOUSE-AGENT-COACHING',
            'project_id': project_id,
            'title': 'House agent coaching loop',
            'description': (
                'Use Codex/house-agent as the teacher: create bounded Studio packets, let local agents attempt them, '
                'review their proof, write corrections into KC, and rerun until the local agents improve.'
            ),
            'owner': 'watchdog',
            'owner_route': 'watchdog:house-agent',
        },
        {
            'step_id': 'S-DEOS-15-LOCAL-AI-DRILL-QUEUE',
            'project_id': project_id,
            'title': 'Local AI DEOS drill queue',
            'description': (
                'Create repeatable tiny drills for each local worker: answer, patch, verify, recover, and escalate. '
                'Each drill must produce chat visibility, job/evidence rows, and KC lessons.'
            ),
            'owner': 'watchdog',
            'owner_route': 'watchdog:drill-queue',
        },
    ]


def format_seed_markdown(steps: Iterable[dict]) -> str:
    lines = ['# DEOS Local AI Teaching Scaffold', '']
    lines.append('The house agent teaches; local agents execute bounded packets; Watchdog enforces proof.')
    for step in steps:
        lines.append('')
        lines.append(f"## {step['step_id']} - {step['title']}")
        lines.append(step['description'])
    return '\n'.join(lines).strip() + '\n'


def evaluate_local_result(answer: str, ok: bool = True) -> dict:
    """Assess whether a local worker followed the DEOS handoff contract."""
    text = str(answer or '').strip()
    lowered = text.lower()
    status_match = re.search(r'(?im)^\s*DEOS_STATUS:\s*(done|blocked|needs_human)\s*$', text)
    status = status_match.group(1).lower() if status_match else ''
    visible = re.sub(r'(?im)^\s*DEOS_STATUS:\s*(done|blocked|needs_human)\s*$', '', text).strip()
    issues = []
    if not ok:
        issues.append('runner_failed')
    if not text:
        issues.append('empty_answer')
    if not visible:
        issues.append('no_visible_work')
    if not status:
        issues.append('missing_deos_status')
    elif status not in {'done', 'blocked', 'needs_human'}:
        issues.append('invalid_deos_status')
    if status == 'done' and not _has_proof_marker(visible):
        issues.append('missing_proof')
    if _looks_like_refusal(text):
        issues.append('refusal')
    if status in {'blocked', 'needs_human'} and not _has_blocker_detail(visible):
        issues.append('missing_blocker_detail')

    passed = ok and bool(text) and bool(visible) and status == 'done' and 'refusal' not in issues
    if 'missing_proof' in issues:
        coaching_status = 'needs_coaching'
    elif passed:
        coaching_status = 'passed'
    else:
        coaching_status = 'failed'

    return {
        'status': status,
        'visible': visible,
        'issues': issues,
        'passed': passed,
        'coaching_status': coaching_status,
        'summary': _coaching_summary(coaching_status, status, issues),
    }


def _has_proof_marker(text: str) -> bool:
    lowered = str(text or '').lower()
    markers = [
        'proof',
        'verified',
        'tested',
        'pytest',
        'curl',
        'sqlite',
        'evidence',
        'logged',
        'created',
        'updated',
        'wrote',
        'completed',
    ]
    return any(marker in lowered for marker in markers)


def _has_blocker_detail(text: str) -> bool:
    lowered = str(text or '').lower()
    markers = ['blocked', 'blocker', 'timeout', 'failed', 'missing', 'unsafe', 'locked', 'needs human']
    return any(marker in lowered for marker in markers)


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


def _coaching_summary(coaching_status: str, status: str, issues: list[str]) -> str:
    issue_text = ','.join(issues) if issues else 'none'
    return f'coaching={coaching_status} deos_status={status or "missing"} issues={issue_text}'
