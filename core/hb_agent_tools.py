"""Guarded execution additions for the assigned APEX task, not a host shell."""
import json
import re
from contextlib import closing

READ_TOOLS = {'local_job_status','gemini_status','task_context', 'task_memory', 'task_evidence','reference_lookup'}
ACCEPT_TOOLS = {'studio_accept','task_plan','runtime_reload'}
WRITE_TOOLS = {'gemini_reload','local_review','archive_acquire','studio_note', 'studio_status', 'studio_task','task_plan', 'run_tests', 'reference_import', 'git_clear_stale_lock'}
WRITE_TOOLS = WRITE_TOOLS | {'does_rename', 'layout', 'change_set', 'studio_proposal'}     # owner 13 Nov: the DOES rename tool (core/hb_rename.py)


def public_error(value):
    text = str(value)[:1000]
    text = re.sub(r'(?i)(?:hbp_|AIza|sk-)[A-Za-z0-9_-]{12,}', '[redacted]', text)
    text = re.sub(r'(?i)(authorization|api[_ -]?key|password|cookie|bearer|secret|token)\s*[:=]\s*[^\s,;}]+', r'\1=[redacted]', text)
    return text


def ground_answer(answer,receipts):
    for receipt in reversed(receipts):
        if receipt.get('tool')!='archive_acquire' or receipt.get('status')!='succeeded':continue
        try:result=json.loads(receipt.get('output','{}'))
        except (ValueError,TypeError):continue
        state=result.get('status');job=result.get('job_id')
        if job and state in {'queued','running','paused','failed'}:
            return 'HF job '+str(job)+' is '+state+': '+str(result.get('stage') or result.get('error') or 'waiting for the worker')+'. Download/index completion is not yet verified; HB will return its result.'
    for receipt in reversed(receipts):
        if receipt.get('tool')!='ask_instructor' or receipt.get('status')!='succeeded':continue
        try:result=json.loads(receipt.get('output','{}'))
        except (ValueError,TypeError):continue
        if result.get('status') in {'waiting','not_queued','local_review_queued'} and re.search(r'(?i)queue|permission|authoriz',answer):
            if result['status'] in {'not_queued','local_review_queued'}:return result['notice']
            return ('The previous request '+str(result['request_ids'][0])+' remains '+str(result.get('recorded_state','waiting'))+
                    ': '+str(result.get('recorded_stage','provider unavailable'))+'. No new online request was queued. '+result['notice'])
    return answer


