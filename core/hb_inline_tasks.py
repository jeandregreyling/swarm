"""Connect owner implementation chat to the same durable HB work queue."""
import re
import time
import uuid


def implementation_request(text,task_id=None):
    value=str(text).strip()
    if value.lower() in {'continue','resume','go on'}:return bool(task_id)
    return bool(re.match(r'^(?:@apex[,:\s]*)?(?:please\s+)?(?:(?:can|could|would|will) you(?: please)?\s+)?(?:help me\s+)?(?:i (?:want|need) you to\s+)?'
        r'(?:build|fix|implement|repair|add|update|change|make|create|enable|remove|complete)\b',value,re.I))


def start(conn,task,*,owner,allow_writes):
    from core import hb_task_manager,hb_tasks,hb_executions
    hb_task_manager.register(conn,task,next_action=task['objective'])
    tools=[t for t in hb_task_manager.EXECUTION_TOOLS if allow_writes or not t.startswith('propose_')]
    hb_tasks.event(conn,task,'hummingbird','tool_scope',{'allowed_tools':tools,'source':'authenticated owner inline request','owner':owner})
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if task['step_id'] and 'project_test_cases' in tables and not conn.execute('SELECT 1 FROM project_test_cases WHERE step_id=?',(task['step_id'],)).fetchone():
        now=time.time()
        conn.execute("INSERT INTO project_test_cases(case_id,project_id,step_id,title,status,owner,created_at,updated_at) VALUES (?,?,?,?,'ready','apex',?,?)",
            ('C-'+uuid.uuid4().hex[:10].upper(),task['project_id'],task['step_id'],'Verify owner goal: '+task['title'][:175],now,now))
    return hb_executions.claim(conn,task,agent='apex',kind='inline')
