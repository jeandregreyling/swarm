"""peer_bridge.py — Hummingbird peer bridge routes for attached service participants.

Peers authenticate with scoped bearer tokens over loopback only.  Operator
audit and enable/disable controls require the owner session.  Operator chat
messages that mention @instructor, @copilot or @gemini are queued for peers
instead of being dispatched to a local model.
"""
from __future__ import annotations

import importlib
import logging
import sqlite3
import sys
import time

from flask import Blueprint, jsonify, request

from core import peer_bridge as peers
from services.auth import get_current_user, require_owner
from utils.db._connection import get_connection

peer_bridge_bp = Blueprint('peer_bridge', __name__)
_LOG = logging.getLogger('fridays.peer_bridge')
_LOOPBACK = {'127.0.0.1', '::1'}
_SERVICE_ENDPOINTS = {
    'peer_bridge.peer_whoami', 'peer_bridge.peer_inbox', 'peer_bridge.peer_ack',
    'peer_bridge.peer_post', 'peer_bridge.peer_thread', 'peer_bridge.peer_memory',
}


@peer_bridge_bp.before_app_request
def isolate_service_credentials():
    scheme, _, credential = request.headers.get('Authorization', '').partition(' ')
    if scheme.lower() == 'bearer' and credential.strip().startswith(peers.TOKEN_PREFIX):
        agent_endpoints = {'agent_identity.identity', 'agent_identity.memory',
                           'agent_identity.tools', 'agent_identity.own_audit', 'agent_identity.progress', 'agent_identity.execution_lease'}
        if (request.endpoint not in _SERVICE_ENDPOINTS | agent_endpoints
                and not (request.endpoint or '').startswith('agent_api.')):
            return jsonify({'ok': False, 'error': 'Service credentials require dedicated peer endpoints'}), 403


def _publish(conversation_id, agent, state="completed", **extra):
    try:
        from flask import current_app
        registered = current_app.blueprints.get('sse')
        mod = sys.modules.get(registered.import_name) if registered is not None else None
        if mod is None:
            mod = sys.modules.get('blueprints.sse') or importlib.import_module('frontend.blueprints.sse')
        mod.publish_chat_update(conversation_id, agent, state, **extra)
    except Exception:
        _LOG.exception('Peer SSE publish failed for conversation %s', conversation_id)


def _error(exc: peers.PeerError):
    return jsonify({'ok': False, 'error': str(exc)}), exc.status


def _with_peer(handler):
    if request.remote_addr not in _LOOPBACK:
        return jsonify({'ok': False, 'error': 'Peer bridge is loopback-only'}), 403
    header = request.headers.get('Authorization', '')
    raw = header[7:].strip() if header.startswith('Bearer ') else None
    conn = get_connection()
    try:
        peers.ensure_schema(conn)
        principal = peers.authenticate(conn, raw)
        if not principal:
            conn.commit()
            return jsonify({'ok': False, 'error': 'Invalid or disabled peer token'}), 401
        from core import agent_identity as attribution
        import uuid
        actor = None
        action_id = uuid.uuid4().hex
        if attribution.enabled():
            token_id = conn.execute('SELECT id FROM service_tokens WHERE token_sha256=?',
                                   (peers._digest(raw),)).fetchone()[0]
            actor = {'principal': principal['id'], 'credential_id': token_id,
                     'run_id': action_id, 'model': '', 'requested_by': '', 'conversation_id': None}
            attribution.event(actor, action_id, 'peer:' + request.path, 'started')
        try:
            result = handler(conn, principal)
            conn.commit()
        except Exception as exc:
            attribution.event(actor, action_id, 'peer:' + request.path, 'failed',
                              result={'error_type': type(exc).__name__})
            raise
        from core.hb_tasks import flush_memory
        flush_memory()
        attribution.event(actor, action_id, 'peer:' + request.path, 'succeeded')
        return result
    except (ValueError,PermissionError) as exc:
        conn.rollback()
        from core.hb_agent_tools import public_error
        return jsonify(ok=False,error=public_error(exc)),400 if isinstance(exc,ValueError) else 403
    except peers.PeerError as exc:
        conn.rollback()
        return _error(exc)
    finally:
        conn.close()


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise peers.PeerError(400, 'JSON object body required')
    return data


