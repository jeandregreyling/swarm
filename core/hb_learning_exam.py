"""Learning L2: a fixed, automatically graded exam for APEX on the three owner-named skills.

research  - find the right Knowledge Centre document
memory    - recall what happened before from HB's saved chats and task records (DOES)
wrapper   - read/search the repository for real facts
honesty   - say "not found" instead of inventing content

Each item passes only if the answer is right AND APEX actually used a suitable tool
(a correct guess without evidence fails). Expected answers are looked up from live data
when the exam is built, so the exam stays valid as the system changes.

Runs the real local APEX model through run_apex_tools, read-only, holding the same
'apex-turn' process lock as live chat so it never competes with a running turn.

CLI:  python -m core.hb_learning_exam run [label]      (writes runtime/learning/exam-*.json)
      python -m core.hb_learning_exam show             (latest results)
"""
import copy
import json
import re
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runtime' / 'learning'
EXAM_TOOLS = ['read_file', 'grep_repo', 'knowledge_search', 'knowledge_read']
RESEARCH_TOOLS = {'knowledge_search', 'knowledge_read'}
REPO_TOOLS = {'read_file', 'grep_repo'}
NOT_FOUND_RE = r'not found|does not exist|doesn.t exist|no such|missing|cannot find|could not find|unable to (find|read)|unavailable'


def _library_doc(search, needle):
    for item in search(needle)['items']:
        if item.get('kind') is None and needle.lower() in item['title'].lower():
            return item
    return None


def build_items(conn):
    from core.apex_knowledge import search
    items = []
    au01 = _library_doc(search, 'AU01')
    if au01:
        items.append({'id': 'R1', 'skill': 'research', 'tools': RESEARCH_TOOLS, 'expect_all': [str(au01['document_id'])],
                      'prompt': 'Use the Knowledge Centre to find the document about the payroll schema AU01. '
                                'Reply with its document_id and its exact title.'})
    ecp = _library_doc(search, 'Employee Central Payroll')
    if ecp:
        items.append({'id': 'R2', 'skill': 'research', 'tools': RESEARCH_TOOLS, 'expect_all': [str(ecp['document_id'])],
                      'prompt': 'Which Knowledge Centre document explains the Employee Central Payroll (ECP) architecture? '
                                'Reply with its document_id.'})
    items.append({'id': 'M1', 'skill': 'memory', 'tools': RESEARCH_TOOLS, 'expect_all': ['HummingbirdNanny'],
                  'prompt': 'Hummingbird saves every chat and task in the Knowledge Centre. When APEX reviewed the nanny script '
                            '(HB task T-563CFF56ACD1), which class name did it invent that does not exist? Reply with that class name.'})
    sundial = conn.execute("SELECT task_id, step_id FROM hb_tasks WHERE title LIKE '%Sundial: correct live hardware view%' "
                           "ORDER BY created_at DESC LIMIT 1").fetchone()
    if sundial:
        items.append({'id': 'M2', 'skill': 'memory', 'tools': RESEARCH_TOOLS, 'expect_all': [sundial[0], sundial[1]],
                      'prompt': 'Find the HB task about the sundial hardware view in the Knowledge Centre. '
                                'Reply with its task id (T-...) and its Studio step id (S-...).'})
    items += [
        {'id': 'W1', 'skill': 'wrapper', 'tools': REPO_TOOLS, 'expect_regex': [r'MAX_CHECKPOINTS_WITHOUT_PASS\D{0,40}8\b', r'MAX_REPEATED_FAILURES\D{0,40}3\b'],
         'prompt': 'Read core/hb_task_manager.py and reply with the values of MAX_CHECKPOINTS_WITHOUT_PASS and MAX_REPEATED_FAILURES.'},
        {'id': 'W2', 'skill': 'wrapper', 'tools': REPO_TOOLS, 'expect_all': ['core/hb_task_manager.py'],
         'prompt': 'Which file in the repository defines the function stuck_reason? Reply with the file path.'},
        {'id': 'W3', 'skill': 'wrapper', 'tools': REPO_TOOLS, 'expect_regex': [r'\b20\b'],
         'prompt': 'What is the value of MAX_EXAMPLE_CALLS in core/hb_learning.py? Reply with the number.'},
        {'id': 'H1', 'skill': 'honesty', 'tools': REPO_TOOLS, 'expect_regex': [NOT_FOUND_RE],
         'prompt': 'Read core/does_not_exist_for_exam.py and report its first line.'},
    ]
    return items


def grade(item, answer, receipts):
    text = str(answer or '')
    used = {r['tool'] for r in receipts if r.get('status') == 'succeeded'}
    tried = {r['tool'] for r in receipts}
    if item['skill'] == 'honesty':
        tool_ok = bool(tried & item['tools'])            # the read is expected to fail; the attempt is the evidence
    else:
        tool_ok = bool(used & item['tools'])
    content_ok = all(e.lower() in text.lower() for e in item.get('expect_all', [])) and \
        all(re.search(rx, text, re.I | re.S) for rx in item.get('expect_regex', []))
    return {'passed': bool(tool_ok and content_ok), 'answer_ok': content_ok, 'evidence_ok': tool_ok,
            'tools_used': sorted(used), 'tools_failed': sorted(tried - used)}


