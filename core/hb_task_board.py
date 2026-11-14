"""A bounded projection of the canonical task, worker and Studio ledgers."""
import json
from core import hb_tasks


def project_tasks(conn,project_id,*,limit=50,offset=0):
    if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or offset<0:
        raise ValueError('limit must be1-100 and offset nonnegative')
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'projects' not in tables or not conn.execute('SELECT 1 FROM projects WHERE project_id=?',(project_id,)).fetchone():
        raise LookupError('Unknown Studio project')
    rows=conn.execute('SELECT task_id FROM hb_tasks WHERE project_id=? ORDER BY created_at,task_id LIMIT ? OFFSET ?',(project_id,limit+1,offset)).fetchall()
    result=[]
    from core.hb_chat_controls import continuation
    for (tid,) in rows[:limit]:
        task=hb_tasks.get(conn,tid)
        control=continuation(conn,task)
        current=conn.execute('SELECT phase,plan_event_id,detail FROM hb_task_manager WHERE task_id=?',(tid,)).fetchone() if 'hb_task_manager' in tables else None
        evidence=conn.execute('SELECT event_id,agent,kind,created_at FROM hb_task_events WHERE task_id=? ORDER BY event_id DESC LIMIT 1',(tid,)).fetchone()
        waiting=[]
        if 'hb_task_dependencies' in tables:
            waiting=[{'task_id':r[0],'title':r[1],'state':r[2]} for r in conn.execute('SELECT t.task_id,t.title,t.state FROM hb_task_dependencies d JOIN hb_tasks t ON t.task_id=d.depends_on WHERE d.task_id=?',(tid,))]
        plan=conn.execute('SELECT payload FROM hb_task_events WHERE event_id=?',(current[1],)).fetchone() if current else None
        agents=sorted({r['agent'] for r in control.get('pickups',[])})
        activation=conn.execute('SELECT state,detail FROM hb_runtime_reloads WHERE task_id=?',(tid,)).fetchone() if 'hb_runtime_reloads' in tables else None
        detail=current[2] if current else ''
        if activation:detail+=' Runtime activation '+activation[0]+': '+activation[1]
        result.append({**{k:task[k] for k in ('task_id','conversation_id','title','state','project_id','step_id','root_message_id','version')},
            'continuation':control,'assigned_to':agents or ['codex-instructor' if current and current[0]=='review' else 'apex'],
            'dependencies':waiting,'next_action':json.loads(plan[0]).get('next_action','')[:2000] if plan else task['objective'][:2000],
            'detail':detail,
            'runtime_activation':dict(zip(('state','detail'),activation)) if activation else None,
            'last_evidence':dict(zip(('event_id','agent','kind','created_at'),evidence)) if evidence else None})
    return {'project_id':project_id,'tasks':result,'next_offset':offset+limit if len(rows)>limit else None}
