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
    prompt = chat_handoff_contract(agent_name, deadline_seconds) + '\n\n' + prompt
    prompt = relay_policy_prefix(auto_relay) + prompt
    if execution_confirmation:
        prompt += execution_confirmation_suffix()
    return prompt
