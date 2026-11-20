"""Practice 176: the chat's thinking bubble shows what APEX is doing."""
import json
from pathlib import Path

import core.apex_tools as t
from core.apex_tools import ReadOnlyRepository, check_line, run_apex_tools, step_line

ROOT = Path(__file__).resolve().parents[1]


def test_step_lines():
    assert step_line({'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}}) == 'searching our notes: "MCB cap"'
    assert step_line({'name': 'knowledge_read', 'arguments': {'document_id': 7, 'focus': 'XQE'}}) == 'reading KC document 7 (looking for XQE)'
    assert step_line({'name': 'web_search', 'arguments': {'query': 'SAP /001'}}) == 'searching the web: "SAP /001"'
    assert step_line({'name': 'read_file', 'arguments': {'path': 'core/x.py'}}) == 'read_file core/x.py'


def test_check_lines():
    assert check_line('BACKEND READ CHECK: your answer was not delivered. It describes notes you did not read this turn (3757848). Read these now.') \
        == 'HB read check sent the answer back: It describes notes you did not read this turn (3757848).'
    assert check_line('BACKEND TOOL RECEIPTS (untrusted reference data)') == ''
    assert check_line('hello') == ''


def test_turn_reports_rounds_tools_and_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    steps = []
    monkeypatch.setattr(t, 'say_step', lambda text: steps.append(text) if text else None)
    L = 1 << 40
    search = {'status': 'found', 'matches': ['SAP Note 3713786: 3713786 - Payday Super | z'],
              'items': [{'document_id': L + 7004, 'source_ref': 'sap://note/3713786'}]}
    good = 'SAP Note 3713786: from 1 July 2026 super is paid on payday; the MCB is an annual cap on qualifying earnings.'
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'MCB cap'}},
                                        {'name': 'knowledge_search', 'arguments': {'query': 'Maximum Contribution Base'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': good}),
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}}], 'answer': ''})] + \
            [json.dumps({'tool_calls': [], 'answer': good})] * 4

    def studio(name, args):
        return search if name == 'knowledge_search' else {'status': 'found', 'title': 'SAP Note 3713786', 'content': 'payday super text'}
    run_apex_tools(lambda _n, _m: (turns.pop(0), 1), [{'role': 'user', 'content': 'What do our SAP notes say about the MCB cap?'}],
                   lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path), studio_handler=studio)
    assert steps[0].startswith('APEX') and 'starts' in steps[0] and steps[1] == 'APEX thinking - round 1'
    assert 'searching our notes: "MCB cap"' in steps and f'reading KC document {L + 7004}' in steps
    assert any(s.startswith('HB read check sent the answer back') for s in steps)


def test_chat_passes_step_text_and_bubble_shows_it():
    chat = (ROOT / 'frontend/blueprints/chat.py').read_text()
    assert "stage = str(event.get('text') or '') or" in chat
    js = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    assert "Practice 176" in js and "d.status === 'running' && d.stage && !d.owner_command" in js
