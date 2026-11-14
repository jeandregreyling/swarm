"""Authenticated self-service identity, private memory, tools and owner audit."""
from contextlib import closing
import hashlib
import json
import uuid

from flask import Blueprint, g, jsonify, request

from core import agent_identity as runtime
from core import peer_bridge as peers
from core.apex_tools import ReadOnlyRepository
from core.tool_approval import ApprovalStore
from services.auth import require_owner
from utils.db._connection import get_connection

agent_identity_bp = Blueprint('agent_identity', __name__)


def owner_memory_route(kind,agent=None):
    """Keep existing owner memory screens connected to the new private files."""
    from services.auth import get_current_user
    owner = get_current_user()
    if not owner or owner.get('role')!='owner':
        return jsonify(ok=False,error='Owner session required to inspect other agents\' private memory'),403
    try:
        limit = int(request.args.get('limit','10'))
        minimum = int(request.args.get('min_importance','0'))
        if kind=='query':
            query = request.args.get('q','').strip()
            if not query:
                raise ValueError('q required')
            targets = [value.strip() for value in request.args.get('agents','').split(',') if value.strip()]
            if not targets:
                targets = [path.name for path in runtime.STATE.iterdir()
                           if path.is_dir() and (path/'credentials.json').is_file()]
            results = {}
            for target in targets:
                runtime.credentials(target)
                rows = [dict(row) for row in runtime.read_memory(target,query,limit) if row['importance']>=minimum]
                if rows:
                    results[target]=rows
            return jsonify(query=query,agents=list(results),results=results)
        runtime.credentials(agent)
        if kind=='read':
            query = request.args.get('query','')
            rows = [dict(row) for row in runtime.read_memory(agent,query,limit) if row['importance']>=minimum]
            return jsonify(agent=agent,table='private_memory.sqlite',query=query,limit=limit,entries=rows)
        data = _json()
        content = data.get('content')
        if not isinstance(content,str) or not content.strip() or len(content)>16000:
            raise ValueError('Memory content must be nonempty text up to 16000 characters')
        # The host writes an owner-supplied note; never attribute it to the recipient model.
        with runtime.execution('fridays',requested_by=owner['username']) as identity:
            action = uuid.uuid4().hex
            runtime.event(identity,action,'memory.owner_note','started',paths=['agent:'+agent])
            with closing(runtime._memory(agent)) as conn:
                cur = conn.execute('INSERT INTO memories(subject,content,tags,importance,source) VALUES (?,?,?,?,?)',
                    (str(data.get('subject') or content[:100])[:200],content,
                     str(data.get('tags') or '')[:500],int(data.get('importance',5)),'owner:'+owner['username']))
                conn.commit()
                record = cur.lastrowid
            runtime.event(identity,action,'memory.owner_note','succeeded',paths=['agent:'+agent],
                          result={'memory_id':record})
        return jsonify(ok=True,agent=agent,entry_id=record,executor='fridays',requested_by=owner['username'])
    except PermissionError as exc:
        from core.hb_agent_tools import public_error
        return jsonify(ok=False,error=public_error(exc),category='permission_denied'),403
    except (OSError,ValueError,TypeError) as exc:
        from core.hb_agent_tools import public_error
        return jsonify(ok=False,error=public_error(exc),category='invalid_arguments'),400


def _with_identity(handler):
    if not runtime.enabled():
        return jsonify(ok=False,error='Individual agent logins have not been provisioned'),503
    if request.remote_addr not in {'127.0.0.1','::1'}:
        return jsonify(ok=False,error='Agent API is loopback-only'),403
    scheme, _, raw = request.headers.get('Authorization','').partition(' ')
    if scheme.lower() != 'bearer' or not raw:
        return jsonify(ok=False,error='Individual agent bearer token required'),401
    try:
        with closing(get_connection()) as conn:
            principal = runtime.authenticate(conn,raw,request.headers.get('X-Agent-Id'))
            conn.commit()
        with runtime.execution(principal['id'],principal=principal):
            return handler(principal)
    except PermissionError as exc:
        from core.hb_agent_tools import public_error
        return jsonify(ok=False,error=public_error(exc),category='permission_denied'),403
    except peers.PeerError as exc:
        return jsonify(ok=False,error=str(exc)),exc.status
    except (ValueError,TypeError) as exc:
        from core.hb_agent_tools import public_error
        return jsonify(ok=False,error=public_error(exc),category='invalid_arguments'),400
    except FileNotFoundError as exc:
        from core.hb_agent_tools import public_error
        return jsonify(ok=False,error=public_error(exc),category='not_found'),404
    except (OSError,RuntimeError) as exc:
        return jsonify(ok=False,error=str(exc)),503


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data,dict):
        raise ValueError('JSON object required')
    return data


