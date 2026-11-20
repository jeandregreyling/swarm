"""Many durable owner instructions and one oversized request cannot stop the inbox."""
import json
import hashlib
from core import hb_tasks,peer_bridge,apex_tools
from test_practice_139_task_packet_budget import conn,say  # noqa: F401
from test_peer_turns import flow,owner  # noqa: F401


def test_long_chat_pages_all_original_references_and_keeps_latest_exact(conn):
    task=hb_tasks.bind(conn,7,say(conn,'Keep owner scope exact'),studio=False)
    mids=[]
    for i in range(120):
        mid=say(conn,f'Owner instruction {i}: preserve constraint '+str(i)+' x'*50)
        mids.append(mid);hb_tasks.bind(conn,7,mid,task_id=task['task_id'])
    latest='What is happening on the existing task?'
    mids.append(say(conn,latest));hb_tasks.bind(conn,7,mids[-1],task_id=task['task_id'])
    task=hb_tasks.get(conn,task['task_id'])
    packet=hb_tasks.packet(conn,task)
    assert len(json.dumps(packet))<=10000
    assert packet['objective']=='Keep owner scope exact'
    assert packet['instructions'][-1]['content']==latest
    assert packet['older_instructions']['count']>0
    index=[];offset=0
    while offset is not None:
        page=hb_tasks.instruction_references(conn,task,offset)
        assert len(json.dumps(page))<6000
        for item in page['instructions']:
            eid=item['reference']['read']['arguments']['evidence_id']
            original=json.loads(conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(eid,)).fetchone()[0])['content']
            assert hashlib.sha256(original.encode()).hexdigest()==item['reference']['sha256']
            index.append(item['message_id'])
        offset=page['next_offset']
    assert index==mids


def test_instruction_pages_remain_scoped_to_selected_task(conn):
    a=hb_tasks.bind(conn,7,say(conn,'first task'),studio=False)
    b=hb_tasks.bind(conn,7,say(conn,'second task'),studio=False)
    amid=say(conn,'private A');hb_tasks.bind(conn,7,amid,task_id=a['task_id'])
    bmid=say(conn,'private B');hb_tasks.bind(conn,7,bmid,task_id=b['task_id'])
    assert [r['message_id'] for r in hb_tasks.instruction_references(conn,a)['instructions']]==[amid]


def test_full_objective_is_readable_through_the_authenticated_task_tool(flow,monkeypatch):
    from core import agent_identity
    from test_practice_193_channels import _Shared
    db,_=flow
    rid=owner(db,'apex');task=hb_tasks.for_request(db,rid)
    objective='EMAIL '+('owner constraints and full body '*500)
    db.execute('UPDATE hb_tasks SET objective=? WHERE task_id=?',(objective,task['task_id']))
    monkeypatch.setattr('utils.db._connection.get_connection',lambda:_Shared(db))
    token=agent_identity.CURRENT.set({'principal':'apex','conversation_id':1,'task_id':task['task_id']})
    try:
        full=[];offset=0
        while offset is not None:
            page=hb_tasks.call('task_context',{'section':'objective','offset':offset})
            full.append(page['content']);offset=page['next_offset']
        assert ''.join(full)==objective
    finally:
        agent_identity.CURRENT.reset(token)


def test_task_context_schema_exposes_optional_pagination():
    schema=apex_tools._call_schema('task_context')['properties']['arguments']
    assert 'offset' in schema['properties'] and schema['required']==[]


def test_one_oversized_exact_objective_is_retained_for_review_and_other_task_delivers(flow):
    db,principals=flow
    bad=owner(db,'apex');bad_task=hb_tasks.for_request(db,bad)
    db.execute('UPDATE hb_tasks SET title=? WHERE task_id=?',('X'*20000,bad_task['task_id']))
    good=owner(db,'apex')
    original=db.execute('SELECT body FROM peer_messages WHERE id=?',(bad,)).fetchone()[0]
    ready=peer_bridge.inbox(db,principals['apex'],pending_only=True)
    assert good in [r['id'] for r in ready] and bad not in [r['id'] for r in ready]
    assert db.execute('SELECT state FROM hb_peer_work WHERE request_id=?',(bad,)).fetchone()[0]=='needs_review'
    assert db.execute('SELECT body FROM peer_messages WHERE id=?',(bad,)).fetchone()[0]==original
    assert db.execute('SELECT delivered_at FROM peer_messages WHERE id=?',(bad,)).fetchone()[0] is None
    assert hb_tasks.get(db,bad_task['task_id'])['title']=='X'*20000