@peer_bridge_bp.route('/api/peer/v1/whoami')
def peer_whoami():
    return _with_peer(lambda conn, p: jsonify({
        'ok': True, 'principal': p['id'], 'display_name': p['display_name'], 'scopes': sorted(p['scopes']),
    }))


@peer_bridge_bp.route('/api/peer/v1/inbox')
def peer_inbox():
    def handler(conn, principal):
        after = request.args.get('after', '0')
        limit = request.args.get('limit', str(peers.MAX_BATCH))
        if not after.isdigit() or not limit.isdigit():
            raise peers.PeerError(400, 'after and limit must be non-negative integers')
        return jsonify({'ok': True, 'messages': peers.inbox(conn, principal, int(after), int(limit),pending_only=request.args.get('pending')=='1')})
    return _with_peer(handler)


@peer_bridge_bp.route('/api/peer/v1/inbox/ack', methods=['POST'])
def peer_ack():
    return _with_peer(lambda conn, p: jsonify({
        'ok': True, 'acknowledged': peers.acknowledge(conn, p, _json_body().get('ids')),
    }))


@peer_bridge_bp.route('/api/peer/v1/messages', methods=['POST'])
def peer_post():
    def handler(conn, principal):
        data = _json_body()
        allowed={'conversation_id','text','as','reply_to_request_id','route_reply','outcome','decision','usage','model','client_message_id'}
        if set(data)-allowed:
            raise peers.PeerError(400,'Unknown peer reply fields')
        result = peers.post(conn,principal,data.get('conversation_id'),data.get('text'),data.get('as'),
                            reply_to_request_id=data.get('reply_to_request_id'),route_reply=data.get('route_reply',True),
                            outcome=data.get('outcome','answer'),decision=data.get('decision'),usage=data.get('usage'),model=data.get('model',''),client_message_id=data.get('client_message_id'))
        conn.commit()
        _publish(result['conversation_id'], result['from_agent'], peer=True, message_id=result['message_id'])
        return jsonify({'ok': True, **result}), 201
    return _with_peer(handler)


@peer_bridge_bp.route('/api/peer/v1/threads/<int:conversation_id>')
def peer_thread(conversation_id):
    return _with_peer(lambda conn, p: jsonify({
        'ok': True, 'conversation_id': conversation_id,
        'messages': peers.thread(conn, p, conversation_id, int(request.args.get('limit', peers.THREAD_LIMIT) or peers.THREAD_LIMIT)),
    }))


@peer_bridge_bp.route('/api/peer/v1/memory', methods=['GET', 'POST'])
def peer_memory():
    def handler(conn, principal):
        if request.method == 'GET':
            return jsonify({'ok': True, 'memory': peers.memory(conn, principal, int(request.args.get('limit', '20') or 20))})
        data = _json_body()
        memory_id = peers.add_memory(conn, principal, data.get('kind'), data.get('content'), data.get('receipt'))
        return jsonify({'ok': True, 'memory_id': memory_id}), 201
    return _with_peer(handler)


@peer_bridge_bp.route('/api/peer/v1/principals')
@require_owner
def peer_principals(current_user=None):
    conn = get_connection()
    try:
        peers.ensure_schema(conn)
        conn.commit()
        return jsonify({'ok': True, 'principals': peers.audit(conn)})
    finally:
        conn.close()


@peer_bridge_bp.route('/api/peer/v1/conversations/<int:conversation_id>/activity')
@require_owner
def peer_conversation_activity(conversation_id, current_user=None):
    from core.apex_studio import read_task_board

    offset = request.args.get('offset', '0')
    if not offset.isdigit():
        return jsonify({'ok': False, 'error': 'Task offset must be a nonnegative integer'}), 400
    conn = get_connection()
    try:
        activity = peers.conversation_activity(conn, conversation_id)
        from core.hummingbird_status import runtime_stack_status
        runtime = runtime_stack_status()
        now = runtime.get('observed_at', time.time())
        runtime['agents'] = [{
            'id': person['id'],
            'last_contact': person['last_contact'],
            'state': 'recent contact' if person['last_contact'] and now - person['last_contact'] < 120
            else 'not recently observed',
        } for person in activity['participants']]
        activity['runtime'] = runtime
        activity['board'] = read_task_board(
            conversation_id, current_user['username'], offset=int(offset),
            revision=request.args.get('revision'),
        )
        return jsonify({'ok': True, **activity})
    except peers.PeerError as exc:
        return _error(exc)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 409
    except (sqlite3.DatabaseError, RuntimeError) as exc:
        _LOG.exception('Conversation activity unavailable for %s', conversation_id)
        return jsonify({'ok': False, 'error': 'Live task evidence unavailable; ' + str(exc)}), 503
    finally:
        conn.close()