def _profile_writes(agent):
    """Owner 14 Nov: write access comes from the agent's profile (onboarded local agents), not from being called 'apex'."""
    try:
        from core.hb_agents import writes
        from contextlib import closing
        with closing(get_connection()) as conn:
            return writes(conn, agent)
    except Exception:
        return False


def _tools(principal):
    peers.require_scope(principal,'agent.tools')
    from utils.local_runtime_policy import agent_skill_allowed
    from database import can_user_invoke_skill
    from core.apex_permissions import autonomous_writes_allowed
    agent = principal['id']
    readable = ((agent == 'seven' or agent_skill_allowed(agent,'fs_readonly'))
                and can_user_invoke_skill(agent,'fs_readonly',default_allow=False))
    writable = (readable and agent_skill_allowed(agent,'fs_write')
                and can_user_invoke_skill(agent,'fs_write',default_allow=False)
                and 'agent.write' in principal['scopes']
                and (agent=='apex' or _profile_writes(agent)) and autonomous_writes_allowed('ghost'))
    from core.hb_workflow import (CONTROL_READ_TOOLS,CONTROL_WRITE_TOOLS,MEMORY_TOOLS,
        CODEX_WORKFLOW_READ_TOOLS,CODEX_WORKFLOW_WRITE_TOOLS)
    controls=set(MEMORY_TOOLS) if 'agent.memory' in principal['scopes'] else set()
    if (readable and agent_skill_allowed(agent,'knowledge_search')
            and can_user_invoke_skill(agent,'knowledge_search',default_allow=False)):
        controls.update(CONTROL_READ_TOOLS)
        if agent == 'apex':
            controls.add('alm_step_get')
        if agent=='codex-instructor':
            controls.update(CODEX_WORKFLOW_READ_TOOLS | CODEX_WORKFLOW_WRITE_TOOLS)
        if writable:
            controls.update(CONTROL_WRITE_TOOLS)
    if readable and agent_skill_allowed(agent,'shell') and can_user_invoke_skill(agent,'shell',default_allow=False):
        controls.add('terminal_run')
    from core.hb_agent_tools import READ_TOOLS, WRITE_TOOLS, ACCEPT_TOOLS
    if readable:controls.update(READ_TOOLS)
    if readable and agent in {'apex','codex-instructor','copilot-instructor'}:controls.add('task_plan')
    if writable:controls.update(WRITE_TOOLS)
    if readable and agent in {'codex-instructor','copilot-instructor'}:controls.update(ACCEPT_TOOLS)
    if readable:   # owner 14 Nov: an agent's profile adds its tools (core/hb_agent_profiles.py) - onboarding without code for its name
        from core.hb_agent_profiles import tools_for
        controls.update(tools_for(agent))
    return sorted(controls | (runtime.SOURCE_TOOLS if readable else set()) | (runtime.WRITE_TOOLS if writable else set()))


@agent_identity_bp.route('/api/agent/v1/whoami')
def identity():
    return _with_identity(lambda p: jsonify(ok=True,principal=p['id'],credential_id=p['credential_id'],
        memory_file=str(runtime.STATE/p['id']/'memory.sqlite'),tools=_tools(p)))


