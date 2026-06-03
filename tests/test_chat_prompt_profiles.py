from utils.chat_prompt_profiles import (
    READ_ONLY_GUARD_MARKER,
    apply_local_chat_profile,
    audit_prefix,
    chat_handoff_contract,
    read_only_guard,
    relay_policy_prefix,
)


def test_read_only_guard_keeps_skills_loop_marker():
    guard = read_only_guard()

    assert READ_ONLY_GUARD_MARKER in guard
    assert 'Do not create proposals' in guard
    assert 'Use read-only inspection only' in guard


def test_system_read_only_guard_can_append_to_system_prompt():
    guard = read_only_guard(prefix_for_system_prompt=True)

    assert guard.startswith('\n\n=== WATCHDOG READ-ONLY ROUTING GUARD ===')
    assert 'latest user message is informational/status-seeking' in guard


def test_audit_prefix_only_for_audit_agents():
    assert audit_prefix('duck').startswith('=== Audit mode ===')
    assert audit_prefix('sniffles').startswith('=== Audit mode ===')
    assert audit_prefix('qwen') == ''


def test_local_chat_profile_orders_relay_timer_guard_and_user_prompt():
    prompt = apply_local_chat_profile(
        agent_name='qwen',
        base_prompt='USER PROMPT',
        deadline_seconds=18,
        auto_relay=False,
        informational_request=True,
        execution_confirmation=False,
    )

    assert prompt.index('=== RELAY DISABLED - HARD RULE ===') < prompt.index('=== FRIDAYS STUDIO HANDOFF TIMER ===')
    assert prompt.index('=== FRIDAYS STUDIO HANDOFF TIMER ===') < prompt.index('=== WATCHDOG READ-ONLY ROUTING GUARD ===')
    assert prompt.index('=== WATCHDOG READ-ONLY ROUTING GUARD ===') < prompt.index('USER PROMPT')


def test_local_chat_profile_appends_execution_confirmation_last():
    prompt = apply_local_chat_profile(
        agent_name='qwen',
        base_prompt='USER PROMPT',
        deadline_seconds=18,
        auto_relay=True,
        informational_request=False,
        execution_confirmation=True,
    )

    assert prompt.startswith('[Auto Relay: ENABLED]\n')
    assert prompt.rstrip().endswith('Do not ask for reconfirmation.')
    assert prompt.index('USER PROMPT') < prompt.index('=== EXECUTION CONFIRMATION ===')


def test_handoff_contract_and_relay_prefix_are_ascii_compatible():
    text = chat_handoff_contract('qwen', 18) + relay_policy_prefix(False)

    text.encode('ascii')
    assert '-> Eight' in text