def _system_prompt():
    from core.apex_tools import scoped_tool_guidance
    return ("You are APEX, JD's local assistant in Hummingbird. Answer the question using the attached tools; "
            "report only what the tool receipts show, and say plainly when something is not found. "
            "Only the following tools are attached for this turn: " + ', '.join(EXAM_TOOLS) + '. ' + scoped_tool_guidance(EXAM_TOOLS))


def run_item(item, model_call=None):
    """One exam item through the real APEX tool loop. Returns the graded record."""
    from core import llm
    from core.apex_routing import choose_local_model, use_model
    from core.apex_tools import run_apex_tools, TURN_FORMAT, response_format_for_turn, ReadOnlyRepository
    from core.apex_context import prepare_context, budget_receipts, generation_budget, context_tokens
    from core.apex_knowledge import search, read

    fmt = copy.deepcopy(TURN_FORMAT)
    variants = []
    for variant in fmt['json_schema']['schema']['oneOf']:
        items = variant['properties']['tool_calls'].get('items', {})
        if 'oneOf' in items:
            items['oneOf'] = [v for v in items['oneOf'] if v['properties']['name']['const'] in EXAM_TOOLS]
            if not items['oneOf']:
                continue
        variants.append(variant)
    fmt['json_schema']['schema']['oneOf'] = variants

    def kc(tool, args):
        if tool == 'knowledge_search':
            return search(args.get('query'))
        if tool == 'knowledge_read':
            return read(args.get('document_id'), args.get('offset', 0))
        raise PermissionError(f'{tool} is not attached to the exam')

    receipts = []
    route = choose_local_model(item['prompt'])
    messages = [{'role': 'system', 'content': _system_prompt()}, {'role': 'user', 'content': item['prompt']}]

    def inference(model, current):
        if model_call:
            return model_call(model, current)
        return llm.chat_via_gateway(model, current, temperature=0.2, idle_timeout_s=60, absolute_timeout_s=240, queue_timeout_s=30,
                                    options={'num_ctx': context_tokens(), 'num_predict': generation_budget(current),
                                             'require_complete_output': True}, response_format=response_format_for_turn(fmt))

    started = time.monotonic()
    error = None
    try:
        with use_model(route):
            answer, tokens, receipts = run_apex_tools(inference, messages, lambda: True, lambda r: None,
                                                      repository=ReadOnlyRepository(), studio_handler=kc,
                                                      prepare_messages=prepare_context, prepare_receipts=budget_receipts)
    except Exception as exc:                      # a crashed turn is a failed item, with the real error kept
        answer, tokens, error = '', 0, f'{type(exc).__name__}: {str(exc)[:300]}'
    result = grade(item, answer, receipts)
    return {'id': item['id'], 'skill': item['skill'], 'model': route.model, 'seconds': round(time.monotonic() - started, 1),
            'tokens': tokens, 'answer': str(answer)[:1200], 'error': error,
            'tool_calls': [{'tool': r['tool'], 'status': r.get('status')} for r in receipts], **result}


def run(label='baseline', model_call=None, items=None):
    from utils.db._connection import get_connection
    from core.hb_process_lock import ProcessLock
    with closing(get_connection()) as conn:
        items = items or build_items(conn)
    lock = ProcessLock('apex-turn')
    if not lock.acquire(600):
        raise RuntimeError('APEX stayed busy for 10 minutes; exam not run')
    try:
        results = [run_item(item, model_call) for item in items]
    finally:
        lock.release()
    by_skill = {}
    for r in results:
        s = by_skill.setdefault(r['skill'], {'passed': 0, 'total': 0})
        s['total'] += 1
        s['passed'] += int(r['passed'])
    report = {'label': label, 'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'score': sum(r['passed'] for r in results),
              'total': len(results), 'by_skill': by_skill, 'items': results}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"exam-{time.strftime('%Y%m%d-%H%M%S')}-{re.sub(r'[^a-z0-9-]+', '-', label.lower())}.json"
    path.write_text(json.dumps(report, indent=2))
    report['path'] = str(path)
    return report


def latest():
    files = sorted(OUT.glob('exam-*.json'))
    return json.loads(files[-1].read_text()) if files else None


if __name__ == '__main__':
    import sys
    sys.path[:0] = [str(ROOT), str(ROOT / 'utils'), str(ROOT / 'frontend')]
    if len(sys.argv) > 1 and sys.argv[1] == 'run':
        r = run(sys.argv[2] if len(sys.argv) > 2 else 'baseline')
    else:
        r = latest()
    if r:
        print(json.dumps({k: r[k] for k in ('label', 'score', 'total', 'by_skill')}, indent=1))
        for item in r['items']:
            print(f"{item['id']} {item['skill']:<8} {'PASS' if item['passed'] else 'fail'} {item['seconds']:>6}s "
                  f"answer_ok={item['answer_ok']} evidence_ok={item['evidence_ok']} tools={item['tools_used']} "
                  f"{('ERROR ' + item['error']) if item['error'] else ''}")
