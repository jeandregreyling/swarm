"""Owner 14 Nov 2026: a recorded deliverable (studio_note/studio_task) counts as progress in the task manager.
Without it, research-type steps (whose correct output is a note, not a code mutation) ratcheted recovery_count
into review phase every few ticks - the DAW/potato-farm review treadmill of 14 Nov."""
import json

import pytest

from core import hb_tasks, peer_bridge as peers, hb_task_manager as manager
from test_peer_turns import flow, owner

pytestmark = pytest.mark.usefixtures("owner_turned_continuation_on", "online_providers_authorised", "owner_defined_done")


def test_studio_note_counts_as_progress_and_stays_in_execute(flow):
    conn, p = flow
    rid = owner(conn)
    task = hb_tasks.for_request(conn, rid)
    manager.register(conn, task, request_id=rid)
    conn.execute("UPDATE hb_peer_work SET state='needs_review', stage='Worker restarted' WHERE request_id=?", (rid,))
    # Two stalled turns already: one more stagnant tick would flip to review without the note counting as progress.
    conn.execute('UPDATE hb_task_manager SET recovery_count=2 WHERE task_id=?', (task['task_id'],))
    hb_tasks.event(conn, task, 'apex', 'studio_note', {'content': 'the checklist with proof paths'})
    queued = manager.tick(conn)
    assert len(queued) == 1
    recipient = conn.execute('SELECT recipient FROM peer_messages WHERE id=?', (queued[0],)).fetchone()[0]
    assert recipient == 'apex'
    body = json.loads(conn.execute('SELECT body FROM peer_messages WHERE id=?', (queued[0],)).fetchone()[0])
    assert body['task_type'] == 'hb_managed_continuation'
    assert manager.tick(conn) == []   # a live attempt is never duplicated
