from agents import skills_loop as sl


def _user(text):
    return [{'role': 'user', 'content': text}]


def test_prose_no_write_does_not_make_turn_read_only():
    relayed = 'Mistral: checkpointing. No write occurs without an active Vortex ID.'
    assert sl._is_explicitly_read_only_task(_user(relayed)) is False


def test_explicit_do_not_edit_is_still_read_only():
    assert sl._is_explicitly_read_only_task(_user('Please do not edit any files.')) is True


def test_only_latest_user_turn_counts():
    msgs = _user('Do not edit anything.') + [{'role': 'assistant', 'content': 'ok'}]
    msgs += _user('Now create the proposal.')
    assert sl._is_explicitly_read_only_task(msgs) is False


def test_bracket_skill_inside_is_executed_as_skill():
    cmds = sl._extract_skill_cmds('[skill:alm_create_proposal "Database Connection Error"]')
    assert cmds == [('alm_create_proposal', '"Database Connection Error"')]


def test_bracket_skill_with_trailing_args_is_executed_as_skill():
    cmds = sl._extract_skill_cmds('[skill:fs_readonly] lines fridays/task_runner.py 1 40')
    assert cmds == [('fs_readonly', 'lines fridays/task_runner.py 1 40')]


def test_echoed_skill_result_is_not_a_command():
    for text in ('[skill:fs_readonly] OK', '[skill:fs_patch_lines] FAILED\nNot authorized'):
        assert sl._extract_skill_cmds(text) == []


def test_plain_skill_line_still_parses():
    cmds = sl._extract_skill_cmds('SKILL fs_readonly lines fridays/task_runner.py 1 40')
    assert cmds == [('fs_readonly', 'lines fridays/task_runner.py 1 40')]


def test_fenced_skill_has_no_trailing_fence_in_args():
    text = '1. Read it.\n```bash\nSKILL fs_readonly lines fridays/task_runner.py 1 60\n```\nDone.'
    assert sl._extract_skill_cmds(text) == [
        ('fs_readonly', 'lines fridays/task_runner.py 1 60'),
    ]


def test_handoff_block_teaches_chain_of_command_and_real_skills():
    from frontend.services.chat_history import _build_chat_handoff_block

    block = _build_chat_handoff_block('gemma', {'latest_sender': 'user'})
    assert 'placeholder' in block
    assert 'CHAIN OF COMMAND' in block
    assert 'SKILL fs_patch_lines <path> <start> <end>' in block
    assert 'approval is open' in block


def test_nudge_example_is_neutral_not_a_magic_number():
    assert 'chat.py 900' not in sl._SKILL_NUDGE
    assert 'SKILL fs_readonly lines docs/sample.md 1 20' in sl._SKILL_NUDGE


def test_literal_agentname_placeholder_is_stripped_in_any_mode():
    from frontend.services.chat_relay import _strip_placeholder_relay

    text = 'AgentName: Please investigate.\nReal finding here.\nAgentName: another'
    assert _strip_placeholder_relay(text) == 'Real finding here.'
    assert _strip_placeholder_relay('Qwen: can you check?') == 'Qwen: can you check?'


def test_fs_readonly_does_not_absorb_echoed_prompt_text():
    text = (
        'SKILL fs_readonly lines fridays/task_runner.py 1 60\n'
        '=== RELAY DISABLED - HARD RULE ===\n'
        'Auto Relay is OFF.'
    )
    assert sl._extract_skill_cmds(text) == [
        ('fs_readonly', 'lines fridays/task_runner.py 1 60'),
    ]


def _run(replies, monkeypatch, ok=True):
    calls = iter(replies)
    monkeypatch.setattr(sl, '_execute_skill_cmds',
                        lambda cmds, *a, **k: '[skill:%s] %s\nProposal ID: 7' % (cmds[0][0], 'OK' if ok else 'FAILED'))
    return sl.run_skill_loop(
        agent_name='qwen', call_fn=lambda m: (next(calls), 1),
        messages=_user('make a proposal'), emit_fn=lambda *_: None,
        max_passes=1, nudge_if_no_skills=False,
    )[0]


def test_trailing_skill_line_is_executed(monkeypatch):
    out = _run(['SKILL alm_create_proposal "T" "D"', 'SKILL alm_create_proposal "T" "D"'], monkeypatch)
    assert 'Proposal ID: 7' in out and '[verification]' not in out


def test_unverified_proposal_claim_is_flagged(monkeypatch):
    out = _run(['I created the proposal, ID 12345.'], monkeypatch)
    assert out.startswith('[verification]')


def test_relay_disabled_block_does_not_make_turn_read_only():
    from utils.chat_prompt_profiles import relay_policy_prefix
    msg = relay_policy_prefix(False) + 'Please create an alm_create_proposal for the README.'
    assert sl._is_explicitly_read_only_task(_user(msg)) is False
    assert sl._is_explicitly_read_only_task(_user(relay_policy_prefix(False) + 'Do not edit anything.')) is True


