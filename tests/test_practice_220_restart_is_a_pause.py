"""Practice 220 (calm swarm 2/5): a restart is a pause - no new turns during it, a cut-off turn is not an APEX attempt."""
import sqlite3
import time

from core import hb_announce, hb_calm
from core import hb_task_manager as tm
from core import peer_bridge as peers


def test_interrupted_stages_are_recognised():
    assert hb_calm.interrupted('Worker restarted during a turn; request not automatically reexecuted')
    assert hb_calm.interrupted('Worker disconnected during a turn; recorded results require review')
    assert hb_calm.interrupted('Worker interrupted; review recorded results before retrying the request')
    assert not hb_calm.interrupted('Worker saved and verified its reply')
    assert not hb_calm.interrupted(None)


def _db():
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE hb_task_requests(task_id TEXT, request_id INTEGER)')
    c.execute('CREATE TABLE peer_messages(id INTEGER PRIMARY KEY, recipient TEXT, created_at REAL)')
    c.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, request_id INTEGER, payload TEXT, '
              'created_at REAL, agent TEXT)')
    c.execute('CREATE TABLE hb_peer_work(request_id INTEGER PRIMARY KEY, principal TEXT, state TEXT, stage TEXT, updated_at REAL)')
    return c


def test_a_turn_cut_off_by_a_restart_is_not_an_apex_attempt():
    """21 Nov 10:06-10:08: three real APEX turns, the fourth cut off 47 s in by a restart -> HB said 'APEX was stuck' and sent Fred."""
    c = _db()
    now = time.time()
    for rid in (2740, 2743, 2746, 2747):
        cut = rid == 2747
        c.execute('INSERT INTO hb_task_requests VALUES (?,?)', ('T-1', rid))
        c.execute('INSERT INTO peer_messages VALUES (?,?,?)', (rid, 'apex', now))
        c.execute('INSERT INTO hb_peer_work VALUES (?,?,?,?,?)', (rid, 'apex', 'needs_review' if cut else 'completed',
                  'Worker restarted during a turn; request not automatically reexecuted' if cut else 'Worker saved and verified its reply', now))
    assert tm.apex_tries(c, 'T-1', now - 60) == 3 < tm.APEX_TRIES


def test_apex_tries_still_counts_without_the_work_table():
    c = _db()
    c.execute('DROP TABLE hb_peer_work')
    c.execute('INSERT INTO hb_task_requests VALUES (?,?)', ('T-1', 1))
    c.execute('INSERT INTO peer_messages VALUES (?,?,?)', (1, 'apex', time.time()))
    assert tm.apex_tries(c, 'T-1', 0) == 1


def test_no_new_turn_starts_while_a_restart_is_announced(monkeypatch):
    monkeypatch.setattr(hb_calm, 'restart_pending', lambda: True)
    assert peers.inbox(None, {'id': 'apex', 'scopes': {'peer.read'}}, pending_only=True) == []


def test_restart_pending_follows_the_maintenance_notice(monkeypatch):
    from core import hb_maintenance
    monkeypatch.setattr(hb_maintenance, 'state', lambda: {'on': True, 'by': 'hb_restart'})
    assert hb_calm.restart_pending()
    monkeypatch.setattr(hb_maintenance, 'state', lambda: {'on': False})
    assert not hb_calm.restart_pending()


def test_a_cut_off_turn_is_announced_as_a_pause(monkeypatch):
    c = _db()
    c.execute("INSERT INTO hb_peer_work VALUES (2747,'apex','needs_review','Worker disconnected during a turn; recorded results require review',0)")
    c.execute("INSERT INTO hb_peer_work VALUES (2746,'apex','failed','Request failed; see the actual error in this thread',0)")
    monkeypatch.setattr(hb_announce, '_accepted', lambda conn, task_id: False)
    state, why = hb_announce._outcome(c, 'P-2747')
    assert state == 'paused' and 'restarted' in why
    assert hb_announce._outcome(c, 'P-2746')[0] == 'failed'
    hb_announce.ensure(c)
    c.execute("INSERT INTO hb_announce VALUES ('P-2747','APEX','Practice 79',?,1)", (time.time() - 50,))
    posted = []
    said = hb_announce.tick(c, items=[], post=lambda conn, line: posted.append(line))
    assert said and said[0].startswith('⏸ APEX paused: Practice 79') and posted == said
