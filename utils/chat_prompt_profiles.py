"""Central prompt policy blocks for chat agents."""


AUDIT_AGENTS = {'duck', 'sniffles'}
READ_ONLY_GUARD_MARKER = 'WATCHDOG READ-ONLY ROUTING GUARD'


def chat_handoff_contract(agent_name, deadline_seconds):
    return (
        "\n\n=== FRIDAYS STUDIO HANDOFF TIMER ===\n"
        f"You are running as {agent_name}. Your visible deadline is {int(deadline_seconds)} seconds.\n"
        "Before that deadline, answer with the useful work you have completed so far. "
        "If you cannot finish, end with a compact SELF-HANDOFF containing: current finding, "
        "next action, files/tables touched, risks, and the exact prompt to continue in the next window. "
        "Do not wait silently for perfect completion.\n"
        "=== END TIMER CONTRACT ===\n"
    )


def audit_prefix(agent_name):
    if str(agent_name or '').strip().lower() not in AUDIT_AGENTS:
        return ''
    return (
        '=== Audit mode ===\n'
        'Review the thread and latest user message. Focus on factual consistency, risk,'
        ' contradictions, and missing assumptions. Return concise findings only.\n\n'
    )


def read_only_guard(prefix_for_system_prompt=False):
    if prefix_for_system_prompt:
        return (
            f'\n\n=== {READ_ONLY_GUARD_MARKER} ===\n'
            'The latest user message is informational/status-seeking. '
            'Do not create proposals, approve work, complete work, or modify files. '
            'Use read-only inspection only. If the request is ambiguous, ask "What do you mean?" '
            'with the missing target/context.\n'
            f'=== END {READ_ONLY_GUARD_MARKER} ===\n'
        )
    return (
        f'=== {READ_ONLY_GUARD_MARKER} ===\n'
        'This is a status/informational chat turn. Do not create proposals, approve work, '
        'complete work, or modify files. Use read-only inspection only. If the request is '
        'ambiguous, ask "What do you mean?" with the missing target/context.\n'
        f'=== END {READ_ONLY_GUARD_MARKER} ===\n\n'
    )


def relay_policy_prefix(auto_relay):
    if auto_relay:
        return '[Auto Relay: ENABLED]\n'
    return (
        '=== RELAY DISABLED - HARD RULE ===\n'
        'Auto Relay is OFF. You MUST NOT route, forward, ask, or mention any other agent '
        'in your response. Do not write "Route to X", "Ask Ten", "-> Eight", or any similar '
        'phrasing. Handle the entire task yourself. If you are uncertain, write a note in '
        'your sandpit and continue alone. Violating this rule breaks the interface.\n'
        '=================================\n\n'
    )


def execution_confirmation_suffix():
    return (
        '\n\n=== EXECUTION CONFIRMATION ===\n'
        'User explicitly approved execution. If your next step is to create a work proposal, '
        'output exactly one executable command line in this format and then brief context:\n'
        'SKILL alm_create_proposal "<title>" "<description>"\n'
        'Do not ask for reconfirmation.'
    )


_HAT_ROLES = {
    'gemma': 'director: plans, delegates, keeps the operator informed',
    'mistral': 'coder and analyst: reads code, writes proposals',
    'duck': 'reviewer: checks proposals, finds flaws',
}


def self_awareness_block(agent_name):
    """Live "where and what am I" facts so a hat can answer about itself."""
    import os
    import sqlite3
    agent = str(agent_name or '').lower()
    model = '?'
    tables = []
    parked = []
    try:
        from utils.db import get_connection
        conn = get_connection()
        try:
            row = conn.execute('SELECT model FROM agents WHERE name=?', (agent,)).fetchone()
            model = (row[0] if row else '?') or '?'
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'memory_%' ORDER BY name")]
            parked = [r[0] for r in conn.execute(
                "SELECT name FROM agents WHERE registry_status='parked' ORDER BY name")]
        finally:
            conn.close()
    except (sqlite3.Error, ImportError, OSError):
        pass
    stage = os.environ.get('STAGE', 'PROD')
    port = os.environ.get('PORT', '5050')
    return (
        '=== WHERE AND WHAT YOU ARE ===\n'
        f'You are {agent}, hat: {_HAT_ROLES.get(agent, "local helper")}. '
        f'Model: {model} (one shared local model wears every hat), running on Ollama, '
        f'AMD RX 6800 16 GB, Linux. Environment: {stage} on port {port} (Fridays / Seven\'s Swarm).\n'
        f'Memory tables you may read: {", ".join(tables) or "none found"}. '
        'Principles in order: 1 honesty, 2 kindness, 3 extreme logic. '
        f'If asked who or what you are, answer with exactly these facts: model {model}, '
        'hosted locally by Ollama; never name any other vendor or model. '
        'Only report what a [skill:...] result returned; otherwise say it is unverified.\n'
        f'Parked, not deleted: {", ".join(parked) or "none"}. '
        'File writes are off; you read files and raise proposals.\n'
        '=== END WHERE AND WHAT YOU ARE ===\n\n'
    )


def apply_local_chat_profile(
    *,
    agent_name,
    base_prompt,
    deadline_seconds,
    auto_relay,
    informational_request=False,
    execution_confirmation=False,
):
    prompt = str(base_prompt or '')
    if informational_request:
        prompt = read_only_guard() + prompt
    prompt = self_awareness_block(agent_name) + prompt
    prompt = chat_handoff_contract(agent_name, deadline_seconds) + '\n\n' + prompt
    prompt = relay_policy_prefix(auto_relay) + prompt
    if execution_confirmation:
        prompt += execution_confirmation_suffix()
    return prompt