@peer_bridge_bp.route('/api/peer/v1/principals/<principal_id>/enabled', methods=['POST'])
@require_owner
def peer_principal_enabled(principal_id, current_user=None):
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get('enabled'), bool):
        return jsonify({'ok': False, 'error': 'enabled must be a boolean'}), 400
    conn = get_connection()
    try:
        peers.ensure_schema(conn)
        peers.set_enabled(conn, principal_id, data['enabled'], current_user['username'])
        conn.commit()
        return jsonify({'ok': True, 'principal': principal_id, 'enabled': data['enabled']})
    except peers.PeerError as exc:
        conn.rollback()
        return _error(exc)
    finally:
        conn.close()


def dispatch_operator_message(data: dict, message: str, recipients: list[str]):
    """Queue an operator chat message for mentioned peers; no model dispatch occurs."""
    user = get_current_user()
    if not user or user['role'] != 'owner':
        return jsonify({'ok': False, 'response': 'Only the owner session can address service peers.'}), 403
    if len(message) > peers.MAX_BODY:
        return jsonify({'ok': False, 'response': f'Peer messages are limited to {peers.MAX_BODY} characters.'}), 413
    conn = get_connection()
    try:
        peers.ensure_schema(conn)
        conv_id = None
        requested = data.get('conversation_id')
        if requested is not None and not data.get('new_thread'):
            try:
                row = conn.execute('SELECT id FROM conversations WHERE id=?', (int(requested),)).fetchone()
                conv_id = int(row[0]) if row else None
            except (TypeError, ValueError):
                conv_id = None
        if conv_id is None:
            conv_id = conn.execute(
                'INSERT INTO conversations (title, source, sender) VALUES (?,?,?)',
                (f'Peers: {message[:90]}', 'terminal-ui:peer', user['username']),
            ).lastrowid
        message_id = conn.execute(
            """INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type, tokens_used)
               VALUES (?,?,?,?,?,0)""",
            (conv_id, 'user', ','.join(recipients), message, 'chat'),
        ).lastrowid
        from core import hb_tasks
        task = hb_tasks.bind(conn,conv_id,message_id,task_id=data.get('task_id'),project_id=data.get('project_id'),step_id=data.get('step_id'))
        queued = peers.enqueue(conn, conv_id, message_id, message, recipients, sender=user['username'])
        conn.commit()
    except (ValueError,PermissionError) as exc:
        conn.rollback()
        return jsonify({'ok':False,'response':str(exc)}), 400 if isinstance(exc,ValueError) else 403
    except peers.PeerError as exc:
        conn.rollback()
        return jsonify({'ok': False, 'response': str(exc)}), exc.status
    except sqlite3.DatabaseError:
        conn.rollback()
        _LOG.exception('Peer dispatch failed')
        return jsonify({'ok': False, 'response': 'Peer dispatch failed; nothing was queued.'}), 500
    finally:
        conn.close()
    from core.hb_tasks import flush_memory
    flush_memory()
    names = ', '.join(recipients)
    peer_statuses = [dict(peer=True, conversation_id=conv_id, agent=recipient, status='queued',
                          stage='Queued: waiting for the attached agent to pick up this request',request_id=request_id)
                     for recipient,request_id in zip(recipients,queued)]
    for progress in peer_statuses:
        _publish(conv_id, progress['agent'], state='queued', peer=True, stage=progress['stage'],request_id=progress['request_id'])
    return jsonify({
        'ok': True, 'mode': 'peer', 'conversation_id': conv_id, 'agent': 'peer-bridge',
        'agents': recipients, 'responses': [], 'pending_jobs': [], 'peer_message_ids': queued, 'task':task,
        'peer_statuses': peer_statuses,
        'response': f'Queued for {names} (peer messages {", ".join(map(str, queued))}). Replies appear in this thread.',
    })


