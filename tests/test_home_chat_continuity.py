"""Regression coverage for restoring home chat and routing follow-up turns."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend'), str(ROOT / 'utils')]

from frontend.blueprints import chat
from agents.seven import seven_agent


@pytest.mark.parametrize('rows,expected', [
    ([
        {'from_agent': 'user', 'to_agent': 'gemma'},
        {'from_agent': 'gemma', 'to_agent': 'user'},
    ], ['gemma']),
    ([
        {'from_agent': 'gemma', 'to_agent': 'user'},
        {'from_agent': 'qwen', 'to_agent': 'gemma'},
    ], ['gemma']),
    ([{'from_agent': 'user', 'to_agent': 'gemma,qwen'}], ['gemma', 'qwen']),
    ([{'from_agent': 'retired-agent', 'to_agent': 'user'}], []),
    ([], []),
])
def test_followups_continue_with_the_thread_participant(monkeypatch, rows, expected):
    calls = []

    def fetch(conv_id, limit):
        calls.append(conv_id)
        return rows

    monkeypatch.setattr(chat, '_fetch_chat_thread_rows', fetch)
    assert chat._chat_followup_agents('42', {'gemma', 'qwen', 'seven'}) == expected
    assert calls == [42]


@pytest.mark.parametrize('conv_id', [None, '', 'bad', 0, -1])
def test_new_or_invalid_threads_do_not_inherit_an_agent(monkeypatch, conv_id):
    monkeypatch.setattr(chat, '_fetch_chat_thread_rows', lambda *a, **k: pytest.fail('must not fetch'))
    assert chat._chat_followup_agents(conv_id, {'gemma'}) == []


@pytest.mark.parametrize('message', [
    'List the first ten with a description about each',
    'Who is the winner of the Australian Open?',
    'List popular games from the 2000s',
])
def test_seven_does_not_replace_general_followups_with_its_roster(message):
    assert seven_agent._compose(message, {}, []) == (None, 0)


def test_seven_can_still_list_the_local_agents():
    answer, _ = seven_agent._compose('list the local agents', {'local_agents': ['Gemma']}, [])
    assert 'Local agents I coordinate: Gemma' in answer


def test_home_chat_refreshes_history_without_resetting_the_view():
    source = (Path(__file__).resolve().parents[1] / 'frontend/static/js/views/home-chat.js').read_text()
    init = source.split('window.initHomeChat = function () {', 1)[1].split('// ── Session 28', 1)[0]
    assert 'localStorage.getItem(HC_ACTIVE_THREAD_KEY)' in init
    assert 'removeItem(HC_ACTIVE_THREAD_KEY)' not in init
    assert "window.addEventListener('focus', () => _hcLoadThreadsListOnly())" in source
    assert "_hcViewVersion !== viewVersion" in source
    assert 'finishedJobs.has(job.job_id)' in source
    assert '_hcConversations.slice(0, 30)' not in source


def test_seven_failed_turn_does_not_dump_swarm_state(monkeypatch):
    monkeypatch.setattr(seven_agent, '_read_state', lambda: {'local_agents': ['Gemma'], 'open_tickets': 6})
    monkeypatch.setattr(seven_agent, '_load_memory', lambda *a, **k: [])
    monkeypatch.setattr(seven_agent, '_live_web_block', lambda *a, **k: '')
    monkeypatch.setattr(seven_agent, '_llm_chat', lambda *a, **k: ('', 0))
    monkeypatch.setattr(seven_agent, '_creative_fallback_response', lambda *a, **k: None)
    answer, _ = seven_agent.chat('what are some of their names')
    assert 'Local agents' not in answer and 'Open tickets' not in answer
    assert "couldn't produce an answer" in answer


def test_verdict_reusing_prompt_numbers_is_not_an_echo():
    from frontend.blueprints.chat import _chat_response_echoes_prompt

    prompt = ("@qwen Verify Gemma's one-sentence answer against: 0 GiB VRAM, 4.28 GiB system RAM. "
              "CORRECT or INCORRECT only, plus the numbers she gave.")
    assert not _chat_response_echoes_prompt(prompt, 'QWEN -> USER: CORRECT. Gemma stated: 0 GiB VRAM, 4.28 GiB system RAM.')
    assert _chat_response_echoes_prompt(prompt, 'Verify Gemma answer against 0 GiB VRAM 4.28 GiB system RAM')
