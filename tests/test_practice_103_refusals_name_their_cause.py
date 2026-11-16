"""Practice 103 (owner 16 Nov 2026): at 17:35 HB refused every change_set and run_tests call of an APEX turn with one catch-all message,
"Read-only repository inspection is not authorized", and its turn record kept only "denied". It looked like APEX inventing a permission
problem; nobody could tell which check refused. Each refusal now names its cause, and the turn record keeps the reason."""
import json

from core import hb_workflow
from core.apex_tools import ReadOnlyRepository, run_apex_tools


def _turn(tmp_path, authorize):
    calls = [json.dumps({'tool_calls': [{'name': 'read_file', 'arguments': {'path': 'x.py'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': 'Stopped: the read was refused.'})]
    model = lambda _name, _msgs: (calls.pop(0), 1)
    (tmp_path / 'x.py').write_text('a = 1\n')
    _answer, _tokens, receipts = run_apex_tools(model, [{'role': 'user', 'content': 'read x.py'}], authorize, lambda _r: None,
                                                ReadOnlyRepository(tmp_path))
    return receipts


def test_practice_103_a_refusal_names_its_cause(tmp_path):
    receipts = _turn(tmp_path, lambda: False)
    assert receipts[0]['status'] == 'denied'
    assert receipts[0]['output'].startswith("read_file refused: HB's turn authorization said no")
    assert 'Read-only repository inspection is not authorized' not in receipts[0]['output']


def test_practice_103_the_turn_record_keeps_the_reason(monkeypatch):
    saved = []

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def close(self): pass
        def execute(self, sql, args=()):
            if sql.startswith('INSERT INTO hb_model_runs'):
                saved.append(args)
    monkeypatch.setattr(hb_workflow, 'get_connection', lambda: Conn())
    monkeypatch.setattr(hb_workflow, '_schema', lambda conn: None)
    monkeypatch.setattr(hb_workflow, 'memory_snapshot', lambda: {})
    hb_workflow.record_run(2845, 'gpt-oss:20b', 'general', 'answered', 0, {}, 5,
                           [{'id': 'r1', 'tool': 'change_set', 'status': 'denied', 'output': 'change_set refused: task cancelled'},
                            {'id': 'r2', 'tool': 'run_tests', 'status': 'succeeded', 'output': 'PASS'}])
    summary = json.loads(saved[0][10])
    assert summary[0] == {'tool': 'change_set', 'status': 'denied', 'receipt_id': 'r1', 'why': 'change_set refused: task cancelled'}
    assert summary[1] == {'tool': 'run_tests', 'status': 'succeeded', 'receipt_id': 'r2'}