@agent_identity_bp.route('/api/agent/v1/memory',methods=['GET','POST'])
def memory():
    def handle(principal):
        peers.require_scope(principal,'agent.memory')
        if request.method == 'GET':
            rows = runtime.read_memory(principal['id'],request.args.get('query',''),int(request.args.get('limit','20')))
            return jsonify(ok=True,principal=principal['id'],memories=[dict(row) for row in rows])
        data = _json()
        if set(data)-{'subject','content','tags','importance','context'} or not {'subject','content'}<=set(data):
            raise ValueError('Memory accepts subject, content, optional tags and importance; no target identity')
        if not isinstance(data['content'],str) or len(data['content'])>16000:
            raise ValueError('Memory content must be text up to 16000 characters')
        context=data.get('context')
        if context is not None:
            if not isinstance(context,dict) or set(context)!={'request_id','model'} or type(context.get('request_id')) is not int or context['request_id']<=0 or not isinstance(context.get('model'),str) or not 1<=len(context['model'])<=160:
                raise ValueError('Memory context requires request_id and model')
            with closing(get_connection()) as conn:
                invite=conn.execute("SELECT conversation_id FROM peer_messages WHERE id=? AND recipient=? AND delivered_at IS NULL AND body NOT LIKE '[TEAM COPY, observe:%' AND NOT EXISTS(SELECT 1 FROM hb_peer_work w WHERE w.request_id=peer_messages.id AND w.state IN ('completed','failed','needs_review','cancelled'))",(context['request_id'],principal['id'])).fetchone()
            if not invite:raise PermissionError('Memory context must name this agent pending request')
            runtime.CURRENT.get().update(peer_request_id=context['request_id'],conversation_id=invite[0],model=context['model'][:160])
        action = uuid.uuid4().hex
        identity = runtime.CURRENT.get()
        runtime.event(identity,action,'memory.write','started')
        record = runtime.save_memory(principal['id'],data['subject'],data['content'],
            data.get('tags',''),data.get('importance',5),'authenticated_agent_api')
        runtime.event(identity,action,'memory.write','succeeded',result={'memory_id':record})
        return jsonify(ok=True,memory_id=record,principal=principal['id']),201
    return _with_identity(handle)