def call(tool, args):
    from core import agent_identity, hb_tasks
    if tool in {'local_review','local_job_status','archive_acquire'}:
        from core.hb_local_jobs import call as local_call
        return local_call(tool,args)
    if tool=='gemini_reload':
        from core.hb_peer_control import gemini_reload
        return gemini_reload(args)
    if tool=='gemini_status':
        if args:raise ValueError('gemini_status takes no arguments')
        import config
        from core.peer_coordination import worker_alive
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn:
            rows=[dict(zip(('request_id','state','stage','delivered_at'),row)) for row in conn.execute('''SELECT p.id,w.state,w.stage,p.delivered_at FROM peer_messages p
                LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.recipient='gemini-advisor'
                AND p.body NOT LIKE '[TEAM COPY, observe:%' ORDER BY p.id DESC LIMIT 4''')]
            success=conn.execute("SELECT p.id,p.conversation_id,p.delivered_at FROM peer_messages p JOIN hb_peer_work w ON w.request_id=p.id WHERE p.recipient='gemini-advisor' AND w.state='completed' AND p.delivered_at IS NOT NULL ORDER BY p.id DESC LIMIT 1").fetchone()
        from scripts.hummingbird_gemini_peer import selected_provider_model
        return {'provider':'Google','model':selected_provider_model(config.GEMINI_AGENT_MODEL),'configured_model':config.GEMINI_AGENT_MODEL,'credential_configured':bool(config.GEMINI_API_KEY),
                'worker_running':worker_alive('gemini-advisor'),'recent_requests':rows,
                'last_verified_delivery':dict(zip(('request_id','conversation_id','delivered_at'),success)) if success else None,
                'notice':'Canonical recorded metadata only; no credential values and no new online call. A successful delivery does not guarantee future provider availability.'}
    if tool == 'reference_lookup':
        from core.hb_references import lookup
        if set(args)-{'query','allow_online'} or 'query' not in args:raise ValueError('reference_lookup requires query and optional allow_online')
        return lookup(**args)
    if tool == 'reference_import':
        from core.hb_references import ingest
        if set(args)!={'kind','repo','revision','path'}:raise ValueError('reference_import requires kind, repo, revision and path')
        return ingest(**args)
    if tool=='runtime_reload':
        if args:raise ValueError('runtime_reload takes no arguments; the accepted task fixes its scope')
        from core.hb_runtime_reload import request_reload
        return request_reload()
    if tool in {'task_context','task_memory','task_evidence','studio_note','studio_status','studio_task','task_plan','studio_accept'}:
        return hb_tasks.call(tool,args)
    actor=agent_identity.CURRENT.get()
    if not actor or actor['principal']!='apex' or not (actor.get('peer_request_id') or actor.get('task_id')):
        raise PermissionError('Guarded tests require the assigned authenticated APEX turn')
    if tool=='layout':     # owner 13 Nov: system review and cleanup (core/hb_layout.py); moves are logged and undoable
        from utils.db._connection import get_connection
        from core.hb_layout import call as layout_call
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:raise PermissionError('layout requires a linked Studio task')
        result=layout_call(args)
        if args.get('action') in ('move','undo'):
            with closing(get_connection()) as conn,conn:
                hb_tasks.event(conn,task,actor['principal'],'mutation',{'status':'succeeded','tool':'layout','output':'layout '+str(args.get('action'))+': '+json.dumps(result)[:400]},request_id=actor.get('peer_request_id'))
        return result
    if tool=='studio_proposal':   # owner 14 Nov: an advisor proposes a change with code; HB checks it, APEX applies it (core/hb_proposals.py)
        from utils.db._connection import get_connection
        from core.hb_proposals import create as propose
        with closing(get_connection()) as conn,conn:
            task=(hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else
                  hb_tasks.get(conn,actor['task_id']) if actor.get('task_id') else None)
            return propose(conn,actor['principal'],args,task)
    if tool=='change_set':     # owner 14 Nov: Claude Code's prepared, tested change for this step (core/hb_change_sets.py)
        from utils.db._connection import get_connection
        from core.hb_change_sets import call as change_set_call
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:raise PermissionError('change_set requires a linked Studio task')
        result=change_set_call(args,task.get('step_id'))
        if args.get('action')=='apply' and result.get('state')=='applied':
            with closing(get_connection()) as conn,conn:
                hb_tasks.event(conn,task,actor['principal'],'mutation',{'status':'succeeded','tool':'change_set',
                    'output':'change set applied: '+json.dumps(result)[:400]},request_id=actor.get('peer_request_id'))
        return result
    if tool=='does_rename':
        from utils.db._connection import get_connection
        from core.hb_rename import call as rename_call
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:raise PermissionError('does_rename requires a linked Studio task')
        result=rename_call(args)
        if args.get('action')!='status' and 'note' not in result:
            with closing(get_connection()) as conn,conn:
                hb_tasks.event(conn,task,actor['principal'],'mutation',{'status':'succeeded','tool':'does_rename',
                    'output':'DOES rename '+str(args.get('action'))+': '+json.dumps(result)[:400]},request_id=actor.get('peer_request_id'))
        return result
    if tool=='git_clear_stale_lock':
        if args:raise ValueError('git_clear_stale_lock takes no arguments')
        from core.hb_git_maintenance import clear_stale_lock
        return clear_stale_lock()
    if tool=='run_tests':
        from utils.db._connection import get_connection
        from core.apex_test_runner import run_tests
        from core.apex_alm import run_recorded_tests
        with closing(get_connection()) as conn:
            task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
        if not task:
            raise PermissionError('Tests require a linked Studio task')
        values=dict(args)
        if values.get('case_id') in (None,'',task['step_id']):   # APEX often passes its step id; the step's own case is meant
            values.pop('case_id',None)
        if 'case_id' not in values:
            from core.knowledge import projects
            cases=projects.list_test_cases(task['project_id'],step_id=task['step_id'])
            if not cases:
                case=projects.add_test_case(task['project_id'],'Guarded task regression checks',step_id=task['step_id'],owner='apex')
                if not case:raise RuntimeError('Could not register the task test case')
            else:
                case=cases[0]['case_id']
            values['case_id']=case
        else:
            from core.knowledge import projects
            case=projects.get_test_case(values['case_id'])
            if not case or case.get('step_id')!=task['step_id']:
                raise PermissionError('Test case must belong to this assigned task step (leave case_id out to use the step\'s own case)')
        result=run_recorded_tests(values,run_tests)
        with closing(get_connection()) as conn,conn:
            hb_tasks.event(conn,task,actor['principal'],'test_result',result,request_id=actor.get('peer_request_id'))
        return result
    raise ValueError('Unknown guarded tool')
