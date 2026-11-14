import sqlite3
from datetime import datetime, timezone
from core.hb_dream import idle_seconds, observe_owner_message


def test_only_saved_owner_chat_refreshes_activity():
    conn=sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,from_agent TEXT,message_type TEXT,created_at TEXT)')
    conn.executemany('INSERT INTO messages VALUES(?,?,?,?)',[
        (1,'user','chat','2026-11-10 08:09:32'),
        (2,'apex','chat','2026-11-10 09:09:32'),
        (3,'user','relay','2026-11-10 09:09:32'),
        (4,'user','chat','invalid'),
        (5,'user','chat','2026-11-09 08:09:32'),
        (6,'user','chat','2026-11-10T08:09:32Z')])
    base=datetime(2026,11,10,8,9,32,tzinfo=timezone.utc).timestamp()
    assert observe_owner_message(conn,999) is False
    assert idle_seconds(conn,base) is None
    assert observe_owner_message(conn,1) is True
    assert idle_seconds(conn,base+3600)==3600
    for mid in [1,2,3,4,5,6]:
        assert observe_owner_message(conn,mid) is False, mid
        assert idle_seconds(conn,base+3600)==3600, mid
    conn.close()

def test_native_event_rejections_preserve_activity():
    import json
    from core import hb_tasks
    from core.hb_dream import observe_native_event

    conn = sqlite3.connect(':memory:')
    try:
        hb_tasks.ensure_schema(conn)
        def add(event_id, raw, agent='owner-host', kind='owner_input_observed'):
            conn.execute(
                'INSERT INTO hb_task_events(event_id,task_id,agent,kind,payload) VALUES(?,?,?,?,?)',
                (event_id, 'T-TEST', agent, kind, json.dumps(raw)))
        base = datetime(2026, 11, 10, 8, 9, 32, tzinfo=timezone.utc).timestamp()
        add(1, {'timestamp': '2026-11-10T08:09:32Z'})
        assert observe_native_event(conn, 1) is True
        assert idle_seconds(conn, base + 3600) == 3600
        assert conn.execute('SELECT timestamp, source_key FROM hb_dream_activity').fetchone() == (base, 'native:1')
        add(2, {'timestamp': '2026-11-10T08:10:32Z'})            # newer owner input moves activity forward
        assert observe_native_event(conn, 2) is True
        assert idle_seconds(conn, base + 3600) == 3540
        # rejections: unknown id, wrong agent, wrong kind, older stamp, bad stamp, non-dict payload
        add(3, {'timestamp': '2026-11-10T09:00:00Z'}, agent='apex')
        add(4, {'timestamp': '2026-11-10T09:00:00Z'}, kind='progress')
        add(5, {'timestamp': '2026-11-09T08:09:32Z'})
        add(6, {'timestamp': 'not a time'})
        add(7, [1, 2])
        for eid in (99, 3, 4, 5, 6, 7):
            assert observe_native_event(conn, eid) is False, eid
            assert idle_seconds(conn, base + 3600) == 3540, eid
    finally:
        conn.close()
