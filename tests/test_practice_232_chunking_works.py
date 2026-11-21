"""Practice 232: chunking works end to end - clean chunks, matched to the work in order, moved at the end of every turn, visible."""
import inspect
import json
import sqlite3
import time

from core import hb_chunks as ch, hb_tasks
from core import hb_task_manager as tm

THEME = ("Do: run python -m pytest tests/test_hb_brand_icons.py and read which file fails, then replace every hard-coded #rrggbb colour in the "
         "five HB interface files that test checks (frontend/static/js/hb-maintenance.js, views/hb-needs-you.js, views/hb-queue.js, "
         "views/hb-approval-popup.js, views/hb-activity.js) with the theme variable for its job (find them with grep -n -- '--[a-z-]*:' "
         "frontend/static/css/*.css: text, card, bg, border, accent, warning, danger), a fallback inside var(--x, #...) is allowed, then the CSS "
         "lines listed above one file per chunk, keeping each gradient's look with color-mix() of theme variables; run the test after each file.\n"
         "Done when: python -m pytest tests/test_hb_brand_icons.py passes.")
PREP = ('PREPARED (Claude Code): this step has a tested change set. Do: change_set show (read why), change_set apply, then run_tests with '
        '{"tests": ["tests/x.py"]}, then report in 2-4 lines.\nDone when: python -m pytest tests/x.py passes')
BUG = ('Bug: failing tests found by the full test run of 18 Nov 2026 (Claude Code; 4,331 passed, 65 failed).\nFile: tests/test_x.py '
       'Failing: test_a; test_b\nIf the failure needs hardware this machine does not have, report that and stop.')


def test_chunks_split_only_at_real_steps():
    parts = ch.plan(THEME)
    assert len(parts) == 4 and parts[0].startswith('run python -m pytest') and parts[1].startswith('replace every hard-coded')
    assert not any(p.startswith(('views/', 'card', 'bg')) or p in ('card', 'bg') for p in parts)
    assert parts[3] == 'run the test after each file'
    assert ch.plan(PREP) == ['change_set show (read why)', 'change_set apply', 'run_tests with {"tests": ["tests/x.py"]}', 'report in 2-4 lines']


def test_a_description_is_never_chunked():
    assert ch.plan(BUG) == []


def _db(desc, title='Theme colours'):
    c = sqlite3.connect(':memory:')
    hb_tasks.ensure_schema(c)
    c.execute('CREATE TABLE IF NOT EXISTS project_steps(step_id TEXT, title TEXT, description TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, conversation_id INT, from_agent TEXT, to_agent TEXT, content TEXT, '
              'message_type TEXT, tokens_used INT)')
    c.execute("INSERT INTO project_steps VALUES ('S-1', ?, ?)", (title, desc))
    return c


def _event(c, kind, payload=None):
    c.execute('INSERT INTO hb_task_events(task_id, agent, kind, payload, created_at) VALUES (?,?,?,?,?)',
              ('T-1', 'apex', kind, json.dumps(payload or {}), time.time()))


TASK = {'task_id': 'T-1', 'step_id': 'S-1', 'objective': '', 'title': 'Calm swarm 4/5', 'conversation_id': 2845}


def test_one_turn_can_finish_several_chunks_in_order_and_says_so():
    c = _db(PREP)
    assert 'chunk 1 of 4: change_set show' in ch.focus(c, TASK)
    for kind, payload in (('tool_result', {'tool': 'change_set'}), ('mutation', {}), ('test_result', {'alm_run_status': 'pass'}), ('reply', {})):
        _event(c, kind, payload)
    assert ch.advance(c, TASK) == 4
    assert c.execute("SELECT COUNT(*) FROM hb_task_events WHERE kind='chunk_done'").fetchone()[0] == 4
    line = c.execute("SELECT content FROM messages ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert line.startswith('▸ Calm swarm 4/5: chunks 1-4 of 4 done') and 'all chunks done' in line


def test_a_look_is_finished_by_a_failing_run_but_a_change_is_not():
    c = _db(THEME)
    assert 'chunk 1 of 4' in ch.focus(c, TASK)
    _event(c, 'test_result', {'alm_run_status': 'fail'})
    assert ch.advance(c, TASK) == 1
    _event(c, 'test_result', {'alm_run_status': 'fail'})
    assert ch.advance(c, TASK) is None                                    # chunk 2 changes files: a failing run does not finish it
    _event(c, 'mutation', {'path': 'frontend/static/js/views/hb-approval-popup.js'})
    assert ch.advance(c, TASK) == 2


def test_old_work_does_not_finish_new_chunks():
    c = _db(THEME)
    _event(c, 'test_result', {'alm_run_status': 'fail'})                  # recorded before the chunks existed
    assert 'chunk 1 of 4' in ch.focus(c, TASK) and ch.advance(c, TASK) is None


def test_chunks_follow_a_new_spec_until_one_is_done():
    c = _db(PREP)
    ch.focus(c, TASK)
    c.execute("UPDATE project_steps SET description=? WHERE step_id='S-1'", (THEME,))
    assert 'run python -m pytest' in ch.focus(c, TASK)                     # nothing done yet: rebuilt from the new spec
    _event(c, 'test_result', {'alm_run_status': 'fail'})
    ch.advance(c, TASK)
    c.execute("UPDATE project_steps SET description=? WHERE step_id='S-1'", (PREP,))
    assert 'chunk 2 of 4: replace' in ch.focus(c, TASK)                     # a chunk is done: kept


def test_chunks_move_at_the_end_of_every_turn_before_the_stuck_check():
    src = inspect.getsource(tm.tick)
    assert src.index('chunks_advance(conn,task)') < src.index('stuck=stuck_reason(conn,task')