def test_handoff_block_does_not_trip_read_only_check():
    from frontend.services.chat_history import _build_chat_handoff_block
    block = _build_chat_handoff_block('gemma', {})
    assert sl._READ_ONLY_TASK_RE.search(block) is None


def test_duplicate_proposal_in_same_thread_is_skipped():
    sl._RECENT_PROPOSALS.clear()
    assert sl._is_duplicate_proposal('llama', 99, '"Same title" "d1"') is False
    assert sl._is_duplicate_proposal('llama', 99, '"Same title" "d2"') is True
    assert sl._is_duplicate_proposal('llama', 100, '"Same title" "d1"') is False


def test_look_and_explain_request_is_look_only():
    assert sl._asks_only_to_look(_user('List docs with SKILL fs_readonly ls docs and tell me what you see.')) is True


def test_injected_context_does_not_make_a_look_request_an_action():
    text = '=== CARRY-OVER ===\nplease create and update things\n=== END CARRY-OVER ===\n=== New user message ===\nWhat do you see in docs?'
    assert sl._asks_only_to_look(_user(text)) is True


def test_change_or_proposal_request_is_not_look_only():
    assert sl._asks_only_to_look(_user('Read README.md then raise a proposal.')) is False
    assert sl._asks_only_to_look(_user('Fix the typo on line 3.')) is False


def test_describing_proposals_is_not_a_false_claim():
    calls = iter(['To suggest a change, create a proposal and report the ID. Ghost reviews proposals.'])
    out, _ = sl.run_skill_loop('fred', lambda m: (next(calls), 1), _user('What is a proposal?'), lambda t: None)
    assert '[verification]' not in out


def test_claiming_a_proposal_without_a_skill_is_flagged():
    calls = iter(['I created a proposal, it is INTERNAL-FRED-9999.'])
    out, _ = sl.run_skill_loop('fred', lambda m: (next(calls), 1), _user('Hello'), lambda t: None)
    assert out.startswith('[verification]')


def test_all_asks_reminder_quotes_operator_message_without_injected_blocks():
    from agents.skills_loop import _all_asks_reminder

    msgs = [{'role': 'user', 'content': '=== RELAY ===\nrules\n=== END RELAY ===\n=== New user message ===\n1) say your role 2) list docs'}]
    out = _all_asks_reminder(msgs)
    assert '1) say your role 2) list docs' in out
    assert 'rules' not in out
    assert 'EVERY part' in out
    assert _all_asks_reminder([]) == ''


def test_verification_ignores_proposal_ids_read_from_skill_results():
    import inspect
    from agents import skills_loop

    src = inspect.getsource(skills_loop.run_skill_loop)
    assert 'pid not in joined' in src


def test_read_only_phrase_in_injected_memory_does_not_strip_skills():
    from agents.skills_loop import _is_explicitly_read_only_task

    ctx = 'Remembered rule: never patch a database as text.\n=== New user message ===\nRun SKILL shell uptime'
    assert not _is_explicitly_read_only_task([{'role': 'user', 'content': ctx}])
    assert _is_explicitly_read_only_task([{'role': 'user', 'content': 'Do not edit anything, just look.'}])


def test_level0_shell_allowed_on_read_only_turn():
    from agents.skills_loop import _is_level0_shell

    ro = {'fs_readonly'}
    assert _is_level0_shell('shell', 'python3 scripts/db_query.py "select 1"', ro)
    assert not _is_level0_shell('shell', 'sudo systemctl restart ollama', ro)
    assert not _is_level0_shell('shell', 'uptime', set())
    assert not _is_level0_shell('fs_write', 'x', ro)


def test_bare_db_query_line_becomes_shell_skill():
    from agents.skills_loop import _extract_skill_cmds

    text = '```shell\npython3 scripts/db_query.py "select 1"\n```'
    assert _extract_skill_cmds(text) == [('shell', 'python3 scripts/db_query.py "select 1"')]


def test_proposal_id_from_operator_message_is_not_flagged():
    from agents.skills_loop import run_skill_loop

    msgs = [{'role': 'user', 'content': 'Which project is INTERNAL-FRED-2118 linked to?'}]
    answer, _ = run_skill_loop(
        agent_name='fred',
        call_fn=lambda m: ('INTERNAL-FRED-2118 is linked to P-00221285D1.', 5),
        messages=msgs,
        emit_fn=lambda *_: None,
        max_passes=1,
    )
    assert '[verification]' not in answer


def test_read_only_turn_allows_memory_and_knowledge_lookups():
    from agents.skills_loop import _is_level0_shell
    assert _is_level0_shell('memory_search', 'x', {'fs_readonly'})
    assert _is_level0_shell('swarm_knowledge_search', 'x', {'fs_readonly'})
    assert not _is_level0_shell('fs_write', 'x', {'fs_readonly'})
