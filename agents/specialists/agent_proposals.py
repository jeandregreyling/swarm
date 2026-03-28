"""
agent_proposals.py — Seven's Swarm / Phase 6 Agent Agency
═══════════════════════════════════════════════════════════════════════════════
Play time routine: when an agent has been idle for 1+ hours, it reads the KB
docs and shared sandpit, drafts an improvement proposal, and writes it to
sandpits/shared/proposals/. Sniffles audits it. swarm_tasks picks it up and
emails Ghost.

Rules:
- Play time fires at most once per agent per 24 hours.
- Agents can only write to sandpits/shared/proposals/ during play time.
- Sniffles must PASS the proposal before Ghost is notified.
- Proposals are additive only — agents propose new KB docs or system ideas.
- Ghost always decides whether a proposal becomes real.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
sys.path.insert(0, '/home/seven/swarm')

import ollama
from database import get_connection, get_project_docs, log_activity
from sandpits import write_proposal, list_files, read_shared, list_proposals, PROPOSALS_DIR
from sniffer import sniff_sandpit
from config import (
    GEMMA_SYSTEM_PROMPT, LLAMA_SYSTEM_PROMPT,
    QWEN_SYSTEM_PROMPT, EIGHT_SYNTHESIS_PROMPT
)
import os
from datetime import datetime, timedelta

# One play-time run per agent per 24 hours
PLAY_COOLDOWN_HOURS = 24
# Idle threshold — no activity for this many seconds
IDLE_THRESHOLD_SECONDS = 3600


def _is_idle():
    """
    Returns True if the swarm has been quiet for IDLE_THRESHOLD_SECONDS.
    Checks activity_log for non-task-check events in the past hour.
    """
    conn = get_connection()
    row = conn.execute(
        """SELECT MAX(created_at) FROM activity_log
           WHERE event != 'task_check'
           AND created_at > datetime('now', ?)""",
        (f'-{IDLE_THRESHOLD_SECONDS} seconds',)
    ).fetchone()
    conn.close()
    # If no recent activity — idle
    return row[0] is None


def _last_play_time(agent):
    """Return datetime of agent's last proposal write, or None."""
    conn = get_connection()
    row = conn.execute(
        """SELECT MAX(created_at) FROM activity_log
           WHERE service=? AND event='play_time_proposal'""",
        (agent,)
    ).fetchone()
    conn.close()
    if row[0]:
        try:
            return datetime.fromisoformat(row[0])
        except Exception:
            pass
    return None


def _cooldown_passed(agent):
    """Return True if agent hasn't run play time in the last 24 hours."""
    last = _last_play_time(agent)
    if last is None:
        return True
    return datetime.now() - last > timedelta(hours=PLAY_COOLDOWN_HOURS)


def _build_context(agent):
    """Build context block: KB docs + shared sandpit files + agent role."""
    lines = [f'You are {agent.capitalize()}, a member of Seven\'s Swarm.',
             'It is currently your play time — the swarm is idle.',
             'Your task: review available knowledge and propose ONE improvement.',
             '']

    # KB docs relevant to this agent or all agents
    docs = get_project_docs(tag='all') + get_project_docs(tag=agent.lower())
    if docs:
        lines.append('=== Knowledge Base ===')
        for doc in docs[:5]:  # Limit to avoid token overload
            lines.append(f'--- {doc["doc_name"]} ---')
            lines.append((doc['content'] or '')[:600])
            lines.append('')

    # Shared sandpit files (excluding proposals subfolder)
    try:
        shared_path = '/home/seven/swarm/sandpits/shared'
        for fname in sorted(os.listdir(shared_path)):
            fpath = os.path.join(shared_path, fname)
            if os.path.isfile(fpath) and fname.endswith(('.md', '.txt')):
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines.append(f'=== Shared: {fname} ===')
                    lines.append(f.read()[:400])
                    lines.append('')
    except Exception:
        pass

    lines.append('=== Proposal Instructions ===')
    lines.append('Write a short proposal (150-300 words) using this structure:')
    lines.append('# Proposal: <title>')
    lines.append('**Agent:** ' + agent.capitalize())
    lines.append('**Date:** ' + datetime.now().strftime('%Y-%m-%d'))
    lines.append('')
    lines.append('## What I propose')
    lines.append('<One clear improvement — a new KB doc, a pipeline enhancement, a system idea>')
    lines.append('')
    lines.append('## Why')
    lines.append('<Specific reasoning — what problem does this solve?>')
    lines.append('')
    lines.append('## Impact')
    lines.append('<Who benefits and how?>')
    lines.append('')
    lines.append('Rules: Do not propose deleting existing config. Do not propose anything requiring system access.')
    lines.append('Propose only one thing. Be specific. Be brief.')

    return '\n'.join(lines)


