"""
Unit checks for chat thread reply routing helpers.

Run:
    python3 tests/test_chat_reply_routing.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'utils'))
sys.path.insert(0, str(ROOT / 'core' / 'pipeline'))
sys.path.insert(0, str(ROOT / 'frontend'))

from blueprints import chat as term


def test_infer_reply_target_from_salutation():
    target = term._infer_reply_target_from_text('Ten, your proposal flow is sound.')
    assert target == 'ten', f'expected ten, got {target!r}'


def test_reply_context_tracks_prior_agent_but_defaults_to_latest_sender():
    rows = [
        {'from_agent': 'user', 'to_agent': 'nine,ten', 'content': 'Lets test each agent.'},
        {'from_agent': 'nine', 'to_agent': 'user', 'content': '[nine] error: credits low'},
        {'from_agent': 'ten', 'to_agent': 'user', 'content': 'Proposal flow looks good.'},
        {'from_agent': 'user', 'to_agent': 'gemma,ten', 'content': 'Gemma can you see this conversation right?'},
    ]
    ctx = term._conversation_reply_context_from_rows(rows, 'gemma')
    assert ctx['latest_sender'] == 'user', ctx
    assert ctx['prior_agent'] == 'ten', ctx
    assert ctx['default_reply_target'] == 'user', ctx


def test_resolve_reply_target_prefers_explicit_agent_address():
    rows = [
        {'from_agent': 'user', 'to_agent': 'gemma', 'content': 'Join the thread.'},
        {'from_agent': 'ten', 'to_agent': 'user', 'content': 'I suggest proposal-first governance.'},
        {'from_agent': 'user', 'to_agent': 'gemma', 'content': 'Gemma, respond.'},
    ]
    ctx = term._conversation_reply_context_from_rows(rows, 'gemma')
    target = term._resolve_chat_reply_target('gemma', 'Ten, your proposal flow is a good baseline.', ctx)
    assert target == 'ten', f'expected ten, got {target!r}'


def test_history_rows_preserve_named_speakers_and_targets():
    rows = [
        {'from_agent': 'user', 'to_agent': 'gemma,ten', 'content': 'Loop Gemma in.'},
        {'from_agent': 'ten', 'to_agent': 'user', 'content': 'Workflow looks sound.'},
    ]
    history = term._chat_history_from_rows(rows)
    assert history[0]['role'] == 'user', history
    assert history[0]['content'].startswith('USER -> GEMMA,TEN:'), history[0]
    assert history[1]['role'] == 'assistant', history
    assert history[1]['content'].startswith('TEN'), history[1]
    assert '-> USER:' in history[1]['content'], history[1]


if __name__ == '__main__':
    failures = []
    tests = [
        ('test_infer_reply_target_from_salutation', test_infer_reply_target_from_salutation),
        ('test_reply_context_tracks_prior_agent_but_defaults_to_latest_sender', test_reply_context_tracks_prior_agent_but_defaults_to_latest_sender),
        ('test_resolve_reply_target_prefers_explicit_agent_address', test_resolve_reply_target_prefers_explicit_agent_address),
        ('test_history_rows_preserve_named_speakers_and_targets', test_history_rows_preserve_named_speakers_and_targets),
    ]

    print('Chat reply routing tests')
    print('=' * 32)

    for name, fn in tests:
        try:
            fn()
            print(f'PASS  {name}')
        except Exception as exc:
            failures.append((name, str(exc)))
            print(f'FAIL  {name} -> {exc}')

    print('-' * 32)
    if failures:
        print(f'{len(failures)} failed')
        for name, msg in failures:
            print(f'- {name}: {msg}')
        sys.exit(1)

    print('All chat reply routing tests passed')
    sys.exit(0)
