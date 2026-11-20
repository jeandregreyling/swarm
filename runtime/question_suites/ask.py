"""Reproduce one main-chat APEX research turn (prompt, card, history, model, knowledge + web tools, checks, grounding) without posting."""
import json, sys, time
sys.path.insert(0, '/home/jd/swarm')
from contextlib import closing
from utils.db._connection import get_connection
from core import llm, hb_tasks
from core.chat_continuity import APEX_AGENT, apex_system_prompt, apex_request_history
from core.apex_tools import run_apex_tools, response_format_for_turn, TURN_SECONDS
from core.apex_context import APEX_REASONING_EFFORT, context_tokens, generation_budget, time_budget, prepare_context, budget_receipts
from core.apex_routing import choose_local_model, use_model
from core.hb_dream_method import card as dream_card
from core.hb_agent_tools import ground_answer
from core.apex_knowledge import search, read
from core.hb_apex_swap import turn_seconds
from lib.search.internet import search_provider

Q = sys.argv[1]
TASK = 'T-5370E459C988'
route = choose_local_model(Q)
deadline = time.monotonic() + turn_seconds(TURN_SECONDS)


def model(name, msgs):
    last = str(msgs[-1].get('content'))
    if not last.startswith('BACKEND TOOL RECEIPTS'):
        print('>> MODEL SEES:', last[:400].replace(chr(10), ' '), flush=True)
    remaining = int(deadline - time.monotonic())
    opts = {'num_ctx': context_tokens(), 'num_predict': min(generation_budget(msgs), time_budget(remaining)),
            'require_complete_output': True, 'reasoning_effort': APEX_REASONING_EFFORT}
    out = llm.chat_via_gateway(name, msgs, temperature=0.2, idle_timeout_s=min(60, remaining), absolute_timeout_s=remaining,
                               queue_timeout_s=1, options=opts, response_format=response_format_for_turn())
    print('<< MODEL SAYS:', str(out[0])[:500].replace(chr(10), ' '), flush=True)
    return out


def studio(tool, args):
    if tool == 'knowledge_search':
        return search(args['query'])
    if tool == 'knowledge_read':
        return read(args['document_id'], args.get('offset', 0), args.get('focus'))
    raise PermissionError(f'{tool} not attached in this reproduction')


with closing(get_connection()) as c:
    task = hb_tasks.get(c, TASK)
    rows = hb_tasks.history(c, task)
    history = [r if isinstance(r, dict) and 'role' in r else {'role': 'user' if r['from_agent'] in ('user', 'ghost') else 'assistant',
                                                              'content': r['content']} for r in rows]
    card = dream_card(c, task)
    # The card quotes the task's latest real main-chat message; this reproduction asks Q instead (19-20 Nov suite: every question
    # was told to 'Answer THAT message' about /001 and /002).
    import re as _re
    card = _re.sub(r'(Latest message for you, from JD \(message \d+\): )".*?"(?=\s*Answer THAT)', lambda m: m.group(1) + json.dumps(Q), card, count=1, flags=_re.S)
    packet = hb_tasks.packet(c, task)
row = {**APEX_AGENT, 'model': route.model}
from core.chat_continuity import fresh_research
msgs = [{'role': 'system', 'content': apex_system_prompt(row, recovery=False, proposals=True, web=True)},
        {'role': 'user', 'content': card}]
if not fresh_research(Q):   # Practice 163: a new research question carries no pinned instructions or old chat
    msgs.append({'role': 'user', 'content': 'HB task reference, not new permissions: ' + json.dumps(packet), 'instructor_reference': True})
msgs += apex_request_history(history, Q)
with use_model(route):
    answer, tokens, receipts = run_apex_tools(model, msgs, lambda: True, lambda r: None, studio_handler=studio,
                                              web_handler=lambda a: search_provider(a['query'], a['provider']),
                                              prepare_messages=lambda cur: prepare_context(cur),
                                              prepare_receipts=lambda cur, b: budget_receipts(cur, b))
answer = ground_answer(answer, receipts)
for r in receipts:
    print('TOOL', r['tool'], json.dumps(r.get('arguments')), r['status'])
print('=====ANSWER=====')
print(answer)