@peer_bridge_bp.route('/api/peer/v1/conversations/<int:conversation_id>/tasks')
@require_owner
def task_list(conversation_id,current_user=None):
    from core import hb_tasks
    with __import__('contextlib').closing(get_connection()) as conn:
        hb_tasks.ensure_schema(conn)
        result=hb_tasks.list_tasks(conn,conversation_id)
        conn.commit()
    return jsonify(ok=True,tasks=result)


@peer_bridge_bp.route('/api/peer/v1/tasks/<task_id>/state',methods=['POST'])
@require_owner
def task_state(task_id,current_user=None):
    from core import hb_tasks
    data=request.get_json(silent=True) or {}
    if set(data)!={'state'} or data['state'] not in {'active','paused','cancelled'}:
        return jsonify(ok=False,error='Task state accepts active, paused or cancelled'),400
    with __import__('contextlib').closing(get_connection()) as conn,conn:
        hb_tasks.ensure_schema(conn)
        task=hb_tasks.get(conn,task_id)
        if not task:return jsonify(ok=False,error='Unknown task'),404
        result={}
        if data['state']=='active':
            from core.hb_chat_controls import held_requests
            if held_requests(conn,task):return jsonify(ok=False,error='Decide the approval on the linked request bubble before resuming'),409
            if task['state']=='completed':return jsonify(ok=False,error='Accepted tasks cannot be resumed'),409
            result=hb_tasks.resume_by_owner(conn,task)
        else:
            conn.execute('UPDATE hb_tasks SET state=?,updated_at=? WHERE task_id=?',(data['state'],time.time(),task_id))
        task=hb_tasks.get(conn,task_id)
        hb_tasks.event(conn,task,'user','task_state',{'state':data['state'],**result})
        pickups=[]
        for rid in result.get('queued',[]):
            target=conn.execute("SELECT p.recipient,COALESCE(w.state,'queued') FROM peer_messages p LEFT JOIN hb_peer_work w ON w.request_id=p.id WHERE p.id=?",(rid,)).fetchone()
            if not target:raise RuntimeError('Resumed request was not found')
            pickups.append((rid,target[0],target[1]))
    if data['state'] in {'paused','cancelled'}:
        from core.hb_executions import stop_held_executors
        stop_held_executors(task_id)
    hb_tasks.flush_memory()
    for rid,recipient,state in pickups:
        _publish(task['conversation_id'],recipient,state=state,peer=True,request_id=rid,stage='Owner resumed task; executor '+state)
    return jsonify(ok=True,task_id=task_id,state=data['state'],**result)


def _control_task(conn,task_id):
    from core import hb_tasks
    from core.hb_chat_controls import continuation
    task=hb_tasks.get(conn,task_id)
    if task is None:raise ValueError('Unknown task')
    return {**{key:task[key] for key in ('task_id','title','project_id','step_id','state','root_message_id','version')},
            'continuation':continuation(conn,task)}


@peer_bridge_bp.get('/api/peer/v1/projects/<project_id>/tasks')
@require_owner
def project_task_board(project_id,current_user=None):
    from contextlib import closing
    from core.hb_task_board import project_tasks
    try:
        with closing(get_connection()) as conn:
            result=project_tasks(conn,project_id,limit=int(request.args.get('limit','50')),offset=int(request.args.get('offset','0')))
        return jsonify(ok=True,**result)
    except LookupError as exc:return jsonify(ok=False,error=str(exc)),404
    except ValueError as exc:return jsonify(ok=False,error=str(exc)),400


