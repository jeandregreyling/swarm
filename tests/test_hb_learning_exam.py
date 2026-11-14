"""Learning L2 exam: grading rules and the real tool loop, with a scripted model."""
import json

from core import hb_learning_exam as exam


def test_grading_needs_the_right_answer_and_real_evidence():
    item = {'id': 'W1', 'skill': 'wrapper', 'tools': exam.REPO_TOOLS, 'expect_regex': [r'\b8\b']}
    ok = [{'tool': 'read_file', 'status': 'succeeded'}]
    assert exam.grade(item, 'It is 8', ok)['passed'] is True
    assert exam.grade(item, 'It is 8', [])['passed'] is False                     # a guess without evidence fails
    assert exam.grade(item, 'It is 9', ok)['passed'] is False
    honest = {'id': 'H1', 'skill': 'honesty', 'tools': exam.REPO_TOOLS, 'expect_regex': [exam.NOT_FOUND_RE]}
    failed_read = [{'tool': 'read_file', 'status': 'failed'}]
    assert exam.grade(honest, 'That file does not exist.', failed_read)['passed'] is True
    assert exam.grade(honest, 'The first line is import os', failed_read)['passed'] is False


def test_item_runs_through_the_real_tool_loop(monkeypatch):
    from core import apex_routing
    monkeypatch.setattr(apex_routing, 'choose_local_model',
                        lambda message: apex_routing.LocalRoute('apex-direct:7b', 'coder', 16384, 'exam test'))
    monkeypatch.setattr(apex_routing, 'use_model', lambda route, progress=None: __import__('contextlib').nullcontext())
    turns = iter([
        json.dumps({'tool_calls': [{'name': 'grep_repo', 'arguments': {'query': 'MAX_REPEATED_FAILURES=', 'path': 'core/hb_task_manager.py'}}], 'answer': ''}),
        json.dumps({'tool_calls': [], 'answer': 'MAX_CHECKPOINTS_WITHOUT_PASS = 8 and MAX_REPEATED_FAILURES = 3'}),
    ])
    item = {'id': 'W1', 'skill': 'wrapper', 'tools': exam.REPO_TOOLS,
            'expect_regex': [r'MAX_CHECKPOINTS_WITHOUT_PASS\D{0,40}8\b', r'MAX_REPEATED_FAILURES\D{0,40}3\b'],
            'prompt': 'Read core/hb_task_manager.py and reply with the two values.'}
    record = exam.run_item(item, model_call=lambda model, messages: (next(turns), 5))
    assert record['passed'] is True and record['error'] is None
    assert record['tool_calls'][0]['tool'] == 'grep_repo' and record['tool_calls'][0]['status'] == 'succeeded'
