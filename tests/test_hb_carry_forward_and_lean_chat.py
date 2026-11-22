"""Tests for Carry Forward continuity, positive-first lean chat prompt, and <=10-tool schema diet."""
import json
import sqlite3

from core import apex_tools, hb_carry_forward as cf


def test_carry_forward_records_and_renders_confidence_weights():
    conn = sqlite3.connect(':memory:')
    cf.record(conn, 2845, 'Find freshest roses in Melbourne', 'Checked local florists via web_search',
              [{'tool': 'web_search', 'status': 'succeeded'}])
    cf.record(conn, 2845, 'Hey apex how are you?', 'Doing great and ready to crack on!', [])
    rendered = cf.card(conn, 2845)
    assert 'CARRY FORWARD' in rendered
    assert '[High]' in rendered and 'web_search' in rendered
    assert '[Medium]' in rendered and 'Hey apex how are you?' in rendered


def test_lean_chat_prompt_is_positive_first_and_slim():
    prompt = cf.lean_chat_prompt('mistral-nemo-12b-abliterated', 'CARRY FORWARD: last topic', cf.select_chat_tools('Hello'))
    assert len(prompt) < 3000
    assert prompt.lower().count('never') <= 1
    assert prompt.lower().count('do not') == 0
    assert 'Pragmatism & Logic' in prompt and 'Creative Options' in prompt and 'Realism & Weights' in prompt and 'Carry Forward' in prompt


def test_response_format_tool_subsetting_shrinks_schema_and_requires_thought():
    full_len = len(json.dumps(apex_tools.TURN_FORMAT))
    tools = cf.select_chat_tools('Find freshest roses in Melbourne')
    assert len(tools) <= 10
    slim = apex_tools.response_format_for_turn(require_thought=True, allowed_tools=tools)
    slim_len = len(json.dumps(slim))
    assert slim_len < full_len * 0.45
    for branch in slim['json_schema']['schema']['oneOf']:
        assert 'thought' in branch['required']