def _model_for_agent(agent):
    """Return the Ollama model name for this agent."""
    from config import GEMMA_SYSTEM_PROMPT, LLAMA_SYSTEM_PROMPT, QWEN_SYSTEM_PROMPT
    models = {
        'gemma':  ('gemma3:latest',   GEMMA_SYSTEM_PROMPT),
        'llama':  ('llama3.2:latest', LLAMA_SYSTEM_PROMPT),
        'qwen':   ('qwen2.5:latest',  QWEN_SYSTEM_PROMPT),
        'eight':  ('qwen2.5:latest',  EIGHT_SYNTHESIS_PROMPT),
    }
    return models.get(agent.lower(), ('qwen2.5:latest', ''))


def draft_proposal(agent):
    """
    Ask the agent model to draft a proposal. Returns the proposal text or None.
    """
    model, system_prompt = _model_for_agent(agent)
    context = _build_context(agent)

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': context},
            ],
            options={'temperature': 0.7}
        )
        content = response['message']['content'].strip()
        return content if content else None
    except Exception as e:
        print(f'[Proposals] Draft failed for {agent}: {e}')
        return None


def run_play_time(agent):
    """
    Full play-time sequence for one agent:
    1. Check idle + cooldown
    2. Draft proposal
    3. Sniffles audit
    4. Write to proposals/ if PASS/WARN
    5. Log to activity_log
    Returns (True, path) if proposal written, (False, reason) otherwise.
    """
    print(f'[Proposals] Checking play time for {agent}...')

    if not _is_idle():
        return False, 'swarm not idle'

    if not _cooldown_passed(agent):
        return False, f'{agent} played within last {PLAY_COOLDOWN_HOURS}h'

    print(f'[Proposals] {agent} drafting proposal...')
    proposal_text = draft_proposal(agent)
    if not proposal_text:
        return False, 'draft failed'

    # Sniffles audit before writing
    audit_result = sniff_sandpit(proposal_text, agent, f'{agent}_proposal.md')
    print(f'[Proposals] Sniffles audit for {agent}: {audit_result[:80]}')

    if 'FLAG' in audit_result.upper()[:10]:
        log_activity(agent, 'play_time_flagged', audit_result[:200])
        print(f'[Proposals] {agent} proposal FLAGGED by Sniffles — not submitted')
        return False, f'Sniffles flagged: {audit_result[:100]}'

    # Write proposal (PASS or WARN both proceed — WARN will be visible in review queue)
    ok, path = write_proposal(agent, proposal_text)
    if not ok:
        return False, f'write failed: {path}'

    log_activity(agent, 'play_time_proposal', os.path.basename(path))
    print(f'[Proposals] {agent} proposal written: {path}')
    return True, path


def run_all_idle_agents():
    """
    Run play time for all eligible agents. Called from swarm_tasks when queue is quiet.
    Only one agent runs per call to avoid model pile-up.
    """
    agents = ['gemma', 'llama', 'qwen', 'eight']
    for agent in agents:
        if not _cooldown_passed(agent):
            continue
        ok, result = run_play_time(agent)
        if ok:
            print(f'[Proposals] Play time complete for {agent}: {result}')
            return agent, result  # One agent per cycle
    return None, 'no eligible agents'


if __name__ == '__main__':
    import sys
    agent = sys.argv[1] if len(sys.argv) > 1 else 'qwen'
    ok, result = run_play_time(agent)
    print(f'Result: {ok} — {result}')
