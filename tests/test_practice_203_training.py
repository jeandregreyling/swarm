"""Practice 203: APEX's training script grades, records, and learns."""
import sqlite3

from core import hb_training as t


def test_grading():
    ex = {'expect_all': ['Excess Qualifying Earnings'], 'expect_any': ['CLING', 'MCB'], 'forbid': ['nothing for me to do']}
    assert t.grade(ex, 'XQE is Excess Qualifying Earnings above the MCB ceiling') == (True, 'ok')
    assert t.grade(ex, 'XQE is a wage type')[0] is False
    assert t.grade({'forbid': ['nothing for me to do']}, 'Nothing for me to do.') == (False, 'said: nothing for me to do')


def test_run_scores_and_learns_after_two_failures(tmp_path):
    path = tmp_path / 't.db'
    connect = lambda: sqlite3.connect(path)
    said = []
    good = lambda q, h: ('def merge(x): sort it' if 'intervals' in q else 'I will do my part. knowledge_search knowledge_read web_search. '
                         'Do you mean the links between HB parts? Excess Qualifying Earnings over the MCB. valuation bases.')
    assert t.run(connect, answer=good, say=said.append) == (6, 6) and 'passed 6 / 6' in said[0]
    bad = lambda q, h: 'Nothing for me to do.'
    t.run(connect, answer=bad, say=said.append)
    t.run(connect, answer=bad, say=said.append)
    learned = t.lessons_learned(sqlite3.connect(path))
    assert 'When JD writes to the team, answer for your part - never \'that is for someone else\'.' in learned
    assert 'lesson learned (failed twice)' in said[-1]
    assert 'APEX training:' in t.report(sqlite3.connect(path))
