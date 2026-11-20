"""Prepare Practice 176: the chat's thinking bubble shows what APEX is doing - each round, each search/read/web search, each HB check."""
import subprocess
import sys
sys.path.insert(0, '/home/jd/swarm')
from core import hb_change_sets as cs

STEP = sys.argv[1]
T = 'core/apex_tools.py'
C = 'frontend/blueprints/chat.py'
J = 'frontend/static/js/views/home-chat.js'

helpers = '''# Practice 176 (owner 20 Nov 2026: "I would like to see what the system is doing through the HB chat window, I'm not seeing what the
# LLMs are doing"): the thinking bubble had a step checklist, but APEX only ever reported "running". Each round, each tool call and each
# HB check that sends an answer back is now one plain line in it.
def step_line(call) -> str:
    """One plain line for a tool call."""
    name = str(call.get('name') or '') if isinstance(call, dict) else ''
    a = call.get('arguments') if isinstance(call, dict) and isinstance(call.get('arguments'), dict) else {}
    if name == 'knowledge_search':
        return 'searching our notes: "' + str(a.get('query', ''))[:70] + '"'
    if name == 'knowledge_read':
        return f"reading KC document {a.get('document_id')}" + (f" (looking for {str(a.get('focus'))[:40]})" if a.get('focus') else '')
    if name == 'web_search':
        return 'searching the web: "' + str(a.get('query', ''))[:70] + '"'
    what = str(a.get('path') or a.get('query') or a.get('action') or a.get('step_id') or '')[:60]
    return f'{name} {what}'.strip()


def check_line(text) -> str:
    """'HB read check sent the answer back: <first sentence>' for a BACKEND ... CHECK message, else ''."""
    m = re.match(r'BACKEND ([A-Z][A-Z ]*?(?:CHECK|LIMIT|ERROR))[:.]?\\s*(?:your answer was not delivered\\.\\s*)?(.*)', str(text or ''), re.S)
    if not m:
        return ''
    why = re.split(r'(?<=[.!?])\\s', m.group(2).strip(), maxsplit=1)[0][:150]
    return f'HB {m.group(1).lower()} sent the answer back' + (f': {why}' if why else '')


def say_step(text):
    """Report one step to the chat (no-op outside a chat turn)."""
    if not text:
        return
    try:
        from core.apex_routing import report_model_progress
        report_model_progress({'stage': 'step', 'text': str(text)[:200]})
    except Exception:
        pass


def _playing_name():
    try:
        from core.hb_apex_swap import playing, backend
        name, where = playing(), backend()
        return f"{name}{' on ' + where.upper().replace('ROCM', 'ROCm').replace('VULKAN', 'Vulkan') if where else ''}" if name else ''
    except Exception:
        return ''


def run_apex_tools(call_model, messages: list[dict], authorize, emit_receipt,
'''

