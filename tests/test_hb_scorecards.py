"""Practice 61 (owner 14 Nov): scorecards from HB's records, a worked-example lookup, and the ladder rule (two failed checks = one rung up)."""
import json
import sqlite3
import core.hb_scorecards as s
import core.hb_commands as cmds
import core.hb_clipboard as clip


def db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_model_runs(model TEXT, category TEXT, status TEXT, elapsed_seconds REAL)')
    c.execute('CREATE TABLE hb_merits(model TEXT, category TEXT, kind TEXT)')
    c.execute('CREATE TABLE project_steps(step_id TEXT, title TEXT, status TEXT, updated_at REAL)')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    c.executemany('INSERT INTO hb_model_runs VALUES (?,?,?,?)', [('qwen14', 'coder', 'answered', 40), ('qwen14', 'coder', 'answered', 60),
                                                                ('qwen14', 'coder', 'failed', 5), ('unknown', 'local', 'failed', 1)])
    c.executemany('INSERT INTO hb_merits VALUES (?,?,?)', [('qwen14', 'coder', 'success'), ('qwen14', 'coder', 'success'), ('fred', None, 'correction'), ('qwen14', 'coder', 'lesson')])
    return c


def test_practice_61_scorecards_from_records():
    cards = s.scorecards(db())
    assert cards[('qwen14', 'coder')] == {'answered': 2, 'failed': 1, 'avg_s': 50.0, 'successes': 2, 'corrections': 0, 'pass_rate': 0.67}
    assert cards[('fred', 'general')]['corrections'] == 1 and ('unknown', 'local') not in cards
    out = s.text(db())
    assert out.splitlines()[1].startswith('- qwen14 / coder: 2 checked success(es), 0 correction(s), 2 turn(s) answered, 1 failed, 67% of turns answered, 50.0 s per turn')


def test_practice_61_worked_examples_are_approved_change_sets():
    c = db()
    c.executemany('INSERT INTO project_steps VALUES (?,?,?,?)', [('S-1', 'Practice 42: grep_repo skips a missing file', 'done', 2), ('S-2', 'Daily summary in main chat', 'done', 1),
                                                                 ('S-3', 'grep rewrite', 'todo', 3), ('S-4', 'No change set here grep', 'done', 4)])
    sets = {'S-1': {'why': 'a tracked file deleted from disk failed every search', 'edits': [{'path': 'core/apex_tools.py'}], 'new_files': {}, 'test': {'tests': ['tests/test_apex_grep_missing.py']}},
            'S-2': {'why': 'once a day', 'edits': [], 'new_files': {'core/hb_daily_summary.py': ''}, 'test': {'tests': []}},
            'S-3': {'why': 'grep', 'edits': [], 'new_files': {}}}
    found = s.examples(c, 'grep_repo fails when a file is missing', load=sets.get)
    assert [e['step_id'] for e in found] == ['S-1'] and found[0]['files'] == ['core/apex_tools.py']
    assert s.examples_text(c, 'grep_repo missing', load=sets.get).startswith('How this was done before (check passed):\n- Practice 42')
    assert s.examples_text(c, 'zzzz', load=sets.get) == 'No worked example matches that yet.'


def test_practice_61_two_failed_checks_move_the_doer_one_rung_up():
    c = db()
    assert s.next_rung('small', 1) == ('small', '')
    assert s.next_rung('small', 2) == ('apex', 'moved up from small after 2 failed checks in a row')
    assert s.next_rung('apex', 5) == ('apex', '') and s.next_rung('fred', 9) == ('fred', '')   # Practice 281: the ladder stops at APEX
    for status in ('pass', 'fail', 'fail'):
        c.execute("INSERT INTO hb_task_events(task_id, kind, payload) VALUES ('T-1','test_result',?)", (json.dumps({'alm_run_status': status}),))
    assert s.failed_checks(c, 'T-1') == 2 and s.failed_checks(c, 'T-none') == 0


def test_practice_61_wired_into_clipboard_and_commands():
    import inspect
    assert 'hb_scorecards.next_rung(' in inspect.getsource(clip.facts)
    assert {'scorecards', 'examples'} <= set(cmds.NAMES)
    assert cmds.parse('examples grep missing file') == ('examples', ['grep missing file']) and cmds.parse('scorecards') == ('scorecards', [])