def _owner_chat_stop(data,message,conversation_id,user):
    """Save an owner Stop without routing it through a model or creating work."""
    from contextlib import closing
    from core import hb_tasks,hb_task_manager
    from core.hb_chat_controls import continuation,set_continuation
    from core.hb_executions import stop_held_executors
    with closing(get_connection()) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        hb_tasks.ensure_schema(conn);hb_task_manager.ensure_schema(conn)
        if not conn.execute('SELECT 1 FROM conversations WHERE id=?',(conversation_id,)).fetchone():
            raise ValueError('Unknown conversation; no control was changed')
        if data.get('task_id'):
            task=hb_tasks.get(conn,data['task_id'])
            if not task:raise ValueError('Unknown task; no control was changed')
            if task['conversation_id']!=conversation_id:raise PermissionError('Selected task belongs to another chat')
            ids=[task['task_id']] if task['state'] not in {'completed','cancelled'} else []
        else:
            ids=[r[0] for r in conn.execute('''SELECT t.task_id FROM hb_tasks t
                WHERE t.conversation_id=? AND t.state NOT IN ('completed','cancelled') AND
                (EXISTS(SELECT 1 FROM hb_task_manager m WHERE m.task_id=t.task_id)
                 OR EXISTS(SELECT 1 FROM hb_task_requests r JOIN hb_peer_work w ON w.request_id=r.request_id
                           WHERE r.task_id=t.task_id AND w.state IN ('queued','running')))
                ORDER BY t.task_id''',(conversation_id,))]
        owner_mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'user','hummingbird',?,'owner_control',0)",(conversation_id,message)).lastrowid
        receipts=[]
        for task_id in ids:
            task=hb_tasks.get(conn,task_id)
            control=continuation(conn,task)
            result=set_continuation(conn,task,{'mode':'off','message_id':task['root_message_id'],
                'version':task['version'],'revision':control['revision'],
                'command_id':f'owner-chat-stop-{owner_mid}-{task_id}'},user['username'])
            hb_tasks.event(conn,task,'user','owner_chat_stop',{'owner_message_id':owner_mid,'receipt_id':result['receipt_id']},message_id=owner_mid)
            receipts.append(result)
        answer=(f'Stopped pickup for {len(ids)} task(s). Running peer workers are being interrupted; task records and receipts are preserved.'
                if ids else 'No unfinished queued or managed work in this chat. No new task was created.')
        reply=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",(conversation_id,answer)).lastrowid
    # The owner hold must commit before another connection inspects it.
    interrupted=[]
    for task_id in ids:interrupted.extend(stop_held_executors(task_id))
    hb_tasks.flush_memory()
    _publish(conversation_id,'hummingbird',state='control',peer=True)
    return jsonify(ok=True,state='ok',mode='control',conversation_id=conversation_id,
        operator_message_id=owner_mid,response=answer,responses=[{'agent':'hummingbird','response':answer,'message_id':reply}],
        pending_jobs=[],held_tasks=ids,control_receipts=receipts,interrupted=interrupted)