@agent_identity_bp.route('/api/agent/v1/tools',methods=['GET','POST'])
def tools():
    def handle(principal):
        allowed = _tools(principal)
        if request.method == 'GET':
            return jsonify(ok=True,principal=principal['id'],tools=allowed)
        data = _json()
        if set(data)-{'tool','arguments','context'} or not {'tool','arguments'}<=set(data) or not isinstance(data['arguments'],dict):
            raise ValueError('Tool request requires only tool and arguments')
        tool, args = data['tool'],data['arguments']
        if not isinstance(tool,str) or tool not in allowed:
            raise PermissionError('Tool is not granted to this authenticated agent')
        context=data.get('context')
        if context is not None:
            if (not isinstance(context,dict) or set(context)!={'request_id','model'}
                    or type(context['request_id']) is not int or context['request_id']<=0
                    or not isinstance(context['model'],str) or not 1<=len(context['model'])<=160):
                raise ValueError('Execution context requires a peer request ID and reported model')
            with closing(get_connection()) as conn:
                invitation=conn.execute('''SELECT conversation_id,sender FROM peer_messages
                    WHERE id=? AND recipient=? AND delivered_at IS NULL
                    AND body NOT LIKE '[TEAM COPY, observe:%'
                    AND NOT EXISTS(SELECT 1 FROM hb_peer_work w WHERE w.request_id=peer_messages.id AND w.state IN ('completed','failed','needs_review','cancelled')) ''',
                    (context['request_id'],principal['id'])).fetchone()
            if invitation is None:
                raise PermissionError('Tool context requires this agent\'s pending explicit invitation')
            from core import hb_tasks
            with closing(get_connection()) as conn:
                task=hb_tasks.for_request(conn,context['request_id'])
                scope=hb_tasks.invitation_tools(conn,context['request_id'])
                if scope is not None and tool not in scope:raise PermissionError('This focused invitation only attaches: '+', '.join(sorted(scope)))
                if task and task['state'] in {'paused','cancelled'}:raise PermissionError('Assigned task is '+task['state'])
                if task:
                    from core.hb_chat_controls import continuation,held_requests
                    if continuation(conn,task)['mode']=='off' or held_requests(conn,task):raise PermissionError('Owner held this task with its chat/request control')
                    from core import hb_executions
                    executor=hb_executions.for_request(conn,context['request_id'])
                    if executor:
                        hb_executions.verify(conn,executor,task['task_id'])
                        runtime.CURRENT.get().update(execution_id=executor,task_id=task['task_id'],task_version=task['version'])
                from core.hb_agent_tools import WRITE_TOOLS
                if task and tool in runtime.WRITE_TOOLS | WRITE_TOOLS | {'archive_ingest','archive_mirror_resume','archive_mirror_curate'}:
                    if tool in runtime.WRITE_TOOLS:
                        from core.hb_owner_sessions import enforce_write_scope
                        enforce_write_scope(conn,task,context['request_id'],tool,args)
                    version=conn.execute('SELECT task_version FROM hb_task_requests WHERE request_id=?',(context['request_id'],)).fetchone()[0]
                    if task['state']=='completed':raise PermissionError('Task already passed acceptance')
                    if version!=task['version']:raise peers.PeerError(409,'Task instructions changed; call task_context before any further side effect')
            runtime.CURRENT.get().update(model=context['model'],model_provenance='agent_runtime_report',
                conversation_id=invitation[0],requested_by=invitation[1],peer_request_id=context['request_id'])
        repository = ReadOnlyRepository()
        action = uuid.uuid4().hex
        if tool in runtime.WRITE_TOOLS:
            operation=None
            if context is not None and tool in {'propose_patch','propose_write_file'}:
                from core import hb_task_operations
                with closing(get_connection()) as ledger,ledger:
                    task=hb_tasks.for_request(ledger,context['request_id'])
                    reused=hb_task_operations.replay(ledger,repository,task,tool,args) if task else None
                    if reused:
                        hb_tasks.event(ledger,task,principal['id'],'mutation_replayed',reused,request_id=context['request_id'])
                if reused:return jsonify(ok=True,principal=principal['id'],receipt=reused)
            store = ApprovalStore()
            try:
                transaction = store.propose(repository,tool,args,principal['id'],
                    'credential:'+str(principal['credential_id']),0)
            except (ValueError,PermissionError) as exc:
                if context is not None and task:
                    # Validation can fail before a source transaction exists.
                    # Retain enough bounded input to diagnose escaping/context
                    # errors, without treating a failed proposal as an effect.
                    from core.hb_agent_tools import public_error
                    preview={'path':str(args.get('file_path',args.get('path','')))[:500]}
                    if tool=='propose_patch':
                        old=args.get('exact_old_text','')
                        preview.update(old_text_prefix_repr=repr(old[:400]) if isinstance(old,str) else type(old).__name__,
                            old_text_characters=len(old) if isinstance(old,str) else None,
                            literal_backslash_n=isinstance(old,str) and '\\n' in old,
                            new_text_characters=len(args.get('new_text','')) if isinstance(args.get('new_text'),str) else None)
                    with closing(get_connection()) as ledger,ledger:
                        hb_tasks.event(ledger,task,principal['id'],'tool_failure',{'tool':tool,
                            'category':type(exc).__name__,'error':public_error(exc),
                            'arguments_preview':preview,'notice':'Partial diagnostic only; no source transaction or effect.'},request_id=context['request_id'])
                raise
            if context is not None and tool in {'propose_patch','propose_write_file'} and task:
                with closing(get_connection()) as ledger,ledger:
                    operation=hb_task_operations.begin(ledger,task,tool,args,transaction,execution_id=runtime.CURRENT.get().get('execution_id'))
            result = store.decide(transaction.id,True,transaction.owner,transaction.session,
                transaction.csrf,lambda name: name in _tools(principal))
            if operation:
                with closing(get_connection()) as ledger,ledger:
                    result=hb_task_operations.finish(ledger,operation,result)
            if context is not None:
                from core import hb_tasks
                with closing(get_connection()) as conn,conn:
                    task=hb_tasks.for_request(conn,context['request_id'])
                    if task:hb_tasks.event(conn,task,principal['id'],'mutation',result,request_id=context['request_id'])
                hb_tasks.flush_memory()
            return jsonify(ok=result['status']=='succeeded',principal=principal['id'],receipt=result)
        identity = runtime.CURRENT.get()
        runtime.event(identity,action,tool,'started')
        try:
            from core.hb_workflow import (CONTROL_READ_TOOLS, CONTROL_WRITE_TOOLS, MEMORY_TOOLS,
                CODEX_WORKFLOW_READ_TOOLS, CODEX_WORKFLOW_WRITE_TOOLS, call_control)
            if tool == 'alm_step_get':
                from core.apex_alm import read_step
                if set(args) != {'step_id'}:
                    raise ValueError('alm_step_get accepts only step_id')
                if context is None:
                    raise PermissionError('Studio step access requires a pending explicit invitation')
                output = json.dumps(read_step(args['step_id']), ensure_ascii=True)
            elif tool in __import__('core.hb_agent_tools',fromlist=['READ_TOOLS']).READ_TOOLS | __import__('core.hb_agent_tools',fromlist=['WRITE_TOOLS']).WRITE_TOOLS | __import__('core.hb_agent_tools',fromlist=['ACCEPT_TOOLS']).ACCEPT_TOOLS:
                from core.hb_agent_tools import call
                output=json.dumps(call(tool,args),ensure_ascii=True)
            elif tool in CONTROL_READ_TOOLS | CONTROL_WRITE_TOOLS | MEMORY_TOOLS | CODEX_WORKFLOW_READ_TOOLS | CODEX_WORKFLOW_WRITE_TOOLS | {'terminal_run'}:
                output=json.dumps(call_control(tool,args),ensure_ascii=True)
            else:
                output = repository.call(tool,args)
        except Exception as exc:
            if context is not None:
                from core import hb_tasks
                from core.hb_agent_tools import public_error
                safe_args={key:(public_error(value)[:300] if key not in {'content','exact_old_text','new_text'} else {'sha256':hashlib.sha256(str(value).encode()).hexdigest(),'length':len(str(value))}) for key,value in args.items()}
                with closing(get_connection()) as conn,conn:
                    task=hb_tasks.for_request(conn,context['request_id'])
                    if task:hb_tasks.event(conn,task,principal['id'],'tool_failure',{'tool':tool,'arguments':safe_args,'category':type(exc).__name__,'error':public_error(exc)},request_id=context['request_id'])
            runtime.event(identity,action,tool,'failed',result={'error_type':type(exc).__name__})
            raise
        runtime.event(identity,action,tool,'succeeded',result={'output_sha256':hashlib.sha256(output.encode()).hexdigest()})
        if context is not None:
            from core import hb_tasks
            with closing(get_connection()) as conn,conn:
                task=hb_tasks.for_request(conn,context['request_id'])
                if task:
                    from core.hb_learning import safe_arguments
                    hb_tasks.event(conn,task,principal['id'],'tool_result',{'tool':tool,'status':'succeeded','action_id':action,
                        'arguments':safe_arguments(args),'output':output},request_id=context['request_id'])
            hb_tasks.flush_memory()
        return jsonify(ok=True,principal=principal['id'],action_id=action,output=output)
    return _with_identity(handle)


