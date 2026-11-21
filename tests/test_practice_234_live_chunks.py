"""Practice 234 (chunk-first interface, stage 1): the live snapshot carries each task's chunks, read-only."""
import sqlite3

from core import hb_chunks as ch, hb_live


def _db():
    c = sqlite3.connect(':memory:')
    ch.table(c)
    for n, text, state in ((1, 'run the test and read which file fails', 'done'), (2, 'replace the colours', 'doing'), (3, 'run the test', 'todo')):
        c.execute('INSERT INTO hb_chunks VALUES (?,?,?,?,?,?)', ('T-1', n, text, state, None, 0))
    c.commit()
    return c


def test_view_says_where_a_task_is():
    v = ch.view(_db(), 'T-1')
    assert v['total'] == 3 and v['done'] == 1 and v['doing'] == {'n': 2, 'text': 'replace the colours'} and v['next']['n'] == 3
    assert [x['state'] for x in v['list']] == ['done', 'doing', 'todo']
    assert ch.view(_db(), 'T-NONE') is None


def test_rows_and_workers_carry_their_chunks_without_writing():
    c = _db()
    items = [{'lane': 'gpu', 'task_id': 'T-1', 'title': 'Theme colours'}, {'step_id': 'S-1', 'task_id': 'T-1'}, {'step_id': 'S-2', 'task_id': None}]
    hb_live._with_chunks(c, items)
    assert items[0]['chunks']['doing']['n'] == 2 and items[1]['chunks']['done'] == 1 and 'chunks' not in items[2]
    assert not c.in_transaction                                                # the Live pane's poll never takes a write lock


def test_the_snapshot_attaches_them():
    import inspect
    src = inspect.getsource(hb_live.snapshot)
    assert "_with_chunks(conn, found + master.get('items', []))" in src
