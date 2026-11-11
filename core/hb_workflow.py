"""Owner-visible backlog and measured local execution history for APEX tools."""
from contextlib import closing
from pathlib import Path
import json
import time
import uuid
from utils.db._connection import get_connection


def memory_snapshot():
    result={'observed_at':time.time(),'scope':'whole_host_visible_to_this_process'}
    try:
        values={line.split(':',1)[0]:int(line.split()[1])*1024
                for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>=2
                and line.split()[1].isdigit()}
        for key in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):
            result[key+'_bytes']=values.get(key)
        result['active_swap']=bool(values.get('SwapTotal',0))
        vm={line.split()[0]:int(line.split()[1]) for line in Path('/proc/vmstat').read_text().splitlines()}
        result['swap_in_pages']=vm.get('pswpin',0)
        result['swap_out_pages']=vm.get('pswpout',0)
        result['major_page_faults']=vm.get('pgmajfault',0)
    except (OSError,ValueError):
        result['measurement_unavailable']=True
    return result


def _schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_model_runs(
        run_id TEXT PRIMARY KEY,conversation_id INTEGER,agent TEXT NOT NULL,model TEXT NOT NULL,
        category TEXT NOT NULL,status TEXT NOT NULL,elapsed_seconds REAL NOT NULL,tokens INTEGER,
        before_json TEXT NOT NULL,after_json TEXT NOT NULL,receipt_summary TEXT NOT NULL,created_at REAL NOT NULL)''')


def record_run(conversation_id,model,category,status,started,before,tokens,receipts,*,agent=None):
    from core.agent_identity import CURRENT
    actor=CURRENT.get()
    run_id=uuid.uuid4().hex
    after=memory_snapshot()
    summary=[{'tool':r.get('tool'),'status':r.get('status'),'receipt_id':r.get('id')}
             for r in receipts]
    with closing(get_connection()) as conn,conn:
        _schema(conn)
        conn.execute('INSERT INTO hb_model_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (run_id,conversation_id,actor['principal'] if actor else agent or 'apex',model,category,status,
             max(0,time.monotonic()-started),tokens,json.dumps(before),json.dumps(after),
             json.dumps(summary),time.time()))
    return {'run_id':run_id,'memory':after,'status':status}


def runtime_history():
    result={'memory':memory_snapshot(),'recent_runs':[],'comparisons':[]}
    with closing(get_connection()) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='hb_model_runs'").fetchone():
            result['notice']='No measured model turns recorded yet.'
            return result
        rows=conn.execute('''SELECT run_id,model,category,status,elapsed_seconds,tokens,after_json,created_at
            FROM hb_model_runs ORDER BY created_at DESC LIMIT 10''').fetchall()
        result['recent_runs']=[{'run_id':r[0],'model':r[1],'category':r[2],'status':r[3],
            'elapsed_seconds':r[4],'tokens':r[5],'memory':json.loads(r[6]),'created_at':r[7]} for r in rows]
        rows=conn.execute('''SELECT model,category,status,count(*),avg(elapsed_seconds),min(elapsed_seconds),
            max(elapsed_seconds) FROM hb_model_runs GROUP BY model,category,status ORDER BY max(created_at) DESC LIMIT 15''').fetchall()
        result['comparisons']=[dict(zip(('model','category','status','runs','mean_seconds','min_seconds','max_seconds'),r)) for r in rows]
    result['notice']='Measured wall time includes tool work; compare like tasks. Swap and faults are host-wide observations, not model-attributed RAM or proof that swap caused latency.'
    return result


def backlog(offset=0,query=None):
    if type(offset) is not int or not 0<=offset<=1_000_000:
        raise ValueError('Backlog offset must be a nonnegative integer')
    if query is not None and (not isinstance(query,str) or not 1<=len(query.strip())<=200):
        raise ValueError('Backlog query must contain 1-200 characters')
    with closing(get_connection()) as conn:
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'projects','project_steps'}<=tables:
            return {'status':'unavailable','reason':'ALM project/step tables are unavailable'}
        counts=[{'status':r[0],'count':r[1]} for r in conn.execute('SELECT status,count(*) FROM project_steps GROUP BY status')]
        rows=conn.execute('''SELECT s.step_id,s.project_id,p.name,s.title,s.status,s.owner,s.updated_at
            FROM project_steps s JOIN projects p ON p.project_id=s.project_id
            WHERE lower(COALESCE(s.status,'')) NOT IN ('done','completed','closed','skipped','cancelled','canceled')
            AND (? IS NULL OR instr(lower(p.name),lower(?))>0 OR instr(lower(s.title),lower(?))>0)
            ORDER BY CASE WHEN lower(s.status)='blocked' THEN 0 WHEN lower(s.status) IN ('doing','in_progress') THEN 1 ELSE 2 END,
            s.updated_at DESC,s.step_id LIMIT 16 OFFSET ?''',(query,query,query,offset)).fetchall()
        projects=conn.execute('SELECT count(*) FROM projects').fetchone()[0]
        background=[]
        if 'hb_background_work' in tables:
            background=[dict(zip(('agent','activity_id','conversation_id','state','stage','updated_at'),r))
                for r in conn.execute("SELECT principal,activity_id,conversation_id,state,stage,updated_at FROM hb_background_work WHERE state!='completed' ORDER BY updated_at DESC LIMIT 20")]
        peer_work=[]
        if 'peer_messages' in tables:
            join=('LEFT JOIN hb_peer_work w ON w.request_id=m.id' if 'hb_peer_work' in tables else '')
            state=("COALESCE(w.state,'queued'),COALESCE(w.stage,'Waiting for attached agent')" if join else "'queued','Waiting for attached agent'")
            peer_work=[dict(zip(('request_id','conversation_id','agent','sender','state','stage'),r))
                for r in conn.execute(f'''SELECT m.id,m.conversation_id,m.recipient,m.sender,{state}
                    FROM peer_messages m {join} WHERE m.delivered_at IS NULL
                    AND m.body NOT LIKE '[TEAM COPY, observe:%' ORDER BY m.id DESC LIMIT 20''')]

    items=[dict(zip(('step_id','project_id','project','title','status','owner','updated_at'),r)) for r in rows[:15]]
    return {'status':'found','source':'ALM Studio','projects':projects,'step_counts':counts,'items':items,'peer_requests':peer_work,'background_tasks':background,
            'next_offset':offset+15 if len(rows)>15 else None,
            'notice':'Live recorded ALM status, not a prediction of completion. Listing a task does not execute or approve it.'}


MEMORY_TOOLS=frozenset({'memory_search','memory_save'})

CONTROL_READ_TOOLS=frozenset({'backlog_list','runtime_status','knowledge_search','knowledge_read','archive_status'})
CONTROL_WRITE_TOOLS=frozenset({'archive_ingest','ask_instructor','archive_mirror_pause','archive_mirror_resume','archive_mirror_curate'})
CODEX_WORKFLOW_READ_TOOLS=frozenset({'workflow_status'})
CODEX_WORKFLOW_WRITE_TOOLS=frozenset({'workflow_control','apex_dispatch'})


def managed_processes():
    """List only Hummingbird-managed workers; never expose arbitrary host processes."""
    known={'hummingbird_hf_mirror.py':'hf-mirror','hummingbird_hf_index.py':'hf-dataset-index',
           'hummingbird_peer_worker.py':'peer-worker'}
    found=[]
    try: entries=Path('/proc').iterdir()
    except OSError:return {'available':False,'processes':[]}
    for entry in entries:
        if not entry.name.isdigit():continue
        try:
            if entry.stat().st_uid!=__import__('os').getuid():continue
            argv=[part for part in (entry/'cmdline').read_bytes().decode(errors='replace').split('\0') if part]
            script=next((Path(arg).name for arg in argv if Path(arg).name in known),None)
            if not script:continue
            state=next((line.split(':',1)[1].strip() for line in (entry/'status').read_text().splitlines()
                        if line.startswith('State:')),'unknown')
            found.append({'name':known[script],'pid':int(entry.name),
                          'state':'stopped' if state[:1] in {'T','t'} else 'running',
                          'proc_state':state[:32]})
        except (OSError,PermissionError,ValueError):continue
    return {'available':True,'processes':found}


def call_control(tool,args):
    if tool in CODEX_WORKFLOW_READ_TOOLS | CODEX_WORKFLOW_WRITE_TOOLS:
        from core import agent_identity,peer_bridge
        actor=agent_identity.CURRENT.get()
        if not actor or actor.get('principal')!='codex-instructor':
            raise PermissionError('Workflow coordination requires the authenticated Codex instructor login')
        conv_id=actor.get('conversation_id');request_id=actor.get('peer_request_id')
        if not conv_id or not request_id:
            raise PermissionError('Workflow tools require a current owner-invited Codex turn')
        with closing(get_connection()) as conn:
            invite=conn.execute('''SELECT sender FROM peer_messages WHERE id=? AND recipient='codex-instructor'
                AND conversation_id=? AND delivered_at IS NULL AND body NOT LIKE '[TEAM COPY, observe:%' ''',
                (request_id,conv_id)).fetchone()
            if (not invite or conn.execute('SELECT 1 FROM service_principals WHERE id=?',(invite[0],)).fetchone()):
                raise PermissionError('Workflow controls require a direct owner invitation')
            if tool=='workflow_status':
                if args:raise ValueError('workflow_status takes no arguments')
                from core.hb_workflow import visible_jobs
                from core.hf_mirror import status as mirror_status
                from core.hf_text_index import status as index_status
                from core.peer_coordination import status as peer_worker_status
                from core.peer_turns import status as peer_round_status
                return {'conversation_id':conv_id,'jobs':visible_jobs(conn,conv_id),
                        'peer_workers':peer_worker_status(conn),
                        'peer_rounds':peer_round_status(conn,conv_id),
                        'huggingface':mirror_status(),'dataset_index':index_status(),
                        'managed_processes':managed_processes(),
                        'notice':'Only Hummingbird-managed jobs are shown. Status is a snapshot; controls act at safe checkpoints.'}
        if tool=='workflow_control':
            if set(args)!={'action','target'} or args['target']!='huggingface-acquisition' or args['action'] not in {'pause','resume'}:
                raise ValueError('Control supports pause or resume for huggingface-acquisition only')
            from core import hf_mirror,hf_text_index
            hf_mirror.pause(args['action']=='pause')
            return {'ok':True,'action':args['action'],'target':args['target'],'mirror':hf_mirror.status(),
                    'dataset_index':hf_text_index.status(),
                    'message':'The active file may finish before pause takes effect.' if args['action']=='pause' else 'Acquisition and indexing resumed from saved state.'}
        if tool=='apex_dispatch':
            constraints=args.get('constraints',[])
            checks=args.get('acceptance_checks')
            if (set(args)-{'objective','constraints','acceptance_checks'}
                    or not isinstance(args.get('objective'),str) or not args['objective'].strip()
                    or len(args['objective'])>1000 or not isinstance(checks,list)
                    or not 1<=len(checks)<=5
                    or any(not isinstance(x,str) or not x.strip() or len(x)>300 for x in checks)
                    or not isinstance(constraints,list) or len(constraints)>5
                    or any(not isinstance(x,str) or not x.strip() or len(x)>300 for x in constraints)):
                raise ValueError('Provide one bounded objective, up to five constraints and one to five acceptance checks')
            body=json.dumps({'task_type':'codex_to_apex','objective':args['objective'].strip(),
                'constraints':constraints,'acceptance_checks':checks,
                'issued_by':'codex-instructor','parent_conversation_id':conv_id},ensure_ascii=False)
            if len(body)>peer_bridge.MAX_BODY:raise ValueError('Structured APEX task exceeds the peer message limit')
            with closing(get_connection()) as conn,conn:
                from core import agent_identity
                identity=agent_identity.CURRENT.get()
                action_id=uuid.uuid4().hex
                agent_identity.event(identity,action_id,'workflow.apex_dispatch','started',
                    result={'conversation_id':conv_id,'objective_sha256':__import__('hashlib').sha256(args['objective'].encode()).hexdigest()})
                message_id=conn.execute('''INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used)
                    VALUES (?,?,?,?,?,0)''',(conv_id,'codex-instructor','apex',body,'chat')).lastrowid
                request=peer_bridge.enqueue(conn,conv_id,message_id,body,['apex'],sender='codex-instructor')[0]
            agent_identity.event(identity,action_id,'workflow.apex_dispatch','succeeded',
                result={'peer_request_id':request,'objective_sha256':__import__('hashlib').sha256(args['objective'].encode()).hexdigest()})
            return {'ok':True,'request_id':request,'message_id':message_id,'conversation_id':conv_id,
                    'status':'queued','agent':'apex','notice':'Queued task, not a completed result. Check workflow_status for progress and receipts.'}
        raise ValueError('Unknown Codex workflow tool')
    if tool=='terminal_run' and set(args)=={'command'}:
        import re,shlex
        from core import agent_identity
        from database import can_user_invoke_skill
        from fridays import shell_agent
        actor=agent_identity.CURRENT.get()
        command=args['command']
        if not actor or not can_user_invoke_skill(actor['principal'],'shell',default_allow=False):
            raise PermissionError('This agent has no HB terminal grant')
        if (not isinstance(command,str) or not 1<=len(command)<=1000
                or re.search(r'[\x00-\x1f;|&`$<>\\]',command)):
            raise ValueError('Terminal diagnostics require a single command without shell composition')
        parts=shlex.split(command)
        safe={'df','free','uptime','uname','lsblk','ps','ss','ip','hostname','whoami','date','systemctl','journalctl'}
        match=shell_agent._match_whitelist(command)
        if (not parts or parts[0] not in safe or match is None or match[0]>2
                or (parts[0]=='journalctl' and '-u' in parts and
                    (parts.index('-u')+1>=len(parts) or parts[parts.index('-u')+1].startswith('-')))):
            raise ValueError('Command is outside the attached terminal diagnostic set; use existing HB Authorisations for elevated actions')
        ok,output=shell_agent.run(command,agent=actor['principal'],notify_ghost=False)
        return {'ok':ok,'command':command,'output':output,'executor':actor['principal']}
    if tool in MEMORY_TOOLS:
        from core import agent_identity
        actor=agent_identity.CURRENT.get()
        if not actor:raise PermissionError('Private memory requires authenticated agent execution')
        if tool=='memory_search' and not set(args)-{'query'}:
            return {'principal':actor['principal'],'memories':[dict(row) for row in
                agent_identity.read_memory(actor['principal'],args.get('query',''),limit=5)],
                'notice':'Private reference notes; verify claims against actual outcomes.'}
        if (tool=='memory_save' and set(args)=={'subject','content'} and
                all(isinstance(args[k],str) for k in args) and 0<len(args['subject'])<=200
                and 0<len(args['content'])<=16000):
            record=agent_identity.save_memory(actor['principal'],args['subject'],args['content'],
                tags='lesson,agent-reported',source='HB authenticated memory tool')
            return {'principal':actor['principal'],'memory_id':record,'status':'saved',
                    'notice':'Stored agent report; saving a claim does not verify it.'}
        raise ValueError('Invalid private memory arguments')
    if tool=='backlog_list' and not set(args)-{'offset','query'}:
        return backlog(args.get('offset',0),args.get('query'))
    if tool=='runtime_status' and not args:
        return runtime_history()
    if tool=='knowledge_search' and set(args)=={'query'}:
        from core.apex_knowledge import search
        return search(args['query'])
    if tool=='knowledge_read' and not set(args)-{'document_id','offset'} and 'document_id' in args:
        from core.apex_knowledge import read
        return read(args['document_id'],args.get('offset',0))
    if tool=='archive_status' and not set(args)-{'view','offset'}:
        from core.hf_library import archive_status
        return archive_status(**args)
    if tool=='ask_instructor' and set(args)=={'peer','question','context'}:
        from core import agent_identity,peer_bridge
        actor=agent_identity.CURRENT.get()
        if not actor or actor['principal']!='apex' or not actor.get('conversation_id'):
            raise PermissionError('Instructor request requires APEX and its invited conversation')
        with closing(get_connection()) as conn,conn:
            return peer_bridge.request_help(conn,actor['conversation_id'],**args)
    if tool=='archive_mirror_curate' and set(args)<= {'repo'}:
        from core import hf_mirror
        policy=hf_mirror.acquisition_policy()
        repositories=list(policy.get('explicit_repositories',[]))
        if 'repo' in args:
            if not isinstance(args['repo'],str):raise ValueError('repo must be a public Hub repository ID')
            repositories.append(args['repo'])
        return hf_mirror.set_acquisition_policy('curated',repositories)
    if tool in {'archive_mirror_pause','archive_mirror_resume'} and not args:
        from core.hf_mirror import pause
        return pause(tool=='archive_mirror_pause')
    if tool=='archive_ingest' and not args:
        from core.hf_library import ingest
        return ingest()
    raise ValueError('Unknown control tool or invalid arguments')


def visible_jobs(conn,conversation_id):
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    jobs=[]
    if 'hb_peer_work' in tables and 'peer_messages' in tables:
        for request,agent,state,stage,updated in conn.execute('''SELECT w.request_id,w.principal,w.state,w.stage,w.updated_at
            FROM hb_peer_work w JOIN peer_messages m ON m.id=w.request_id
            WHERE m.conversation_id=? AND w.state IN ('queued','running') ORDER BY w.updated_at DESC''',(conversation_id,)):
            jobs.append({'job_id':f'peer-{conversation_id}-{agent}-request-{request}','agent':agent,
                         'status':state,'stage':stage,'updated_at':updated,'stage_trace':[]})
        for request,agent,state,stage,updated in conn.execute('''SELECT w.request_id,w.principal,w.state,w.stage,w.updated_at
            FROM hb_peer_work w JOIN peer_messages m ON m.id=w.request_id
            WHERE m.conversation_id=? AND w.state NOT IN ('queued','running') ORDER BY w.updated_at DESC LIMIT 30''',(conversation_id,)):
            jobs.append({'job_id':f'peer-{conversation_id}-{agent}-request-{request}','agent':agent,
                         'status':state,'stage':stage,'updated_at':updated,'stage_trace':[]})
    if 'hb_background_work' in tables:
        for agent,activity,state,stage,updated in conn.execute('''SELECT principal,activity_id,state,stage,updated_at
            FROM hb_background_work WHERE conversation_id=? ORDER BY updated_at DESC LIMIT 10''',(conversation_id,)):
            jobs.append({'job_id':f'peer-{conversation_id}-{agent}-activity-{activity}','agent':agent,
                         'status':state,'stage':stage,'updated_at':updated,'stage_trace':[]})
    return jobs