@agent_identity_bp.route('/api/agent/v1/audit')
def own_audit():
    return _with_identity(lambda p: jsonify(ok=True,principal=p['id'],
        events=runtime.audit_rows(agent=p['id'],limit=int(request.args.get('limit','50')))))


@agent_identity_bp.route('/api/agent/v1/execution',methods=['POST'])
def execution_lease():
    def handle(principal):
        peers.require_scope(principal,'peer.post')
        data=_json()
        if data.get('action') not in {'claim','release'} or type(data.get('request_id')) is not int:
            raise ValueError('Execution requires action and request_id')
        expected={'action','request_id','pid'} if data['action']=='claim' else {'action','request_id','execution_id','state'}
        if set(data)!=expected:raise ValueError('Execution fields do not match action')
        from core import hb_tasks,hb_executions,peer_turns
        with closing(get_connection()) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            invitation=conn.execute('SELECT recipient,delivered_at FROM peer_messages WHERE id=?',(data['request_id'],)).fetchone()
            task=hb_tasks.for_request(conn,data['request_id'])
            if not invitation or invitation[0]!=principal['id'] or not task:raise PermissionError('Execution requires this agent task invitation')
            if data['action']=='claim':
                if invitation[1] is not None or not peer_turns.ready(conn,data['request_id']):raise PermissionError('Task is held or this attempt already finished')
                key=hb_executions.claim(conn,task,agent=principal['id'],kind='peer',request_id=data['request_id'],pid=data['pid'])
            else:
                key=data['execution_id']
                own=conn.execute('SELECT 1 FROM hb_executions WHERE execution_id=? AND request_id=? AND agent=?',(key,data['request_id'],principal['id'])).fetchone()
                if not own:raise PermissionError('Execution belongs to another attempt')
                hb_executions.release(conn,key,data['state'])
        return jsonify(ok=True,execution_id=key)
    return _with_identity(handle)


