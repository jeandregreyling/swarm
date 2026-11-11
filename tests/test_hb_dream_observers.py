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
                (event_id, 'T-14AEA38BF295', agent, kind, json.dumps(raw)))
        add(1, {'timestamp': '2026-11-10T08:09:32Z', 'task_id': 'T-14AEA38BF295', 'message': 'test message'})
        assert observe_native_event(conn, 1) is True
        assert idle_seconds(conn, datetime.now(timezone.utc)) == 3600
        assert conn.execute('SELECT timestamp, source_key FROM hb_dream_activity WHERE id=1').fetchone() == (datetime.now(timezone.utc), 'native:1')
        add(2, {'timestamp': datetime.now(timezone.utc) + timedelta(seconds=60)})
        assert observe_native_event(conn, 2) is True
        assert idle_seconds(conn, datetime.now(timezone.utc)) == 3540
        assert conn.execute('SELECT timestamp, source_key FROM hb_dream_activity WHERE id=1').fetchone() == (datetime.now(timezone.utc) + timedelta(seconds=60), 'native:2')
    finally:
        conn.close()