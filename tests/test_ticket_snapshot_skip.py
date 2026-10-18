import importlib.util
import pathlib
import re
import sys


def _load():
    src = pathlib.Path('frontend/blueprints/chat.py').read_text()
    start = src.index('def _should_attach_ticket_snapshot')
    end = src.index('def _build_ticket_snapshot_block')
    ns = {'re': re}
    exec(src[start:end], ns)
    return ns['_should_attach_ticket_snapshot']


def test_explicit_skill_line_skips_snapshot():
    f = _load()
    assert not f('Use the shell skill: SKILL shell python3 x "select status from t"', [])
    assert f('what is the ticket status?', [])


def test_data_questions_skip_snapshot():
    f = _load()
    assert not f('how many project steps are done, what status?', [])
    assert f('give me a status update on tickets', [])


def test_record_id_questions_skip_snapshot():
    f = _load()
    assert not f('which project is the proposal INTERNAL-FRED-2118 linked to?', [])
    assert not f('what is ticket TICKET-442 status', [])
    assert f('what proposals are pending', [])


def test_short_answer_with_new_data_is_not_an_echo():
    src = pathlib.Path('frontend/blueprints/chat.py').read_text()
    start = src.index('def _chat_response_echoes_prompt')
    end = src.index('def _chat_response_is_timeout_handoff')
    ns = {}
    exec(src[start:end], ns)
    f = ns['_chat_response_echoes_prompt']
    q = 'Fred, which project is the proposal INTERNAL-FRED-2118 linked to? Tell me the project id.'
    assert not f(q, 'The proposal INTERNAL-FRED-2118 is linked to project P-00221285D1.')
    assert f(q, 'which project is the proposal INTERNAL-FRED-2118 linked to tell me the project id')