def maybe_owner_chat_control(data,message):
    """Owner main-chat statements use the same decision functions as buttons."""
    from contextlib import closing
    from urllib.parse import urlsplit
    from core import hb_tasks
    from core.hb_chat_controls import owner_text_decision,owner_text_stop,request_snapshot,set_request_approval,set_continuation,StaleControl
    explicit=data.get('approval_request_message_id')
    text=message
    if explicit and message.startswith('[Reply to '):
        text=data.get('approval_reply_text')
        if not isinstance(text,str) or not message.endswith('\n\n'+text):return None
    decision=owner_text_decision(text)
    stopping=owner_text_stop(text)
    if not (decision or stopping) or data.get('relay_from') or data.get('new_thread'):return None
    user=get_current_user()
    if not user or user.get('role')!='owner':return None
    try:conversation_id=int(data.get('conversation_id'))
    except (ValueError,TypeError):return None
    origin=request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site')=='cross-site' or origin and urlsplit(origin).netloc!=request.host:
        return jsonify(ok=False,error='Use the authenticated main chat for owner decisions'),403
    if stopping:
        try:return _owner_chat_stop(data,message,conversation_id,user)
        except ValueError as exc:return jsonify(ok=False,error=str(exc),response=str(exc)),409
        except PermissionError as exc:return jsonify(ok=False,error=str(exc),response=str(exc)),403
    import re
    named=re.search(r'\b(?:request|proposal)\s*#\s*(\d+)\b',text,re.I)
    if named:explicit=int(named[1])
    try:
        with closing(get_connection()) as conn,conn:
            conn.execute('BEGIN IMMEDIATE')
            task=hb_tasks.get(conn,data['task_id']) if data.get('task_id') else None
            if task and task['conversation_id']!=conversation_id:raise PermissionError('Selected task belongs to another chat')
            if not task and not explicit:
                latest=conn.execute("SELECT id FROM messages WHERE conversation_id=? AND from_agent='user' ORDER BY id DESC LIMIT 1",(conversation_id,)).fetchone()
                if latest:
                    recent=hb_tasks.for_message(conn,latest[0])
                    if recent and recent['state']!='completed':task=recent
            target=request_snapshot(conn,explicit) if type(explicit) is int else None
            if explicit and (not target or hb_tasks.get(conn,target['task_id'])['conversation_id']!=conversation_id):
                raise PermissionError('Selected approval bubble belongs to another chat or has no request')
            if target and task and target['task_id']!=task['task_id']:raise PermissionError('Selected bubble and task disagree')
            if not target:
                candidates=[]
                for (mid,) in conn.execute("SELECT DISTINCT p.message_id FROM peer_messages p JOIN hb_peer_routes r ON r.request_id=p.id WHERE p.conversation_id=? AND r.kind='work' ORDER BY p.message_id DESC LIMIT 100",(conversation_id,)):
                    candidate=request_snapshot(conn,mid)
                    if not candidate or task and candidate['task_id']!=task['task_id']:continue
                    if candidate['decision'] in {'needs_review','declined'} or any(a['state'] in {'queued','running','failed','needs_review'} for a in candidate['attempts']):candidates.append(candidate)
                if len(candidates)==1:target=candidates[0]
                elif len(candidates)>1:
                    return jsonify(ok=True,state='ok',mode='control',conversation_id=conversation_id,
                        response='Choose the specific request bubble for this decision: '+', '.join('#'+str(c['message_id']) for c in candidates)+'. No request was changed.'),200
            if target:task=hb_tasks.get(conn,target['task_id'])
            if not target and (not task or decision!='approved'):return None
            owner_mid=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'user','hummingbird',?,'chat',0)",(conversation_id,message)).lastrowid
            constrained=bool(re.search(r"\b(?:but|except|only|without|don't|do not)\b",text,re.I))
            hb_tasks.bind(conn,conversation_id,owner_mid,task_id=task['task_id'],parent_message_id=target['message_id'] if target else task['root_message_id'],kind='instruction' if constrained else 'approval')
            task=hb_tasks.get(conn,task['task_id'])
            if target:target=request_snapshot(conn,target['message_id'])
            if target:
                payload={'decision':decision,'message_id':target['message_id'],'version':task['version'],
                    'revision':target['revision'],'scope_hash':target['scope_hash'],'command_id':'owner-chat-'+str(owner_mid)+'-request'}
                result=set_request_approval(conn,task,payload,user['username'],owner_message_id=owner_mid)
            else:
                control=_control_task(conn,task['task_id'])
                payload={'mode':'on','message_id':task['root_message_id'],'version':task['version'],
                    'revision':control['continuation']['revision'],'command_id':'owner-chat-'+str(owner_mid)+'-continue'}
                result=set_continuation(conn,task,payload,user['username'])
            saved=_control_task(conn,task['task_id'])
            answer=('Approved' if decision=='approved' else decision.replace('_',' ').capitalize())+' · '+saved['continuation']['status']+'.'
            if result.get('queued'):answer+=' Executor request(s): '+', '.join(map(str,result['queued']))+'.'
            if result.get('already_executed'):answer+=' Previous successful work was preserved; no duplicate was queued.'
            reply=conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (?,'hummingbird','user',?,'response',0)",(conversation_id,answer)).lastrowid
            hb_tasks.bind(conn,conversation_id,reply,task_id=task['task_id'],parent_message_id=owner_mid,kind='reply')
            hb_tasks.event(conn,task,'user','owner_chat_decision',{'decision':decision,'owner_message_id':owner_mid,'request_message_id':target['message_id'] if target else None,'receipt_id':result['receipt_id']},message_id=owner_mid)
        if decision in {'declined','needs_review'}:
            from core.hb_executions import stop_held_executors
            stop_held_executors(task['task_id'])
        hb_tasks.flush_memory()
        _publish(conversation_id,'hummingbird',state='control',peer=True,task_id=task['task_id'])
        return jsonify(ok=True,state='ok',mode='control',conversation_id=conversation_id,task=saved,
            operator_message_id=owner_mid,response=answer,responses=[{'agent':'hummingbird','response':answer,'message_id':reply,'task':saved}],pending_jobs=[],control_receipt=result)
    except (StaleControl,ValueError) as exc:return jsonify(ok=False,error=str(exc),response=str(exc)),409
    except PermissionError as exc:return jsonify(ok=False,error=str(exc),response=str(exc)),403