@agent_identity_bp.route('/api/agent/v1/progress',methods=['POST'])
def progress():
    def handle(principal):
        peers.require_scope(principal,'peer.post')
        data = _json()
        if ((set(data)-{'conversation_id','status','stage','request_id','activity_id'} or not {'conversation_id','status','stage'}<=set(data))
                or type(data['conversation_id']) is not int
                or data['status'] not in {'queued','running','completed','failed'}
                or not isinstance(data['stage'],str) or len(data['stage'])>200):
            raise ValueError('Progress requires conversation_id, status and a brief public stage')
        with closing(get_connection()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            if not peers._invited(conn,[principal['id']],data['conversation_id']):
                raise PermissionError('Agent progress requires an invitation to this conversation')
            if 'request_id' in data:
                if type(data['request_id']) is not int or data['request_id']<=0:
                    raise ValueError('request_id must be positive')
                own=conn.execute('SELECT 1 FROM peer_messages WHERE id=? AND recipient=? AND conversation_id=?',
                    (data['request_id'],principal['id'],data['conversation_id'])).fetchone()
                if own is None:raise PermissionError('Progress request belongs to another agent or conversation')
                conn.execute('''CREATE TABLE IF NOT EXISTS hb_peer_work(request_id INTEGER PRIMARY KEY,
                    principal TEXT,state TEXT,stage TEXT,updated_at REAL)''')
                import time
                from core import hb_tasks
                from core.hb_chat_controls import continuation,held_requests
                task=hb_tasks.for_request(conn,data['request_id'])
                held=bool(task and (task['state'] in {'paused','cancelled','completed'}
                    or continuation(conn,task)['mode']=='off' or held_requests(conn,task)))
                status='cancelled' if held else data['status']
                conn.execute('INSERT OR REPLACE INTO hb_peer_work VALUES (?,?,?,?,?)',
                    (data['request_id'],principal['id'],status,'Owner hold retained; late progress saved as evidence' if held else data['stage'],time.time()))
                if task:
                    hb_tasks.event(conn,task,principal['id'],'progress',{'status':data['status'],'stage':data['stage'],'owner_held':held},request_id=data['request_id'])
                    if not held and data['status']=='failed':
                        state='waiting' if 'HTTP 50' in data['stage'] or 'network/timeout' in data['stage'] else 'needs_review'
                        conn.execute('UPDATE hb_tasks SET state=?,updated_at=? WHERE task_id=?',(state,time.time(),task['task_id']))
                    elif not held and data['status']=='completed' and principal['id']=='gemini-advisor' and task['state']=='waiting':
                        conn.execute("UPDATE hb_tasks SET state='active',updated_at=? WHERE task_id=?",(time.time(),task['task_id']))
                if held:data={**data,'status':status}
                conn.commit()
        from core.hb_tasks import flush_memory
        flush_memory()
        if 'activity_id' in data:
            import re,time
            if not isinstance(data['activity_id'],str) or not re.fullmatch(r'[a-z0-9-]{1,80}',data['activity_id']):
                raise ValueError('activity_id must be a short stable identifier')
            with closing(get_connection()) as conn,conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS hb_background_work(principal TEXT,activity_id TEXT,
                    conversation_id INTEGER,state TEXT,stage TEXT,updated_at REAL,
                    PRIMARY KEY(principal,activity_id,conversation_id))''')
                conn.execute('INSERT OR REPLACE INTO hb_background_work VALUES (?,?,?,?,?,?)',
                    (principal['id'],data['activity_id'],data['conversation_id'],data['status'],data['stage'],time.time()))
        from frontend.blueprints.peer_bridge import _publish
        detail={key:data[key] for key in ('request_id','activity_id') if key in data}
        _publish(data['conversation_id'],principal['id'],state=data['status'],peer=True,stage=data['stage'],**detail)
        return jsonify(ok=True,principal=principal['id'],status=data['status'])
    return _with_identity(handle)


@agent_identity_bp.route('/api/agent-identities/audit')
@require_owner
def owner_audit(current_user=None):
    return jsonify(ok=True,events=runtime.audit_rows(agent=request.args.get('agent') or None,
        limit=int(request.args.get('limit','50'))))


@agent_identity_bp.after_app_request
def record_agent_response(response):
    identity = getattr(g,'authenticated_agent_execution',None)
    if identity:
        body = response.get_json(silent=True)
        status = 'succeeded' if response.status_code<400 and (not isinstance(body,dict) or body.get('ok') is not False) else 'failed'
        runtime.event(identity,identity['run_id'],'http:'+request.method+' '+request.path,status,
                      result={'http_status':response.status_code})
    return response


@agent_identity_bp.teardown_app_request
def clear_agent_request(_error):
    token = g.pop('agent_execution_reset',None)
    if token is not None:
        runtime.CURRENT.reset(token)
