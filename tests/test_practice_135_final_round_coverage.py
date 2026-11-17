"""Practice 135 (17 Nov 2026): APEX's STP2 answer left out 3643537 and HB's coverage check never ran - three searches filled the window,
HB asked for a tool-free final answer, and every retry check was off. The window was small because the GPU guard raised its margin on
APEX's normal 1.43 GB of host buffers. Now the guard only acts above 2 GB and undoes that false alarm, and the coverage check also
runs in the final round."""
import json
import sqlite3

import core.apex_tools as t
from core import hb_gpu_guard as g
from core.apex_tools import ReadOnlyRepository, run_apex_tools
from test_practice_133_gpu_spill import DROPIN

Q = 'What do our SAP notes say about STP Phase 2 issues in Australian payroll? Cite the note numbers and say what you could not find.'
RESULT = {'status': 'found', 'matches': ['SAP Note 3660828: 3660828 - STP2: Performance improvements for CE',
                                         'SAP Note 3643537: 3643537 - STP2: GMOA, GTPR, GTPA cumulation wage types']}


def test_practice_135_coverage_check_runs_in_the_final_round(tmp_path, monkeypatch):
    monkeypatch.setattr(t, 'kc_notes_claimed_missing', lambda answer: [])
    calls, seen = [], []
    turns = [json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'STP2'}}], 'answer': ''}),
             json.dumps({'tool_calls': [{'name': 'knowledge_search', 'arguments': {'query': 'Single Touch Payroll Phase 2'}}], 'answer': ''}),
             json.dumps({'tool_calls': [], 'answer': 'Note 3660828 covers STP2. Nothing else was found.'}),
             json.dumps({'tool_calls': [], 'answer': 'Notes 3660828 and 3643537 cover STP2.'})]

    def prep(working, batch):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('APEX context budget exceeded')
        return batch

    def model(_name, msgs):
        seen.append(str(msgs[-1]['content']))
        return turns.pop(0), 1
    answer, _, _ = run_apex_tools(model, [{'role': 'user', 'content': Q}], lambda: True, lambda _r: None, ReadOnlyRepository(tmp_path),
                                  studio_handler=lambda name, args: RESULT, prepare_receipts=prep)
    back = [s for s in seen if s.startswith('BACKEND COVERAGE CHECK')]
    assert back and 'Answer now without tools' in back[0] and '3643537' in answer


def test_practice_135_normal_host_buffers_are_not_a_spill_and_the_false_alarm_is_undone(tmp_path):
    path = tmp_path / 'gpu-offload.conf'
    path.write_text(g.with_margin(DROPIN, 2048))
    (tmp_path / 'gpu-offload.conf.before-hb').write_text(g.with_margin(DROPIN, 1536))
    conn, said, done = sqlite3.connect(':memory:'), [], []
    conn.execute('CREATE TABLE hb_gpu_spill(at REAL, spilled_gb REAL, margin_from INTEGER, margin_to INTEGER, ok INTEGER)')
    conn.execute('INSERT INTO hb_gpu_spill VALUES (100, 2.49, NULL, 1536, 1), (200, 1.43, 1536, 2048, 1)')
    kw = dict(path=path, idle=lambda: True, reload=lambda: done.append('reload') or True, restart=lambda: done.append('restart') or True,
              answers=lambda: True, say=said.append)
    healthy = [{'port': 8080, 'placement': 'gpu', 'spilled_gb': 1.45}]
    g.spill_tick(conn, now=200 + g.SPILL_GAP_S + 1, procs=healthy, **kw)
    assert g.margin(path.read_text()) == 1536 and done == ['reload', 'restart'] and 'undid its last GPU change' in said[0]
    g.spill_tick(conn, now=200 + 2 * g.SPILL_GAP_S + 2, procs=healthy, **kw)
    assert g.margin(path.read_text()) == 1536 and len(said) == 1          # 1.45 GB is normal: nothing more, no loop