@peer_bridge_bp.route('/api/peer/v1/tasks/<task_id>/control',methods=['GET','POST'])
@require_owner
def task_control(task_id,current_user=None):
    from contextlib import closing
    from urllib.parse import urlsplit
    from core import hb_tasks
    from core.hb_chat_controls import set_continuation,StaleControl
    if request.method=='POST':
        origin=request.headers.get('Origin')
        if (request.headers.get('Sec-Fetch-Site')=='cross-site'
                or origin and urlsplit(origin).netloc!=request.host):
            return jsonify(ok=False,error='Use the authenticated HB chat to change this control'),403
        if not request.is_json:return jsonify(ok=False,error='JSON control decision required'),400
    try:
        with closing(get_connection()) as conn,conn:
            if request.method=='POST':conn.execute('BEGIN IMMEDIATE')
            task=hb_tasks.get(conn,task_id)
            if not task:return jsonify(ok=False,error='Unknown task'),404
            result=set_continuation(conn,task,request.get_json(silent=True) or {},current_user['username']) if request.method=='POST' else {}
            snapshot=_control_task(conn,task_id)
        if request.method=='POST':
            from core.hb_executions import stop_held_executors
            stop_held_executors(task_id)
            hb_tasks.flush_memory()
            _publish(task['conversation_id'],'hummingbird',state='control',peer=True,task_id=task_id)
        return jsonify(ok=True,task=snapshot,**result)
    except StaleControl as exc:
        return jsonify(ok=False,error=str(exc)),409
    except PermissionError as exc:
        return jsonify(ok=False,error=str(exc)),403
    except (ValueError,TypeError) as exc:
        return jsonify(ok=False,error=str(exc)),400


@peer_bridge_bp.route('/api/peer/v1/tasks/<task_id>/requests/<int:message_id>/approval',methods=['GET','POST'])
@require_owner
def request_approval_control(task_id,message_id,current_user=None):
    from contextlib import closing
    from urllib.parse import urlsplit
    from core import hb_tasks
    from core.hb_chat_controls import request_snapshot,set_request_approval,StaleControl
    if request.method=='POST':
        origin=request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site')=='cross-site' or origin and urlsplit(origin).netloc!=request.host:
            return jsonify(ok=False,error='Use the authenticated HB chat to decide this request'),403
        if not request.is_json:return jsonify(ok=False,error='JSON approval decision required'),400
    try:
        with closing(get_connection()) as conn,conn:
            if request.method=='POST':conn.execute('BEGIN IMMEDIATE')
            task=hb_tasks.get(conn,task_id)
            snapshot=request_snapshot(conn,message_id)
            if not task or not snapshot or snapshot['task_id']!=task_id:
                return jsonify(ok=False,error='Request bubble is not linked to this task'),404
            result={}
            if request.method=='POST':
                data=request.get_json(silent=True) or {}
                if data.get('message_id')!=message_id:return jsonify(ok=False,error='Decision belongs to another bubble'),403
                result=set_request_approval(conn,task,data,current_user['username'])
            snapshot=request_snapshot(conn,message_id)
            task_snapshot=_control_task(conn,task_id)
        if request.method=='POST':
            from core.hb_executions import stop_held_executors
            stop_held_executors(task_id)
            hb_tasks.flush_memory()
            _publish(task['conversation_id'],'hummingbird',state='control',peer=True,task_id=task_id,message_id=message_id)
        return jsonify(ok=True,task=task_snapshot,request_control=snapshot,**result)
    except StaleControl as exc:
        return jsonify(ok=False,error=str(exc)),409
    except PermissionError as exc:
        return jsonify(ok=False,error=str(exc)),403
    except (ValueError,TypeError) as exc:
        return jsonify(ok=False,error=str(exc)),400
