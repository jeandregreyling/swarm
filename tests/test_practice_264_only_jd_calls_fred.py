"""Practice 264: Fred works only when JD asked for him on that task."""
import sqlite3

from core import hb_task_manager as tm


def _db(text=None):
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_events(task_id TEXT, agent TEXT, kind TEXT, payload TEXT)')
    if text:
        c.execute("INSERT INTO hb_task_events VALUES ('T-1','user','instruction',?)", ('{"content": "%s"}' % text,))
    return c


def test_no_fred_unless_jd_named_him():
    t = {'task_id': 'T-1', 'step_id': 'S-1'}
    assert tm.local_help(_db(), t).startswith('unavailable: only JD can call Fred')
    assert tm.jd_asked_for_fred(_db('@fred take this one'), t)
    assert not tm.jd_asked_for_fred(_db('Build it Apex'), t)


def test_apex_task_turns_have_no_local_review():
    assert 'local_review' not in tm.EXECUTION_TOOLS