edits = [
    {'path': T, 'old': "def run_apex_tools(call_model, messages: list[dict], authorize, emit_receipt,\n", 'new': helpers},
    {'path': T, 'old': '''                from core.apex_routing import active_model
                text, used = call_apex(call_model, active_model(), working)''', 'new': '''                from core.apex_routing import active_model
                if not round_index:                       # Practice 176
                    say_step('APEX' + (f' ({_playing_name()})' if _playing_name() else '') + ' starts: reading the question')
                say_step(f'APEX thinking - round {round_index + 1}' + (' (writing the answer)' if final_answer else ''))
                text, used = call_apex(call_model, active_model(), working)'''},
    {'path': T, 'old': '''        if isinstance(calls, list) and calls and all(isinstance(call, dict) and set(call) == {"name", "arguments"}
               and isinstance(call["arguments"], dict) and repeated_read(call, receipts)''', 'new': '''        for call in calls if isinstance(calls, list) else []:
            say_step(step_line(call))             # Practice 176
        if isinstance(calls, list) and calls and all(isinstance(call, dict) and set(call) == {"name", "arguments"}
               and isinstance(call["arguments"], dict) and repeated_read(call, receipts)'''},
    {'path': T, 'old': '''        delivered = _grounded(answer, can_retry, can_fix)
''', 'new': '''        delivered = _grounded(answer, can_retry, can_fix)
        if delivered is None:                     # Practice 176: say which HB check sent it back, and why
            say_step(check_line(next((m.get('content') for m in reversed(working) if m.get('role') == 'user'), '')))
'''},
    {'path': C, 'old': '''                stage = str(event.get('stage') or 'running').replace('_', ' ')
                _sse_chat(conv_id, APEX_AGENT['name'], 'running', model=selected_model,
                          stage=stage + ': ' + selected_model)''', 'new': '''                # Practice 176: APEX's own step lines go to the thinking bubble as they are
                stage = str(event.get('text') or '') or (str(event.get('stage') or 'running').replace('_', ' ') + ': ' + selected_model)
                _sse_chat(conv_id, APEX_AGENT['name'], 'running', model=selected_model, stage=stage)'''},
    {'path': J, 'old': '''      if (!_hcConvId) return;
      if (d.conversation_id && String(d.conversation_id) !== String(_hcConvId)) return;
      if (d.state) _hcSetLaneState(d.state, d.error || '');''', 'new': '''      if (d.status === 'running' && d.stage && !d.owner_command && _hcSending && _hcConvId
          && String(d.conversation_id || '') === String(_hcConvId)) {
        // Practice 176 (owner 20 Nov 2026: "I'm not seeing what the LLMs are doing"): APEX's steps - each round, search, read, web
        // search and HB check - go into the thinking bubble's checklist as they happen.
        const pending = document.querySelector('#home-chat-messages .hc-bubble[data-pending-job-id^="hc-tmp-"]');
        if (pending) {
          _hcUpsertThinkingBubble({ job_id: pending.dataset.pendingJobId, agent: d.agent || 'apex', status: 'running', stage: d.stage });
          return;
        }
      }
      if (!_hcConvId) return;
      if (d.conversation_id && String(d.conversation_id) !== String(_hcConvId)) return;
      if (d.state) _hcSetLaneState(d.state, d.error || '');'''},
]

test = '''"""Practice 176: the chat's thinking bubble shows what APEX is doing."""
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
    assert check_line('BACKEND READ CHECK: your answer was not delivered. It describes notes you did not read this turn (3757848). Read these now.') \\
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
             json.dumps({'tool_calls': [{'name': 'knowledge_read', 'arguments': {'document_id': L + 7004}}], 'answer': ''})] + \\
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
'''


def run(cmd):
    out = subprocess.run(cmd, cwd='/home/jd/swarm', capture_output=True, text=True, timeout=900)
    if out.returncode:
        print(out.stdout[-6000:])
    return out


out = cs.prepare(STEP, why=("Owner 20 Nov (\"I would like to see what the system is doing through the HB chat window, I'm not seeing what the "
                            "LLMs are doing\"): the thinking bubble has a step checklist, but APEX only ever reported 'running: <model>'. "
                            "core/apex_tools: say_step() reports each round (with the model and GPU backend at the start), each tool call "
                            "(step_line: searching our notes / reading KC document / searching the web) and each HB check that sends an "
                            "answer back, with its reason (check_line). chat.py model_progress passes the line through; home-chat.js puts "
                            "APEX 'running' events into the pending bubble's checklist."),
                 edits=edits, new_files={'tests/test_practice_176_see_apex_work.py': test},
                 test={'tests': ['tests/test_practice_176_see_apex_work.py', 'tests/test_practice_174_out_of_tool_calls.py',
                                 'tests/test_practice_157_online_research.py', 'tests/test_practice_155_keep_the_answer.py',
                                 'tests/test_practice_143_reasked_questions.py', 'tests/test_apex_grounding.py',
                                 'tests/test_practice_165_routing_import.py'], 'keyword': ''}, run=run)
print(out['verified'])
