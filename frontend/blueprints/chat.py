import json
"""chat.py — Chat Engine routes

LINKED TO:
  frontend/services.py      — imports everything via `from services import *`.
                              _AGENT_ROSTER, _CHAT_AGENT_ETA_SECONDS, and
                              _alm_gate_or_response all live there.
  utils/config.py           — agent system prompts loaded dynamically in
                              _run_ghost_layer_chat() via <NAME>_SYSTEM_PROMPT.
  utils/db/_schema.py       — _get_ghost_agent_names() queries agents table
                              for tier IN ('paid','free'). If an agent's tier
                              is wrong in the DB the ALM gate will mis-fire.
  frontend/blueprints/proposals.py — ALM gate creates/checks work_proposals;
                              developer_agents set here must match that file.
"""
import os
import json
import logging
import re
import subprocess
import threading
import time
import urllib.request

from flask import Blueprint, request, Response, jsonify, send_file, g
from services import *
from database import log_ghost_circle
from utils.db.registry import get_agent_roster as _reg_roster, get_single_task_locals as _reg_stl
from utils.db.chat import (
    ensure_chat_relay_recovery,
    ensure_silent_chat_thread_recovery,
    get_open_chat_relay_recoveries,
    update_chat_relay_recovery_status,
)
from utils.db.timeline import timeline_append as _trace
from utils.worker import is_worker_agent
from utils.thread_memory import (
    _HAT_AGENTS as _THREAD_HATS,
    carry_over_block as _carry_over_block,
    record_exchange as _record_exchange,
    run_in_conversation as _run_in_conversation,
    update_thread_state as _update_thread_state,
)
from utils.chat_prompt_profiles import (
    apply_local_chat_profile,
    audit_prefix as _chat_audit_prefix,
    chat_handoff_contract,
    read_only_guard as _chat_read_only_guard,
)
try:
    from utils.circuit_breaker import check as _cb_check, record_success as _cb_ok, record_failure as _cb_fail, health_probe as _cb_probe
    _CB_AVAILABLE = True
except ImportError:
    _CB_AVAILABLE = False


def _sse_module():
    """Resolve the SSE module instance whose blueprint the running app registered.

    terminal.py registers `blueprints.sse` (frontend/ on sys.path) while tests
    import `frontend.blueprints.sse`; those are distinct module objects with
    separate subscriber lists, so publishing to the wrong one reaches nobody.
    """
    import importlib
    import sys

    try:
        from flask import current_app
        registered = current_app.blueprints.get('sse')
    except Exception:
        registered = None
    if registered is not None:
        mod = sys.modules.get(registered.import_name)
        if mod is not None and hasattr(mod, 'publish_chat_update'):
            return mod
    for name in ('blueprints.sse', 'frontend.blueprints.sse'):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, 'publish_chat_update'):
            return mod
    return importlib.import_module('frontend.blueprints.sse')


def _sse_chat(conversation_id, agent, status, **extra):
    """Lazy SSE publish to avoid cross-blueprint import at module load."""
    try:
        if agent == "apex":
            extra.setdefault("runtime_class", "local")
        _sse_module().publish_chat_update(conversation_id, agent, status, **extra)
    except Exception:
        _LOG.exception('Failed to publish chat SSE update for conversation %s', conversation_id)

chat_bp = Blueprint('chat', __name__)


@chat_bp.teardown_request
def release_inline_execution(error=None):
    key=getattr(g,'hb_inline_execution',None)
    if key:
        from contextlib import closing
        from core.hb_executions import release
        with closing(get_connection()) as conn,conn:
            release(conn,key,'failed' if error else 'completed')
        g.hb_inline_execution=None
from core.apex_turn_queue import TurnQueue as _TurnQueue
_APEX_TURNS = _TurnQueue()
APEX_QUEUE_SECONDS = 1260  # one pending approval (900 s) plus one full turn (360 s)
_LOG = logging.getLogger('fridays.chat')


def _dispatch_apex_peers(conv_id, agent_name, response_text):
    """Hand strict APEX [DISPATCH: @peer] lines to the Hummingbird peer queue."""
    from core import peer_bridge as peers
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT MAX(id) FROM messages WHERE conversation_id=? AND from_agent=?",
            (conv_id, agent_name),
        ).fetchone()
        result = peers.dispatch_from_agent(conn, conv_id, row[0] if row else None,
                                           agent_name, response_text)
        conn.commit()
        if result.get('queued') or result.get('locked'):
            _LOG.info('APEX peer dispatch for conversation %s: %s', conv_id, result)
        return result
    except Exception:
        _LOG.exception('APEX peer dispatch failed for conversation %s', conv_id)
        return None
    finally:
        if conn is not None:
            conn.close()


def _share_apex_exchange(conv_id, operator_message_id, message, answer, receipts, addressed):
    """Copy a committed APEX turn only to peers explicitly addressed by the owner."""
    from core import peer_bridge as peers
    operator = _tool_operator()
    if not operator:
        return None
    conn = None
    try:
        conn = get_connection()
        queued = peers.share_exchange(conn, conv_id, operator_message_id, message, 'apex', answer,
                                      receipts=receipts or (), addressed=addressed or (),
                                      sender=operator[0])
        conn.commit()
        return queued
    except Exception:
        _LOG.exception('APEX team copy failed for conversation %s', conv_id)
        return None
    finally:
        if conn is not None:
            conn.close()


def _tool_operator():
    """No body identity, proxy, network-origin or agent-key authentication fallback."""
    from core.tool_approval import session_identity
    if request.headers.get('X-Agent-Key') or request.headers.get('X-Agent-Id'):
        return None
    user = get_current_user()
    token = request.cookies.get('friday_session', '')
    if not user or user['role'] != 'owner' or not token:
        return None
    return user['username'], session_identity(token)


def _owner_package_command(message):
    """Run a literal owner-pasted Hummingbird package command from main chat."""
    import hashlib, shlex, subprocess, uuid
    from pathlib import Path
    from urllib.parse import urlsplit
    from core import agent_identity
    from utils.db.chat import new_conversation, log_message

    operator=_tool_operator()
    if not operator:return jsonify({'ok':False,'response':'An authenticated owner session is required to run a package command.'}),401
    owner,_=operator
    payload=request.get_json(silent=True) or {}
    if payload.get('relay_from'):
        return jsonify({'ok':False,'response':'Package commands must be typed directly by the owner, not relayed by an agent.'}),403
    origin=request.headers.get('Origin','')
    if not origin or (urlsplit(origin).scheme,urlsplit(origin).netloc)!=(request.scheme,request.host):
        return jsonify({'ok':False,'response':'Package commands must come from the authenticated same-origin HB chat.'}),403
    try:
        if not isinstance(message,str) or len(message)>512 or any(ord(c)<32 for c in message):
            raise ValueError('Paste one complete bash command on a single line.')
        parts=shlex.split(message)
        if len(parts)!=2 or parts[0]!='bash':
            raise ValueError('Main chat runs only a single bash package-script command, without arguments or shell composition.')
        script=Path(parts[1])
        if (not script.is_absolute() or script.name not in {'activate.sh','deactivate.sh','rollback.sh'}
                or not script.parent.name.startswith('Hummingbird-')
                or script.parent.parent!=Path('/home/jd')
                or script.is_symlink() or script.parent.is_symlink()
                or not script.is_file() or not (script.parent/'README.md').is_file()
                or (script.parent/'README.md').is_symlink()):
            raise ValueError('The script must be activate.sh, deactivate.sh or rollback.sh in a reviewed /home/jd/Hummingbird-* package.')
        info=script.stat();directory=script.parent.stat()
        if (info.st_uid!=os.getuid() or directory.st_uid!=os.getuid()
                or info.st_gid!=os.getgid() or directory.st_gid!=os.getgid()
                or info.st_mode&0o002 or directory.st_mode&0o002 or info.st_size>128*1024):
            raise ValueError('Package command ownership or file permissions failed the host check.')
    except (ValueError,OSError) as exc:
        return jsonify({'ok':False,'response':'Package command not run: '+str(exc)}),400

    data=payload
    conv_id=None
    try:
        requested=int(data.get('conversation_id')) if data.get('conversation_id') is not None else 0
    except (TypeError,ValueError):requested=0
    if requested>0:
        from contextlib import closing
        from utils.db._connection import get_connection
        with closing(get_connection()) as conn:
            if conn.execute('SELECT 1 FROM conversations WHERE id=?',(requested,)).fetchone():conv_id=requested
    if conv_id is None:
        env=os.environ.get('SWARM_ENV','prod').upper()
        conv_id=new_conversation('HB command: '+script.name,source='terminal-ui:'+env,sender=owner)
    log_message(conv_id,'user',message,to_agent='fridays',message_type='chat')
    action_id=uuid.uuid4().hex
    _sse_chat(conv_id,'fridays','running',action_id=action_id,stage='Running the owner-pasted Hummingbird package command')
    outcome='failed';exit_code=-1;output='';error=''
    try:
        with agent_identity.execution('fridays',requested_by=owner,conversation_id=conv_id) as actor:
            agent_identity.event(actor,action_id,'owner_package_command','started',result={'script':script.name,'command_sha256':hashlib.sha256(message.encode()).hexdigest()})
            _sse_chat(conv_id,'fridays','running',owner_command=True,action_id=action_id,stage='Starting '+script.name)
            run_env=os.environ.copy()
            runtime_dir='/run/user/'+str(os.getuid())
            if Path(runtime_dir).is_dir():
                run_env.setdefault('XDG_RUNTIME_DIR',runtime_dir)
                bus=Path(runtime_dir)/'bus'
                if bus.exists():run_env.setdefault('DBUS_SESSION_BUS_ADDRESS','unix:path='+str(bus))
            try:
                result=subprocess.run(['/bin/bash',str(script)],cwd='/home/jd',env=run_env,
                    capture_output=True,text=True,errors='replace',timeout=300,start_new_session=True)
                exit_code=result.returncode
                output=(result.stdout or '')+(('\n'+result.stderr) if result.stderr else '')
                outcome='succeeded' if exit_code==0 else 'failed'
            except subprocess.TimeoutExpired as exc:
                stdout=exc.stdout.decode(errors='replace') if isinstance(exc.stdout,bytes) else (exc.stdout or '')
                stderr=exc.stderr.decode(errors='replace') if isinstance(exc.stderr,bytes) else (exc.stderr or '')
                output=stdout+(('\n'+stderr) if stderr else '')+'\nCommand exceeded the 300-second limit.'
                error='timeout';outcome='failed'
            except Exception as exc:
                output='Command launcher failed: '+type(exc).__name__;error=type(exc).__name__;outcome='failed'
            output=output[-16000:].strip()
            agent_identity.event(actor,action_id,'owner_package_command',outcome,
                result={'script':script.name,'exit_code':exit_code,'output_sha256':hashlib.sha256(output.encode()).hexdigest(),'error_type':error or None})
    except Exception as exc:
        output='HB could not run the package command: '+type(exc).__name__
        outcome='failed'
    summary=('HB package command completed' if outcome=='succeeded' else 'HB package command failed')+f' (exit code {exit_code}).'
    response=summary+(('\n\n'+output) if output else '')
    log_message(conv_id,'fridays',response,to_agent='user',message_type='response')
    _sse_chat(conv_id,'fridays','completed' if outcome=='succeeded' else 'failed',owner_command=True,action_id=action_id,exit_code=exit_code)
    return jsonify({'ok':True,'state':'ok','mode':'owner_package_command','agent':'fridays','model':'host-package-runner',
        'response':response,'tokens':0,'responses':[{'agent':'fridays','response':response,'tokens':0,'pending':False,'job_id':None}],
        'pending_jobs':[],'conversation_id':conv_id,'command_status':outcome,'exit_code':exit_code})


def _is_owner_package_command(message):
    return isinstance(message,str) and message.lstrip().startswith('bash /home/jd/Hummingbird-')


@chat_bp.route('/api/chat/hf-mirror/status', methods=['GET'])
@chat_bp.route('/api/chat/hf-mirror/control', methods=['POST'])
def api_hf_mirror_control():
    """Owner-only main-chat control for the resumable Hub mirror."""
    from urllib.parse import urlsplit
    from core import agent_identity
    from core import hf_mirror
    import uuid
    operator=_tool_operator()
    if not operator:return jsonify({'ok':False,'error':'Authenticated owner session required'}),401
    owner,_=operator
    if request.method=='POST':
        origin=request.headers.get('Origin','')
        if not origin or (urlsplit(origin).scheme,urlsplit(origin).netloc)!=(request.scheme,request.host):
            return jsonify({'ok':False,'error':'Same-origin owner action required'}),403
        if request.headers.get('X-HB-Owner-Action')!='1':
            return jsonify({'ok':False,'error':'Owner action header required'}),403
        body=request.get_json(silent=True)
        if not isinstance(body,dict) or body.get('action') not in {'pause','resume','curate','include'}:
            return jsonify({'ok':False,'error':'Choose pause, resume, curate or include'}),400
        action=body['action']
        if set(body)!={'action','repo'} and set(body)!={'action'}:
            return jsonify({'ok':False,'error':'Unexpected control fields'}),400
        if action=='include' and (not isinstance(body.get('repo'),str) or len(body['repo'])>200):
            return jsonify({'ok':False,'error':'include requires one public Hub repository ID'}),400
        try:
            with agent_identity.execution('fridays',requested_by=owner,conversation_id=2833) as actor:
                action_id=uuid.uuid4().hex
                agent_identity.event(actor,action_id,'hf_mirror.'+action,'started',
                    result={'repo':body.get('repo')})
                if action in {'curate','include'}:
                    repos=hf_mirror.acquisition_policy().get('explicit_repositories',[])
                    if action=='include':repos.append(body['repo'])
                    result=hf_mirror.set_acquisition_policy('curated',repos)
                elif action=='pause':result=hf_mirror.pause(True)
                else:result=hf_mirror.pause(False)
                agent_identity.event(actor,action_id,'hf_mirror.'+action,'succeeded',
                    result={'policy':result.get('acquisition_policy'),'pause_requested':result.get('pause_requested',action=='pause')})
                result['action_id']=action_id
        except (PermissionError,ValueError) as exc:return jsonify({'ok':False,'error':str(exc)}),400
        result['mirror']=hf_mirror.status()
        result['message']=('Current file may finish; the mirror will pause at its next file boundary.' if action in {'pause','curate','include'} else
            'Mirror resumed under its selected policy. Existing verified files and checkpoints are retained.')
        return jsonify({'ok':True,**result})
    result=hf_mirror.status()
    response=jsonify({'ok':True,'mirror':result,'observed_at':result.get('observed_at')})
    response.headers['Cache-Control']='no-store'
    return response


@chat_bp.route('/api/tool-approval', methods=['GET', 'POST'])
def api_tool_approval():
    from core.tool_approval import APPROVALS, ApprovalConflict
    from sqlite3 import DatabaseError
    try:
        operator = _tool_operator()
        if not operator:
            return jsonify({'ok': False, 'error': 'Authenticated owner session required'}), 401
        owner, session_id = operator
        if request.method == 'GET':
            response = jsonify({'ok': True, 'pending': APPROVALS.list_for(owner, session_id)})
            response.headers['Cache-Control'] = 'no-store'
            return response
        data = request.get_json(silent=True)
        if (not isinstance(data, dict) or set(data) != {'transaction_id', 'decision'}
                or not isinstance(data['transaction_id'], str) or type(data['decision']) is not bool):
            return jsonify({'ok': False, 'error': 'UUID and boolean decision required'}), 400
        import uuid
        try:
            if str(uuid.UUID(data['transaction_id'])) != data['transaction_id']:
                raise ValueError
        except ValueError:
            return jsonify({'ok': False, 'error': 'Canonical transaction UUID required'}), 400
        # Same-origin JSON plus a per-transaction secret fetched by the owning session.
        from urllib.parse import urlsplit
        origin = request.headers.get('Origin', '')
        if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (
                request.scheme, request.host):
            return jsonify({'ok': False, 'error': 'Cross-origin approval refused'}), 403

        def authorize(tool):
            permission = 'fs_write' if tool in {'propose_write_file', 'propose_patch'} else 'git_commit'
            return can_user_invoke_skill(owner, permission, default_allow=True)

        result = APPROVALS.decide(
            data['transaction_id'], data['decision'], owner, session_id,
            request.headers.get('X-Tool-Approval-CSRF', ''), authorize)
        return jsonify({'ok': result['status'] != 'failed', 'receipt': result}), (
            409 if result['status'] == 'failed' else 200)
    except PermissionError as exc:
        _LOG.warning('Tool approval refused: %s', exc)
        return jsonify({'ok': False, 'error': str(exc)}), 403
    except ApprovalConflict as exc:
        _LOG.warning('Tool approval conflict: %s', exc)
        return jsonify({'ok': False, 'error': str(exc)}), 409
    except DatabaseError:
        _LOG.exception('Tool approval authentication storage unavailable')
        return jsonify({'ok': False, 'error': 'Approval authentication unavailable'}), 503

def _chat_execution_breakdown(receipts, runtime_nudges):
    counts = {
        status: sum(1 for receipt in receipts if receipt.get('status') == status)
        for status in ('succeeded', 'failed', 'denied', 'skipped')
    }
    return (
        '\n\n### Execution and teaching evidence\n'
        f'- Local tool receipts: {counts["succeeded"]} succeeded, '
        f'{counts["failed"]} failed, {counts["denied"]} denied, '
        f'{counts["skipped"]} skipped.\n'
        f'- Runtime guidance prompts: {runtime_nudges} (not instructor teaching).\n'
        '- Instructor teaching: no teaching recorded for this turn.\n'
        '- Independent contribution: not measured; tool counts are not an autonomy percentage.\n'
        '- Verification: these counts confirm tool outcomes only, not that the whole task succeeded.'
    )


def _record_vortex_action(action_type, *, source_agent='', target_agent='', status='recorded',
                          context_parts=(), thread_id=None, details=None, source='fridays.execution'):
    try:
        from core.vortex_ledger import record_action
        return record_action(
            action_type,
            source_agent=source_agent,
            target_agent=target_agent,
            status=status,
            context_parts=tuple(context_parts),
            thread_id=str(thread_id) if thread_id else None,
            details=details,
            source=source,
        )
    except Exception:
        _LOG.exception('Could not record Vortex action %s', action_type)
        return False

_CHAT_LOCAL_HANDOFF_DEADLINE_SECONDS = 2000
_CHAT_RECONCILE_SCHEDULE_LOCK = threading.Lock()
_CHAT_RECONCILE_LAST_TS = 0.0
_CHAT_RECONCILE_MIN_INTERVAL_SECONDS = 5.0


def _chat_local_handoff_deadline_seconds():
    """Runtime-configurable local handoff deadline, defaulting to 2000s."""
    try:
        return max(5, int(os.environ.get('SWARM_CHAT_HANDOFF_DEADLINE_SECONDS') or _CHAT_LOCAL_HANDOFF_DEADLINE_SECONDS))
    except Exception:
        return _CHAT_LOCAL_HANDOFF_DEADLINE_SECONDS


def _chat_agent_timeout_seconds(agent_name, persistent_mode=False):
    """User-visible completion/handoff deadline for chat agent calls."""
    agent = str(agent_name or '').strip().lower()
    if persistent_mode:
        if agent in {
            'gemma', 'llama', 'llama3', 'mistral', 'qwen', 'eight', 'seven', 'fred',
            'twenty', 'librarian', 'duck', 'sniffles', 'phi3',
            'deepseek_local', 'deepseek-local', 'lmstudio'
        }:
            return _chat_local_handoff_deadline_seconds()
        return 240
    if agent == 'sniffles':
        return 35
    if agent == 'duck':
        return 18
    if agent in {'llama', 'llama3'}:
        return 90
    if agent in {'phi3'}:
        return 60
    if agent in {'deepseek_local', 'deepseek-local', 'lmstudio', 'ghost_coder'}:
        return 120
    return 12


def _chat_handoff_contract(agent_name, deadline_seconds):
    return chat_handoff_contract(agent_name, deadline_seconds)


def _looks_like_token_exhaustion(text):
    lower = str(text or '').lower()
    cues = (
        'context length',
        'maximum context',
        'max context',
        'context window',
        'token limit',
        'tokens exceeded',
        'out of tokens',
        'maximum tokens',
        'input is too long',
        'prompt is too long',
        'num_ctx',
    )
    return any(cue in lower for cue in cues)


def _chat_response_is_unusable(agent_name, response_text):
    raw = str(response_text or '').strip()
    if not raw:
        return True
    lower = raw.lower()
    agent = _normalize_chat_participant(agent_name)
    placeholders = {
        f'[{agent} unavailable]' if agent else '',
        f'[{agent}] no response' if agent else '',
        f'[{agent}] unavailable' if agent else '',
        '[agent unavailable]',
        '[agent] no response',
    }
    if lower in placeholders:
        return True
    if 'no response' in lower and 'check server logs' in lower and lower.startswith('['):
        return True
    if lower.endswith('no response') and lower.startswith('['):
        return True
    if 'unavailable' in lower and lower.startswith('[') and len(lower) <= 80:
        return True
    if 'my model is offline right now' in lower and 'state read only' in lower:
        return True
    return False


def _chat_response_echoes_prompt(prompt_text, response_text):
    import re
    prompt_norm = re.sub(r'\W+', ' ', str(prompt_text or '').lower()).strip()
    response_norm = re.sub(r'\W+', ' ', str(response_text or '').lower()).strip()
    if not prompt_norm or not response_norm:
        return False
    if response_norm == prompt_norm:
        return True
    response_words = response_norm.split()
    # "QWEN -> USER: CORRECT. ..." picks one of the options the prompt offered;
    # reusing the prompt's words is then the answer, not an echo.
    body = re.sub(r'^\w+\s*->\s*\w+\s*:\s*', '', str(response_text or '').strip())
    body_words = re.sub(r'\W+', ' ', body.lower()).split()
    if body_words and body_words[0] in {
        'correct', 'incorrect', 'approve', 'approved', 'reject', 'rejected', 'yes', 'no',
        'pass', 'fail', 'true', 'false', 'agree', 'disagree',
    } and body_words[0] in prompt_norm.split():
        return False
    # Short answers may legitimately reuse a couple of prompt words; only a
    # substantial reply can be a real echo.
    if len(response_words) >= 5 and len(response_norm) <= len(prompt_norm) + 12 and (
        response_norm in prompt_norm or prompt_norm in response_norm
    ):
        return True
    prompt_words = set(prompt_norm.split())
    if 5 <= len(response_words) <= 24:
        if any(word not in prompt_words and any(c.isdigit() for c in word) for word in response_words):
            return False
        overlap = sum(1 for word in response_words if word in prompt_words)
        if overlap / len(response_words) >= 0.8:
            return True
    return False


def _chat_response_is_timeout_handoff(response_text, tokens_used=0):
    raw = str(response_text or '').strip()
    if not raw:
        return False
    if int(tokens_used or 0) != 0:
        return False
    lower = raw.lower()
    return 'self-handoff:' in lower and 'handoff deadline' in lower


def _chat_extract_explicit_agent_mentions(text, allowed_agents=None):
    """Return routable agents explicitly named in the user's message."""
    raw = str(text or '')
    if not raw.strip():
        return []
    allowed = {str(a or '').strip().lower() for a in (allowed_agents or []) if str(a or '').strip()}
    labels = {}
    try:
        labels = _get_agent_labels()
    except Exception:
        labels = {}
    matches = []
    for agent in sorted(allowed):
        names = {agent}
        label = str(labels.get(agent) or '').strip().lower()
        if label:
            names.add(label)
            names.add(label.split()[0])
        for name in sorted(names, key=len, reverse=True):
            if not name or len(name) < 3:
                continue
            pattern = r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])'
            if re.search(pattern, raw, flags=re.IGNORECASE):
                matches.append(agent)
                break
    return matches


WEB_LOOKUP_AGENTS = frozenset({'gemma', 'qwen', 'llama', 'mistral'})


def _chat_followup_agents(conversation_id, allowed_agents):
    """Continue with the last agent speaking to the user, not the default agent."""
    try:
        conv_id = int(conversation_id)
    except (TypeError, ValueError):
        return []
    if conv_id <= 0:
        return []
    for row in reversed(_fetch_chat_thread_rows(conv_id, limit=30)):
        sender = str(row.get('from_agent') or '').strip().lower()
        targets = [name.strip().lower() for name in str(row.get('to_agent') or '').split(',')]
        if sender in allowed_agents and 'user' in targets:
            return [sender]
        if sender == 'user':
            return [name for name in targets if name in allowed_agents]
    return []


def _with_live_web_context(prompt, message, stage=None, eta=None):
    """Prepend live search results when the user's message needs outside facts."""
    try:
        from lib.search.internet import needs_web_lookup, web_context_block
        from utils.local_runtime_policy import is_explicitly_no_tools_request
        if not needs_web_lookup(message) or is_explicitly_no_tools_request(message):
            return prompt
        if stage:
            stage('searching web · Serper/Tavily', eta)
        block = web_context_block(message)
    except Exception:
        _LOG.exception('Live web lookup failed')
        return prompt
    return f'{block}\n\n{prompt}' if block else prompt


def _chat_user_prompt_is_informational(text):
    """True when a prompt asks for status/explanation rather than system changes."""
    raw = str(text or '').strip().lower()
    if not raw:
        return False
    action_patterns = (
        r'\bfix\b',
        r'\bbuild\b',
        r'\bimplement\b',
        r'\bchange\b',
        r'\bmodify\b',
        r'\bpatch\b',
        r'\bwrite\b',
        r'\b(?:fs|file)_(?:write|patch|patch_lines)\b',
        r'\b(?:rewrite|restore|save|overwrite|append|edit)\b',
        r'\bcreate\b',
        r'\bdelete\b',
        r'\badd\b',
        r'\bremove\b',
        r'\bteach\b',
        r'\b(?:close|skip|skipped|mark|claim|studio_step_update|alm_close_proposals|alm_purge_proposals|purge)\b',
        r'\bclean(?:\s|-)?(?:up|slate)\b',
        r'\bmake changes?\b',
        r'\bupdate (the )?(file|code|function|system|watchdog|duck|agent|agents)\b',
    )
    if any(re.search(pattern, raw) for pattern in action_patterns):
        return False
    info_patterns = (
        r'\bstatus update\b',
        r'\bgive me (a )?status\b',
        r'\bcurrent status\b',
        r'\bwhat is\b',
        r'\bwhat are\b',
        r'\bshow me\b',
        r'\btell me\b',
        r'\bhow many\b',
        r'\bwhy\b',
        r'\bexplain\b',
        r'\bsummar(y|ize)\b',
    )
    return any(re.search(pattern, raw) for pattern in info_patterns)


def _chat_prompt_needs_clarification(text):
    raw = str(text or '').strip().lower()
    if not raw:
        return True
    compact = re.sub(r'\s+', ' ', raw)
    vague = {
        'help',
        'status',
        'status update',
        'continue',
        'fix it',
        'do it',
        'go',
        'what now',
        'look at it',
    }
    return compact in vague


def _disable_agent_for_chat(agent_name, reason):
    """Take an agent out of chat routing until re-enabled from Agents tile."""
    name = str(agent_name or '').strip().lower()
    if not name or name in {'ghost', 'user', 'fridays'}:
        return False
    try:
        conn = get_connection()
        try:
            row = conn.execute("SELECT tier FROM agents WHERE name=?", (name,)).fetchone()
            if not row:
                return False
            if (row['tier'] or '') == 'service':
                return False
            conn.execute("UPDATE agents SET enabled=0 WHERE name=?", (name,))
            conn.commit()
        finally:
            conn.close()
        try:
            DISABLED_AGENTS.add(name)
        except Exception:
            pass
        try:
            from utils.db.registry import invalidate_cache as _inv
            _inv()
        except Exception:
            pass
        try:
            log_activity('terminal', 'agent_auto_offline', f'{name}: {str(reason or "")[:500]}')
        except Exception:
            pass
        return True
    except Exception:
        return False


def _chat_error_should_disable_agent(text):
    raw = str(text or '').strip().lower()
    if not raw:
        return False
    first_line = raw.splitlines()[0][:300]
    local_runtime_error = first_line.startswith('[local runtime error:')
    agent_runtime_error = re.match(
        r'^\[(?:gemma|llama|qwen|mistral|nine|ten|eleven|twelve|thirteen|gemini|ghost_coder)\]\s*'
        r'(?:error:|(?:groq|github|anthropic|openai|huggingface|gemini|google)\b.*'
        r'(?:access denied|token rejected|api key rejected|unauthorized))',
        first_line,
        flags=re.IGNORECASE,
    ) is not None
    if not (local_runtime_error or agent_runtime_error):
        return False
    auth_cues = (
        '401',
        '403',
        'unauthorized',
        'access denied',
        'network settings',
        'bad credentials',
        'invalid api key',
        'missing api key',
        'authentication',
        'api key rejected',
        'token rejected',
    )
    return any(cue in raw for cue in auth_cues) or _looks_like_token_exhaustion(raw)


# Ollama-agent helpers live in services.chat_agents and are re-exported through
# services/__init__.py. Names available here via `from services import *`:
#   _local_ollama_chat_agents, _chat_model_aliases,
#   _chat_agent_configured_model, _chat_running_ollama_models.
_registry_chat_runtime_class = _chat_runtime_class


def _chat_runtime_class(agent):
    """Classify chat runtime, falling back to Ollama model config if registry is unavailable."""
    normalized = _normalize_chat_participant(agent)
    try:
        runtime = str(_registry_chat_runtime_class(normalized) or '').strip().lower()
    except Exception:
        runtime = ''
    if runtime and runtime != 'unknown':
        return runtime

    try:
        if normalized and normalized in _all_local_ollama_chat_agents():
            return 'local'
    except Exception:
        pass

    model = ''
    try:
        model = str(_chat_agent_configured_model(normalized) or '').strip().lower()
    except Exception:
        model = ''
    if model and model not in {'external', 'local-algorithm'} and not model.startswith('seven-direct:'):
        return 'local'
    return runtime or 'unknown'

# Watchdog circuit breaker: per-model kill state to prevent infinite noisy
# retries when `ollama stop` fails and the runner process is orphaned.
# escalation_level: 0=initial, 1=ollama-cli, 2=kill-9, 3=ticket-emitted
_WATCHDOG_KILL_STATE: "dict[str, dict]" = {}
_WATCHDOG_KILL_LOCK = threading.Lock()
_WATCHDOG_MAX_FAILS_BEFORE_KILL9 = 3
_WATCHDOG_MAX_FAILS_BEFORE_TICKET = 5
_WATCHDOG_BACKOFF_BASE_SECONDS = 5


def _normalize_human_alias(value):
    raw = str(value or '').strip().lower()
    if not raw:
        return ''
    alias = re.sub(r'[^a-z0-9_]+', '_', raw).strip('_')
    return alias[:40]


def _ghost_log_source(identity, current_user=None):
    """Prefer the human alias over the canonical ghost owner username."""
    session_user = current_user or {}
    session_name = str(session_user.get('username') or '').strip().lower()
    session_display = _normalize_human_alias(session_user.get('display_name') or '')
    if session_name and session_name != 'ghost':
        return session_name
    if session_display:
        return session_display

    actor = identity.get('actor') or {}
    actor_name = str(actor.get('username') or identity.get('acting_user') or '').strip().lower()
    actor_display = _normalize_human_alias(actor.get('display_name') or '')
    if actor_name and actor_name != 'ghost':
        return actor_name
    if actor_display:
        return actor_display

    effective = identity.get('effective') or {}
    effective_name = str(effective.get('username') or identity.get('effective_user') or '').strip().lower()
    effective_display = _normalize_human_alias(effective.get('display_name') or '')
    if effective_name and effective_name != 'ghost':
        return effective_name
    if effective_display:
        return effective_display
    return actor_name or effective_name or 'ghost'


def _log_human_ghost_thought(message, identity, conversation_id=None, current_user=None):
    raw = str(message or '').strip()
    if not raw:
        return
    source = _ghost_log_source(identity, current_user=current_user)
    entry_type = 'developer_thought' if ('?' in raw or _chat_user_prompt_is_informational(raw)) else 'operator_prompt'
    conv_ref = f'conv:{conversation_id}' if conversation_id else ''
    meta = (
        f'acting_user={identity.get("acting_user") or ""} '
        f'effective_user={identity.get("effective_user") or ""} '
        f'proxy_as={identity.get("proxy_as") or ""}'
    ).strip()
    content = raw if not meta else f'{raw}\n\n[{meta}]'
    try:
        log_ghost_circle(entry_type, source, content, ticket_ref=conv_ref, severity='info')
    except Exception:
        pass


def _watchdog_get_kill_state(model_name: str) -> dict:
    key = str(model_name or '').strip().lower()
    with _WATCHDOG_KILL_LOCK:
        return _WATCHDOG_KILL_STATE.setdefault(key, {
            'consecutive_failures': 0,
            'last_attempt_ts': 0.0,
            'escalation_level': 0,
            'ticket_emitted': False,
        })


def _watchdog_reset_kill_state(model_name: str) -> None:
    key = str(model_name or '').strip().lower()
    with _WATCHDOG_KILL_LOCK:
        _WATCHDOG_KILL_STATE.pop(key, None)


def _watchdog_backoff_ok(state: dict) -> bool:
    """Return True if enough time has passed since the last attempt."""
    now = time.time()
    fails = int(state.get('consecutive_failures', 0))
    last = float(state.get('last_attempt_ts', 0.0))
    if fails == 0:
        return True
    # Exponential backoff: 5s, 10s, 20s, 40s, 60s (cap at 60)
    backoff = min(60, _WATCHDOG_BACKOFF_BASE_SECONDS * (2 ** (fails - 1)))
    return (now - last) >= backoff


def _chat_running_ollama_model_info():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=3) as resp:
            payload = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
        return [dict(item) for item in (payload.get('models') or []) if isinstance(item, dict)]
    except Exception:
        return []


def _chat_ollama_model_blob_patterns(model_name):
    try:
        payload = json.dumps({'model': str(model_name or '').strip()}).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:11434/api/show',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
        modelfile = str(data.get('modelfile') or '')
    except Exception:
        return []
    return sorted(set(re.findall(r'sha256-[0-9a-f]{32,}', modelfile, flags=re.IGNORECASE)))


def _watchdog_stop_direct_model(model_name: str, action: str) -> dict | None:
    """Stop a llama-server-backed model; None when the model is not direct."""
    try:
        from core import llm as _core_llm
        direct = _core_llm._direct_model(model_name)
    except Exception:
        direct = None
    if not direct:
        return None
    result = {'model': str(model_name or '').strip(), 'ok': False, 'detail': '', 'action': action}
    try:
        from core.seven_llm import llama_server
        stopped = llama_server.stop(direct)
        result['ok'] = True
        result['detail'] = f'llama-server stop {direct} stopped={bool(stopped)}'
    except Exception as exc:
        result['detail'] = f'llama-server stop failed: {exc}'
    return result


def _watchdog_api_unload_model(model_name: str, *, timeout_s: float = 8.0) -> dict:
    """Ask Ollama via HTTP /api/generate with keep_alive=0 to unload a model.

    This is the transport-agnostic unload (works whether Ollama runs as a
    local Linux daemon, on Windows over a WSL bridge, or remotely). It
    matches what the `ollama stop` CLI does internally. Returning ok=True
    only requires the request to succeed; the caller still re-checks
    /api/ps to confirm the model actually left memory.
    """
    name = str(model_name or '').strip()
    direct_result = _watchdog_stop_direct_model(name, 'direct-stop')
    if direct_result is not None:
        return direct_result
    result = {'model': name, 'ok': False, 'detail': '', 'action': 'api-unload'}
    if not name:
        result['detail'] = 'no model name'
        return result
    try:
        body = json.dumps({'model': name, 'keep_alive': 0}).encode('utf-8')
        req = urllib.request.Request(
            'http://127.0.0.1:11434/api/generate',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = getattr(resp, 'status', 200)
            resp.read()
        result['ok'] = 200 <= int(status) < 300
        result['detail'] = f'api keep_alive=0 status={status}'
    except Exception as exc:
        result['detail'] = f'api-unload failed: {exc}'
    return result


def _watchdog_kill_ollama_runner_pid(model_name: str) -> dict:
    """Find the actual ollama runner process for this model and kill -9 it."""
    direct_result = _watchdog_stop_direct_model(model_name, 'direct-stop')
    if direct_result is not None:
        return {'ok': direct_result['ok'], 'detail': direct_result['detail'], 'pid': None}
    result = {'ok': False, 'detail': '', 'pid': None}
    try:
        patterns = [str(model_name or '').strip()]
        aliases = _chat_model_aliases(model_name)
        for item in _chat_running_ollama_model_info():
            running_name = str(item.get('model') or item.get('name') or '').strip()
            if aliases and not (aliases & _chat_model_aliases(running_name)):
                continue
            digest = str(item.get('digest') or '').strip()
            if digest:
                patterns.append(digest)
                patterns.append('sha256-' + digest)
            patterns.extend(_chat_ollama_model_blob_patterns(running_name))

        pids = []
        seen = set()
        for pattern in [p for p in patterns if p]:
            proc = subprocess.run(
                ['pgrep', '-f', f'ollama.*runner.*{pattern}'],
                capture_output=True, text=True, timeout=6, check=False,
            )
            stdout = str(proc.stdout or '').strip()
            if proc.returncode != 0 or not stdout:
                continue
            for pid in stdout.splitlines():
                pid = pid.strip()
                if not pid.isdigit() or pid in seen or int(pid) == os.getpid():
                    continue
                try:
                    cmdline = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\x00', b' ').decode(errors='replace')
                except Exception:
                    cmdline = ''
                if 'ollama runner' not in cmdline or '--model' not in cmdline:
                    continue
                if pid not in seen:
                    seen.add(pid)
                    pids.append(pid)

        # Ollama runner commands use blob paths rather than model names on many
        # installs; the digest lookup above is the reliable path. If neither
        # form found a process, report the attempted patterns for diagnosis.
        if not pids:
            result['detail'] = f'pgrep found no runner for {model_name} (patterns={patterns})'
            return result
        killed = []
        failed = []
        for pid in pids:
            try:
                proc = subprocess.run(['kill', '-9', pid], capture_output=True, text=True, timeout=6, check=False)
                if proc.returncode != 0:
                    proc = subprocess.run(['sudo', '-n', 'kill', '-9', pid], capture_output=True, text=True, timeout=6, check=False)
                if proc.returncode == 0:
                    time.sleep(0.2)
                    if os.path.exists(f'/proc/{pid}'):
                        failed.append(f'{pid}:still-present')
                    else:
                        killed.append(pid)
                else:
                    detail = str(proc.stderr or proc.stdout or '').strip()
                    failed.append(f'{pid}:failed({detail or proc.returncode})')
            except Exception as exc:
                failed.append(f'{pid}:failed({exc})')
        result['pid'] = pids[0] if pids else None
        result['detail'] = f'kill-9 runner PIDs killed={killed} failed={failed} for {model_name}'
        result['ok'] = bool(killed) and not failed
    except Exception as exc:
        result['detail'] = f'kill-9 exception for {model_name}: {exc}'
    return result


def _watchdog_restart_ollama_service(model_name: str) -> dict:
    result = {'ok': False, 'detail': '', 'action': 'systemctl-restart-ollama'}
    try:
        proc = subprocess.run(
            ['systemctl', '--no-ask-password', 'restart', 'ollama'],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            result['detail'] = str(proc.stderr or proc.stdout or f'returncode={proc.returncode}').strip()
            return result
        after_models = _chat_wait_for_ollama_models_to_clear([model_name], timeout_s=8.0, interval_s=0.5)
        aliases = _chat_model_aliases(model_name)
        still = any(aliases & _chat_model_aliases(name) for name in after_models)
        result['ok'] = not still
        result['detail'] = 'ollama service restarted' if result['ok'] else f'ollama restarted but {model_name} still running'
    except Exception as exc:
        result['detail'] = f'ollama restart exception: {exc}'
    return result


def _watchdog_emit_escalation_ticket(agent_name: str, model_name: str, fails: int) -> None:
    """Emit a spine TICKET event when we've failed too many times."""
    try:
        from core import spine as _spine
        _spine.log(
            _spine.EventKind.TICKET,
            f'watchdog escalation: {agent_name} model {model_name} survived {fails} stop attempts. '
            f'ollama stop + kill-9 both failed. Human intervention required.',
            severity=_spine.Severity.ERROR,
            source='watchdog_ollama_escalation',
            agent=agent_name,
            payload={
                'model': model_name,
                'consecutive_failures': fails,
                'escalation_level': 3,
            },
        )
    except Exception:
        pass


def _chat_try_hard_kill_local_agent(agent_name, *, ignore_job_id=None):
    """Best-effort hard kill for local Ollama-backed jobs.

    Uses a circuit breaker with escalation:
      1. ollama stop (normal)
      2. kill -9 on the runner PID (if stop fails 3×)
      3. emit spine TICKET (if kill-9 also fails, after 5× total)

    Backoff prevents hammering the system every heartbeat.
    """
    normalized = _normalize_chat_participant(agent_name)
    result = {
        'agent': normalized or str(agent_name or '').strip().lower(),
        'configured_model': '',
        'before_models': [],
        'after_models': [],
        'models': [],
        'attempts': [],
        'ok': False,
        'detail': '',
    }
    if normalized not in _all_local_ollama_chat_agents():
        result['detail'] = 'agent is not an Ollama-backed local runtime'
        return result

    configured_model = _chat_agent_configured_model(normalized)
    result['configured_model'] = configured_model
    wanted_aliases = _chat_model_aliases(configured_model)
    running_models = _chat_running_ollama_models()
    result['before_models'] = running_models

    candidates = []
    for running_name in running_models:
        if wanted_aliases and _chat_model_aliases(running_name) & wanted_aliases:
            candidates.append(running_name)
    if configured_model and not candidates:
        candidates.append(configured_model)
    if not candidates:
        result['detail'] = 'no matching Ollama model is configured or currently running'
        return result

    unique_candidates = []
    seen = set()
    for model_name in candidates:
        key = str(model_name or '').strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_candidates.append(str(model_name).strip())

    result['models'] = unique_candidates
    still_running = []

    for model_name in unique_candidates:
        state = _watchdog_get_kill_state(model_name)

        # Respect backoff so we don't hammer every heartbeat.
        if not _watchdog_backoff_ok(state):
            result['attempts'].append({
                'model': model_name,
                'ok': False,
                'action': 'backoff',
                'detail': f'backoff active ({state["consecutive_failures"]} fails)',
            })
            still_running.append(model_name)
            continue

        state['last_attempt_ts'] = time.time()
        fails_before = int(state.get('consecutive_failures', 0))

        # Escalation level 2: kill -9 the runner PID directly.
        if fails_before >= _WATCHDOG_MAX_FAILS_BEFORE_KILL9:
            kill9_result = _watchdog_kill_ollama_runner_pid(model_name)
            result['attempts'].append({
                'model': model_name,
                'ok': kill9_result['ok'],
                'action': 'kill-9',
                'pid': kill9_result.get('pid'),
                'detail': kill9_result['detail'],
            })
            if kill9_result['ok']:
                state['consecutive_failures'] = 0
                state['escalation_level'] = 2
            else:
                restart_result = None
                try:
                    if not _chat_active_local_agents_from_db(exclude_job_id=ignore_job_id):
                        restart_result = _watchdog_restart_ollama_service(model_name)
                except Exception:
                    restart_result = None
                if restart_result:
                    result['attempts'].append({
                        'model': model_name,
                        'ok': restart_result['ok'],
                        'action': restart_result.get('action') or 'systemctl-restart-ollama',
                        'detail': restart_result.get('detail') or '',
                    })
                if restart_result and restart_result.get('ok'):
                    state['consecutive_failures'] = 0
                    state['escalation_level'] = 2
                else:
                    state['consecutive_failures'] = fails_before + 1
                    still_running.append(model_name)

            # Escalation level 3: emit spine TICKET once after max failures.
            if state['consecutive_failures'] >= _WATCHDOG_MAX_FAILS_BEFORE_TICKET and not state.get('ticket_emitted'):
                state['ticket_emitted'] = True
                state['escalation_level'] = 3
                _watchdog_emit_escalation_ticket(normalized, model_name, state['consecutive_failures'])
            continue

        # Escalation level 0/1: primary path is the HTTP API (keep_alive=0).
        # Works for local Linux daemon, Windows host over WSL bridge, or any
        # remote Ollama. Fall back to the CLI only if the API call failed
        # AND the CLI is available on PATH.
        api_result = _watchdog_api_unload_model(model_name)
        result['attempts'].append(api_result)
        if api_result['ok']:
            # Confirm via /api/ps before declaring success.
            after_models = _chat_wait_for_ollama_models_to_clear(
                [model_name], timeout_s=4.0, interval_s=0.4,
            )
            aliases = _chat_model_aliases(model_name)
            still = any(aliases & _chat_model_aliases(name) for name in after_models)
            if not still:
                state['consecutive_failures'] = 0
                state['escalation_level'] = 0
                continue

        try:
            proc = subprocess.run(
                ['ollama', 'stop', model_name],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            stdout = str(proc.stdout or '').strip()
            stderr = str(proc.stderr or '').strip()
            ok = proc.returncode == 0
            result['attempts'].append({
                'model': model_name,
                'ok': ok,
                'action': 'ollama-stop',
                'returncode': proc.returncode,
                'stdout': stdout,
                'stderr': stderr,
            })
            if ok:
                state['consecutive_failures'] = 0
                state['escalation_level'] = 0
            else:
                state['consecutive_failures'] = fails_before + 1
                still_running.append(model_name)
        except FileNotFoundError:
            # No CLI on this host (e.g. WSL bridging to Windows Ollama).
            # The API attempt above is what we have; treat its outcome as
            # authoritative and skip the OS-level escalation.
            if api_result['ok']:
                state['consecutive_failures'] = 0
                state['escalation_level'] = 0
            else:
                state['consecutive_failures'] = fails_before + 1
                still_running.append(model_name)
        except Exception as exc:
            state['consecutive_failures'] = fails_before + 1
            still_running.append(model_name)
            result['attempts'].append({
                'model': model_name,
                'ok': False,
                'action': 'ollama-stop',
                'returncode': None,
                'stdout': '',
                'stderr': str(exc),
            })

    after_models = _chat_wait_for_ollama_models_to_clear(unique_candidates)
    result['after_models'] = after_models
    after_alias_sets = [_chat_model_aliases(name) for name in after_models]
    for model_name in unique_candidates:
        aliases = _chat_model_aliases(model_name)
        if any(aliases & running_aliases for running_aliases in after_alias_sets):
            if model_name not in still_running:
                still_running.append(model_name)

    if still_running and len(after_models) == 1:
        try:
            proc = subprocess.run(
                ['pkill', '-f', 'ollama runner --model'],
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
            result['attempts'].append({
                'model': ','.join(still_running),
                'ok': proc.returncode in (0, 1),
                'action': 'runner-pkill',
                'returncode': proc.returncode,
                'stdout': str(proc.stdout or '').strip(),
                'stderr': str(proc.stderr or '').strip(),
            })
            time.sleep(1.0)
            after_models = _chat_running_ollama_models()
            result['after_models'] = after_models
            after_alias_sets = [_chat_model_aliases(name) for name in after_models]
            still_running = []
            for model_name in unique_candidates:
                aliases = _chat_model_aliases(model_name)
                if any(aliases & running_aliases for running_aliases in after_alias_sets):
                    still_running.append(model_name)
        except Exception as exc:
            result['attempts'].append({
                'model': ','.join(still_running),
                'ok': False,
                'action': 'runner-pkill',
                'returncode': None,
                'stdout': '',
                'stderr': f'runner-pkill-failed: {exc}',
            })

    if still_running:
        try:
            active_agents_now = _chat_active_local_agents_from_db(exclude_job_id=ignore_job_id)
        except Exception:
            active_agents_now = set()
        if not active_agents_now:
            for model_name in list(still_running):
                kill9_result = _watchdog_kill_ollama_runner_pid(model_name)
                result['attempts'].append({
                    'model': model_name,
                    'ok': kill9_result['ok'],
                    'action': 'kill-9-immediate',
                    'pid': kill9_result.get('pid'),
                    'detail': kill9_result.get('detail') or '',
                })
            after_models = _chat_wait_for_ollama_models_to_clear(unique_candidates, timeout_s=3.0, interval_s=0.5)
            result['after_models'] = after_models
            after_alias_sets = [_chat_model_aliases(name) for name in after_models]
            still_running = []
            for model_name in unique_candidates:
                aliases = _chat_model_aliases(model_name)
                if any(aliases & running_aliases for running_aliases in after_alias_sets):
                    still_running.append(model_name)
            for model_name in list(still_running):
                restart_result = _watchdog_restart_ollama_service(model_name)
                result['attempts'].append({
                    'model': model_name,
                    'ok': restart_result.get('ok'),
                    'action': restart_result.get('action') or 'systemctl-restart-ollama',
                    'detail': restart_result.get('detail') or '',
                })
            if still_running:
                after_models = _chat_wait_for_ollama_models_to_clear(unique_candidates, timeout_s=3.0, interval_s=0.5)
                result['after_models'] = after_models
                after_alias_sets = [_chat_model_aliases(name) for name in after_models]
                still_running = []
                for model_name in unique_candidates:
                    aliases = _chat_model_aliases(model_name)
                    if any(aliases & running_aliases for running_aliases in after_alias_sets):
                        still_running.append(model_name)

    # Purge from still_running anything ollama ps confirms is actually gone.
    # The stop/kill action may report failure because the process exited
    # during the attempt; ollama ps is ground truth.
    after_set = set(after_models)
    for model_name in unique_candidates:
        if model_name in still_running and model_name not in after_set:
            still_running.remove(model_name)

    # Reset state for models that are actually gone now.
    for model_name in unique_candidates:
        if model_name not in still_running or model_name not in after_set:
            _watchdog_reset_kill_state(model_name)

    ok_models = [item['model'] for item in result['attempts'] if item.get('ok')]
    result['stopped_models'] = [m for m in unique_candidates if m not in still_running]
    result['still_running_models'] = still_running
    result['ok'] = bool(unique_candidates) and not still_running
    if result['ok']:
        result['detail'] = 'stopped ' + ', '.join(result['stopped_models'] or ok_models or unique_candidates)
    else:
        errors = [item.get('detail') or item.get('stderr') or item.get('stdout') or 'unknown error' for item in result['attempts']]
        if still_running:
            result['detail'] = 'still running after stop: ' + ', '.join(still_running)
        else:
            result['detail'] = '; '.join(errors[:2])
    return result


def _chat_wait_for_ollama_models_to_clear(model_names, *, timeout_s=5.0, interval_s=0.5):
    """Poll Ollama briefly after stop/kill so unload latency is not logged as failure."""
    wanted = [str(name or '').strip() for name in (model_names or []) if str(name or '').strip()]
    if not wanted:
        return _chat_running_ollama_models()
    deadline = time.time() + max(0.0, float(timeout_s or 0))
    checks = max(1, int(max(0.0, float(timeout_s or 0)) / max(0.05, float(interval_s or 0.5))) + 1)
    after_models = _chat_running_ollama_models()
    for _ in range(checks):
        after_alias_sets = [_chat_model_aliases(name) for name in after_models]
        still = []
        for model_name in wanted:
            aliases = _chat_model_aliases(model_name)
            if any(aliases & running_aliases for running_aliases in after_alias_sets):
                still.append(model_name)
        if not still:
            return after_models
        if time.time() >= deadline:
            break
        time.sleep(max(0.05, float(interval_s or 0.5)))
        after_models = _chat_running_ollama_models()
    return after_models


def _chat_runtime_stop_trace(result):
    agent = str((result or {}).get('agent') or 'agent')
    if not result:
        return f'ollama stop skipped - {agent}: no result'
    detail = str(result.get('detail') or '').strip()
    before = ','.join(result.get('before_models') or [])
    after = ','.join(result.get('after_models') or [])
    status = 'ok' if result.get('ok') else 'failed'
    bits = [f'ollama stop {status} - {agent}']
    if detail:
        bits.append(detail[:220])
    if before or after:
        bits.append(f'before=[{before}] after=[{after}]')
    return ' - '.join(bits)


def _chat_log_watchdog_ollama_event(conversation_id, job_id, agent_name, action, result, message):
    payload = {
        'action': str(action or ''),
        'job_id': str(job_id or ''),
        'agent': str(agent_name or ''),
        'ok': bool((result or {}).get('ok')),
        'configured_model': (result or {}).get('configured_model') or '',
        'models': (result or {}).get('models') or [],
        'before_models': (result or {}).get('before_models') or [],
        'after_models': (result or {}).get('after_models') or [],
        'detail': (result or {}).get('detail') or '',
    }
    try:
        if conversation_id:
            _trace(
                conversation_id,
                'watchdog',
                'ollama_control',
                payload,
                job_id=job_id,
            )
    except Exception:
        pass
    try:
        from core import spine as _spine
        _spine.log(
            _spine.EventKind.WATCHDOG,
            message,
            severity=_spine.Severity.INFO if payload['ok'] else _spine.Severity.WARN,
            source='watchdog_ollama',
            agent=str(agent_name or '') or None,
            thread_id=str(conversation_id or '') or None,
            payload=payload,
        )
    except Exception:
        pass


def _chat_apply_runtime_stop_to_job(
    job_id,
    agent_name,
    reason,
    *,
    elapsed_ms=0,
    stage_trace=None,
    conversation_id=None,
    action='watchdog_stop',
):
    trace = list(stage_trace or [])
    try:
        update_chat_job_db(
            job_id,
            status='failed',
            stage='stalled',
            error=str(reason or '').strip(),
            elapsed_ms=int(elapsed_ms or 0),
            stage_trace_json=json.dumps(trace),
        )
    except Exception:
        pass
    result = _chat_try_hard_kill_local_agent(agent_name, ignore_job_id=job_id)
    stop_text = _chat_runtime_stop_trace(result)
    trace.append({'text': stop_text, 'ts': time.time()})
    error = str(reason or '').strip()
    detail = str(result.get('detail') or '').strip()
    if detail:
        error = (error + '; ' if error else '') + f'ollama stop: {detail}'
    try:
        update_chat_job_db(
            job_id,
            status='failed',
            stage='stalled',
            error=error,
            elapsed_ms=int(elapsed_ms or 0),
            stage_trace_json=json.dumps(trace),
        )
    except Exception:
        pass
    _chat_log_watchdog_ollama_event(
        conversation_id,
        job_id,
        agent_name,
        action,
        result,
        stop_text,
    )
    return result, trace, error


def _chat_schedule_delayed_runtime_cleanup(agent_name, job_id=None, delay_seconds=30):
    agent = str(agent_name or '').strip().lower()
    if not agent:
        return False

    def _delayed():
        try:
            time.sleep(max(1, int(delay_seconds or 30)))
            _chat_try_hard_kill_local_agent(agent, ignore_job_id=job_id)
        except Exception:
            pass

    try:
        thread = threading.Thread(
            target=_delayed,
            name=f'chat-delayed-cleanup-{agent}',
            daemon=True,
        )
        thread.start()
        return True
    except Exception:
        return False


def _chat_active_local_agents_from_db(exclude_job_id=None):
    try:
        conn = get_connection()
        try:
            params = []
            extra = ''
            if exclude_job_id:
                extra = ' AND job_id != ?'
                params.append(str(exclude_job_id))
            rows = conn.execute(
                f"""
                SELECT DISTINCT agent
                FROM chat_jobs
                WHERE status IN ('running', 'dispatched', 'processing')
                  AND runtime_class='local'
                  {extra}
                """,
                params,
            ).fetchall()
            return {
                _normalize_chat_participant(row['agent'])
                for row in rows
                if str(row['agent'] or '').strip()
            }
        finally:
            conn.close()
    except Exception:
        return set()


def _chat_sch_council_active():
    """Council models are owned by Seven's active SCH job, not orphan runners."""
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT is_council_active FROM diamond_sch_state WHERE state_id=1"
            ).fetchone()
            return bool(row and row['is_council_active'])
        finally:
            conn.close()
    except Exception:
        return False


def _chat_reconcile_unowned_ollama_runners(conversation_id=None):
    """Stop local Ollama models that no live Fridays chat job owns.

    This is the bridge step while Ollama remains an external wrapper: Fridays
    treats the DB/runtime job table as ownership truth and unloads matching
    chat-agent models when no active job exists for that agent.
    """
    if _chat_sch_council_active():
        return []
    # One model stays resident on the GPU. Unloading it after each chat forces a cold reload
    # (~15 s), and a wrong "unowned" reading kills a reply mid-sentence.
    if os.environ.get('SWARM_ONE_MODEL', '1').strip().lower() not in {'0', 'false', 'no', 'off'}:
        return []
    active_agents = _chat_active_local_agents_from_db()
    # Jobs this process is running are always owned, even if the DB row could not be read.
    with _CHAT_JOB_LOCK:
        active_agents = set(active_agents) | {
            _normalize_chat_participant(j.get('agent'))
            for j in _CHAT_JOBS.values()
            if str(j.get('status') or '') == 'running' and str(j.get('agent') or '').strip()
        }
    running_models = _chat_running_ollama_models()
    if not running_models:
        return []

    stopped = []
    for agent_name in sorted(_all_local_ollama_chat_agents()):
        agent = _normalize_chat_participant(agent_name)
        if not agent or agent in active_agents:
            continue
        configured_model = _chat_agent_configured_model(agent)
        from utils.local_runtime_policy import is_resident_cpu_backup
        if is_resident_cpu_backup(configured_model):
            continue
        aliases = _chat_model_aliases(configured_model)
        if not configured_model or not aliases:
            continue
        if not any(aliases & _chat_model_aliases(model) for model in running_models):
            continue
        result = _chat_try_hard_kill_local_agent(agent)
        stopped.append(result)
        _chat_log_watchdog_ollama_event(
            conversation_id,
            '',
            agent,
            'watchdog_unowned_runner_stop',
            result,
            _chat_runtime_stop_trace(result),
        )
    return stopped


def _chat_schedule_unowned_runner_reconcile(conversation_id=None):
    """Run wrapper cleanup without blocking the user-facing status poll."""
    global _CHAT_RECONCILE_LAST_TS
    now = time.monotonic()
    with _CHAT_RECONCILE_SCHEDULE_LOCK:
        if now - _CHAT_RECONCILE_LAST_TS < _CHAT_RECONCILE_MIN_INTERVAL_SECONDS:
            return False
        _CHAT_RECONCILE_LAST_TS = now

    def _reconcile():
        try:
            _chat_reconcile_unowned_ollama_runners(conversation_id)
        except Exception:
            pass

    try:
        threading.Thread(
            target=_reconcile,
            name=f'chat-runner-reconcile-{int(conversation_id or 0)}',
            daemon=True,
        ).start()
        return True
    except Exception:
        return False


def _chat_ensure_unusable_thread_recovery(conversation_id):
    """Open one watchdog card when the latest persisted reply is not useful."""
    try:
        conv_id = int(conversation_id or 0)
    except Exception:
        return {'created': False, 'recovery': None, 'message': ''}
    if conv_id <= 0:
        return {'created': False, 'recovery': None, 'message': ''}
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT id, from_agent, content
                FROM messages
                WHERE conversation_id=?
                ORDER BY id DESC
                LIMIT 12
                """,
                (conv_id,),
            ).fetchall()
        finally:
            conn.close()
        latest_reply = next(
            (dict(row) for row in rows if str(row['from_agent'] or '') not in {'user', 'watchdog'}),
            None,
        )
        latest_user = next(
            (dict(row) for row in rows if str(row['from_agent'] or '') == 'user'),
            None,
        )
        if not latest_reply or not latest_user or int(latest_reply['id']) < int(latest_user['id']):
            return {'created': False, 'recovery': None, 'message': ''}
        reply_text = str(latest_reply.get('content') or '')
        prompt_text = str(latest_user.get('content') or '')
        agent = str(latest_reply.get('from_agent') or 'agent')
        if not (
            _chat_response_is_unusable(agent, reply_text)
            or _chat_response_echoes_prompt(prompt_text, reply_text)
        ):
            return {'created': False, 'recovery': None, 'message': ''}
        return ensure_chat_relay_recovery(
            job_id=f'quality-thread-{conv_id}-{int(latest_reply["id"])}',
            conversation_id=conv_id,
            stalled_agent=agent,
            reason='Watchdog: latest persisted agent reply is unusable or echoes the user prompt.',
            stage_trace=[{'text': 'unusable persisted reply detected (watchdog)'}],
        )
    except Exception as exc:
        return {'created': False, 'recovery': None, 'message': '', 'error': str(exc)}

# Thread/history helpers live in services.chat_history and are re-exported
# through services/__init__.py. Names available here via `from services import *`:
#   _fetch_chat_thread_rows, _chat_history_from_rows,
#   _thread_transcript_from_rows, _conversation_reply_context_from_rows,
#   _build_chat_handoff_block.


# Chat relay / intent parsing helpers live in services.chat_relay and are
# available here via `from services import *` at the top of this module.
# Names re-exported: _RELAY_LINE_PATTERNS, _RELAY_ROUTE_PATTERNS,
# _derive_proposal_from_text, _extract_skill_lines_from_text, _gate_relay_target,
# _infer_reply_target_from_text, _is_execution_confirmation,
# _parse_chat_skill_command, _resolve_chat_reply_target, _strip_relay_routing.

def _load_local_agent_memories(selected_agent, latest_message, topic_limit=4, recent_limit=2):
    query = str(latest_message or '').strip()[:160]
    collected = []
    seen_ids = set()

    for search_query, limit in ((query, topic_limit), ('', recent_limit)):
        try:
            rows = get_agent_memory(selected_agent, query=search_query, limit=limit) or []
        except Exception:
            rows = []
        for row in rows:
            row_id = row['id'] if 'id' in row.keys() else id(row)
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            collected.append(row)
    return collected

def _build_local_memory_block(selected_agent, latest_message):
    memories = _load_local_agent_memories(selected_agent, latest_message)
    if not memories:
        return ''

    lines = []
    for row in memories:
        tags = str(row['tags'] or '').strip()
        subject = str(row['subject'] or '').strip()[:120]
        content = str(row['content'] or '').strip().replace('\n', ' ')[:420]
        combined = f'{subject} {content}'.lower()
        if 'live_chat_proof' in combined or 'archived-bad-live-proof' in tags.lower():
            continue
        prefix = f'[{tags}] ' if tags else ''
        lines.append(f'- {prefix}{subject}: {content}')

    if not lines:
        return ''

    return (
        '\n\n=== Your recent memory ===\n'
        + '\n'.join(lines)
        + '\n=== End memory ===\n'
        + 'Use this for continuity and hand-off. Do not quote it verbatim unless asked.'
    )

def _build_knowledge_broadcast_block(agent_name, latest_message=''):
    """Inject recent unacked swarm knowledge + research events into agent context (A.3.4, B.5.3)."""
    try:
        from utils.db.knowledge import get_unacked_events, ack_all_events
        events = get_unacked_events(agent_name, event_type='knowledge.new', limit=5)
        if not events:
            return ''
        lines = []
        ids = []
        for ev in events:
            try:
                import json as _json
                payload = _json.loads(ev['payload'])
                cat = payload.get("category", "?")
                key = payload.get("key", "?")
                src = payload.get("source_agent", "?")
                # Mark research-origin entries
                prefix = '[Research] ' if str(key).startswith('research:') else ''
                lines.append(f'- {prefix}[{cat}] {key} (by {src})')
            except Exception:
                lines.append(f'- {str(ev.get("payload", ""))[:100]}')
            ids.append(ev['id'])
        # Ack so agent doesn't see them again
        from utils.local_runtime_policy import is_explicitly_no_tools_request
        if ids and not is_explicitly_no_tools_request(latest_message):
            ack_all_events(agent_name, ids)
        return (
            '\n\n=== New swarm knowledge ===\n'
            + '\n'.join(lines)
            + '\n=== End knowledge broadcast ===\n'
        )
    except Exception:
        return ''


def _normalize_project_context_text(value):
    from core.knowledge import context_packs as _context_packs
    return _context_packs.normalize_project_context_text(value)


def _resolve_project_context_id(text):
    from core.knowledge import context_packs as _context_packs
    return _context_packs.resolve_project_context_id(text)


def _project_context_doc_rows(project_id, project_name, limit=3):
    from core.knowledge import context_packs as _context_packs
    return _context_packs.project_context_doc_rows(project_id, project_name, limit)


def _build_project_context_block(text):
    from core.knowledge import context_packs as _context_packs
    return _context_packs.build_project_context_block(
        text,
        doc_loader=_project_context_doc_rows,
    )


def _build_local_agent_prompt(selected_agent, threaded_prompt, latest_message, reply_context, conv_id=None, auto_relay=True):
    memory_block = _build_local_memory_block(selected_agent, latest_message)
    knowledge_block = _build_knowledge_broadcast_block(selected_agent, latest_message)
    handoff_block = _build_chat_handoff_block(selected_agent, reply_context, auto_relay=auto_relay)
    project_block = _build_project_context_block(f'{latest_message}\n{threaded_prompt[-4000:]}')
    if is_worker_agent(selected_agent):
        # The worker runs on a 4096-token context: only carry project context when asked about it.
        if re.search(r'(?i)\b(projects?|studio|steps?|scenes?|P-[0-9A-F]{10})\b', str(latest_message or '')):
            project_block = project_block[:900]
        else:
            project_block = ''
    base_prompt = handoff_block + project_block + memory_block + knowledge_block + threaded_prompt
    if str(selected_agent or '').lower() in _THREAD_HATS:
        try:
            base_prompt = _carry_over_block(selected_agent, conv_id, latest_message) + base_prompt
        except Exception:
            pass
    prefix = _chat_audit_prefix(selected_agent)
    if prefix:
        return prefix + base_prompt
    return base_prompt

def _get_ghost_agent_names():
    """Return names of all enabled non-local agents (tier paid/free) from DB."""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT name FROM agents WHERE tier IN ('paid','free') AND enabled=1"
        ).fetchall()
        conn.close()
        return {r['name'] for r in rows}
    except Exception:
        return {'nine', 'ten', 'eleven', 'twelve', 'thirteen'}


def _get_agent_labels():
    """Return {name: label} for all agents from DB, with fallback to name."""
    try:
        conn = get_connection()
        rows = conn.execute("SELECT name, label FROM agents WHERE enabled=1").fetchall()
        conn.close()
        return {r['name']: (r['label'] or r['name'].capitalize()) for r in rows}
    except Exception:
        return {}


def _should_attach_ticket_snapshot(latest_message, thread_rows):
    text = str(latest_message or '').strip().lower()
    if not text and thread_rows:
        text = str(thread_rows[-1].get('message') or '').strip().lower()
    if not text:
        return False
    if re.search(r'(?m)^\s*/?skill\s+[a-z0-9_-]+\b|\bskill\s+(?:shell|fs_readonly)\b', text):
        return False
    if re.search(r'\b(?:project[_ ]steps?|steps?|database|db|sqlite|scheduled[_ ]tasks?)\b', text):
        return False
    if re.search(r'\b(?:internal-[a-z]+-\d+|ticket-\d+|tg-\d+|s-[0-9a-f]{10}|p-[0-9a-f]{10})\b', text):
        return False
    triggers = (
        'ticket', 'tickets', 'queue', 'triage', 'open',
        'proposal', 'proposals', 'backlog', 'pending',
        'work item', 'work items', 'action plan', 'status'
    )
    return any(term in text for term in triggers)

def _build_ticket_snapshot_block(limit=8):
    conn = get_connection()
    try:
        queue_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM queue GROUP BY status"
        ).fetchall()
        queue_counts = {str(r['status'] or 'unknown').lower(): int(r['c'] or 0) for r in queue_rows}
        queue_total = sum(queue_counts.values())

        proposal_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM work_proposals GROUP BY status"
        ).fetchall()
        proposal_counts = {str(r['status'] or 'unknown').lower(): int(r['c'] or 0) for r in proposal_rows}

        pending_rows = conn.execute(
            """
            SELECT wp.proposal_id, wp.agent, wp.title, wp.status, wp.queue_id,
                   q.status AS queue_status, q.created_at
            FROM work_proposals wp
            LEFT JOIN queue q ON q.id = wp.queue_id
            WHERE lower(coalesce(wp.status, '')) IN ('pending', 'approved', 'in_progress')
            ORDER BY coalesce(q.created_at, wp.created_at) DESC
            LIMIT ?
            """,
            (int(max(1, min(20, limit))),)
        ).fetchall()

        lines = []
        for row in pending_rows:
            pid = str(row['proposal_id'] or '').strip() or '(no-id)'
            agent_name = str(row['agent'] or 'unknown').strip()
            title = str(row['title'] or '').strip().replace('\n', ' ')
            title = title[:140] if len(title) > 140 else title
            p_status = str(row['status'] or 'unknown').strip().lower()
            q_status = str(row['queue_status'] or 'unknown').strip().lower()
            lines.append(f"- {pid} | {agent_name} | {p_status}/{q_status} | {title}")

        queue_open = int(queue_counts.get('queued', 0) + queue_counts.get('processing', 0))
        queue_done = int(queue_counts.get('completed', 0) + queue_counts.get('done', 0))
        queue_failed = int(queue_counts.get('failed', 0))

        prop_pending = int(proposal_counts.get('pending', 0))
        prop_approved = int(proposal_counts.get('approved', 0))
        prop_in_progress = int(proposal_counts.get('in_progress', 0))
        prop_closed = int(proposal_counts.get('closed', 0) + proposal_counts.get('executed', 0) + proposal_counts.get('done', 0))

        return (
            "\n\n=== Live Ticket Snapshot ===\n"
            f"Queue: total={queue_total}, open={queue_open}, done={queue_done}, failed={queue_failed}\n"
            f"Proposals: pending={prop_pending}, approved={prop_approved}, in_progress={prop_in_progress}, closed={prop_closed}\n"
            "Open proposal samples (newest first):\n"
            + ("\n".join(lines) if lines else "- none")
            + "\nUse this snapshot directly as ground truth for this turn."
            + " If the user asks about open tickets/triage/action plan, answer from these counts and samples first"
            + " and do NOT ask the user to provide the same ticket list again unless snapshot shows none."
        )
    except Exception as exc:
        log_activity('terminal', 'chat_ticket_snapshot_warning', str(exc)[:180])
        return ''
    finally:
        conn.close()

def _persist_local_agent_memory(selected_agent, latest_message, response_text):
    answer = str(response_text or '').strip()
    if not answer:
        return

    lowered = answer.lower()
    if lowered.startswith(f'[{selected_agent}] acknowledged.'):
        return
    if 'taking longer than expected' in lowered:
        return
    if lowered.endswith('no response'):
        return
    if 'live_chat_proof' in lowered or 'live_chat_proof' in str(latest_message or '').lower():
        return
    if 'your agent name is gemma' in lowered and str(selected_agent or '').strip().lower() != 'gemma':
        return

    content = (
        f'User asked: {str(latest_message or '').strip()[:400]}\n'
        f'You answered: {answer[:1600]}'
    )
    try:
        save_agent_memory(
            agent_name=selected_agent,
            subject=str(latest_message or '').strip()[:100] or f'{selected_agent} terminal chat',
            content=content,
            tags='chat,terminal-ui,shared-thread',
            importance=7,
            source='terminal_chat',
        )
    except Exception as exc:
        log_activity('terminal', 'chat_memory_persist_warning', f'{selected_agent}: {exc}')


def _friendly_api_error(exc) -> str:
    """Return a concise, human-readable description of an API exception."""
    import re as _re
    # SDK-style structured errors (Anthropic, OpenAI) expose .body or .message
    body = getattr(exc, 'body', None)
    if isinstance(body, dict):
        inner = body.get('error') or {}
        msg = inner.get('message') if isinstance(inner, dict) else None
        if msg:
            return str(msg)
    sdk_msg = getattr(exc, 'message', None)
    if sdk_msg and sdk_msg != str(exc):
        return str(sdk_msg)
    # Try to pull 'message': '...' out of the string representation
    raw = str(exc)
    m = _re.search(r"'message':\s*'([^']+)'", raw) or _re.search(r'"message":\s*"([^"]+)"', raw)
    if m:
        return m.group(1)
    # Known substrings → friendly labels
    if 'credit balance' in raw.lower() or 'billing' in raw.lower():
        return 'API credit balance too low — please top up billing'
    if 'rate limit' in raw.lower() or '429' in raw:
        return 'Rate limit reached — please retry shortly'
    if 'invalid api key' in raw.lower() or '401' in raw:
        return 'Invalid or missing API key'
    if 'context length' in raw.lower() or 'token' in raw.lower() and 'exceed' in raw.lower():
        return 'Context length exceeded'
    # Fallback: first 120 chars stripped of dict noise
    return raw[:120]



@chat_bp.route('/api/chat', methods=['POST'])
def api_chat():
    """Send a chat message to one or more agents on a shared conversation thread."""
    data = request.get_json() or {}
    bound_task = None
    message = (data.get('message') or '').strip()
    explicit_agent_field = str(data.get('agent') or '').strip().lower()
    agent = (explicit_agent_field or 'seven').strip().lower()
    requested_agents = data.get('agents')
    requested_conv_id = data.get('conversation_id')
    force_new_thread = bool(data.get('new_thread'))
    relay_from = str(data.get('relay_from') or '').strip().lower() or None
    auto_relay = bool(data.get('auto_relay', True))
    parallel_mode = bool(data.get('parallel_mode', False))
    history_mode = str(data.get('history_mode') or 'full').strip().lower()
    history_limit_raw = data.get('history_limit')

    if not message:
        return jsonify({'ok': False, 'response': 'Empty message'}), 400
    if not relay_from:
        from importlib import import_module
        control_module=import_module(__package__+'.peer_bridge')
        control_reply=control_module.maybe_owner_chat_control(data,message)
        if control_reply is not None:return control_reply
    if _is_owner_package_command(message):
        return _owner_package_command(message)
    # Main chat always starts with the local harness. Stale UI selections and
    # historical thread participants cannot implicitly invoke paid providers.
    data["local_only"] = True
    from core.peer_bridge import mentioned_peers
    peer_targets = mentioned_peers(message)
    # Local APEX has no external inbox worker; invoke its tool-enabled handler.
    if peer_targets == ["apex"]:
        peer_targets = []
        data["local_only"] = True
    # In the APEX lane an @mention only flags a peer as addressed; APEX still answers first.
    if (peer_targets and not relay_from
            and re.match(r'^\s*@(codex|gemini|instructor|copilot|tiered(?:-assistant)?|mistral(?:-vibe)?|vibe)\b', message, re.I)):
        import importlib as _importlib
        import sys as _sys
        peer_name = _sse_module().__name__.replace('.sse', '.peer_bridge')
        peer_mod = _sys.modules.get(peer_name) or _importlib.import_module(peer_name)
        return peer_mod.dispatch_operator_message(data, message, [peer for peer in peer_targets if peer != "apex"])
    from core.chat_continuity import (
        STATE_OFFLINE, STATE_OK, STATE_RECOVERY, APEX_AGENT, ApexOffline, ContinuityChat,
        apex_roster, apex_system_prompt, call_apex, recovery_roster, storage_fault,
    )

    apex_lane = data.get("local_only") is True
    routed_from = []
    if apex_lane:
        # APEX is the sole local routing target. Record what the UI asked for
        # so the response is honest about the override, then force the lane.
        if isinstance(requested_agents, list):
            routed_from = [str(item or '').strip().lower() for item in requested_agents if str(item or '').strip()]
        elif explicit_agent_field:
            routed_from = [explicit_agent_field]
        if relay_from:
            return jsonify({
                'ok': False, 'state': STATE_OK,
                'response': 'APEX is the only local routing target; agent relays are disabled.',
            }), 400
        requested_agents = [APEX_AGENT['name']]
        explicit_agent_field = APEX_AGENT['name']
        agent = APEX_AGENT['name']

    primary_chat_fault = storage_fault(get_connection)
    if apex_lane:
        routable_rows = recovery_roster() if primary_chat_fault else apex_roster()
    elif primary_chat_fault:
        # Non-local or relayed traffic cannot be served while primary storage is faulted;
        # say so explicitly instead of failing agent validation against the APEX-only roster.
        return jsonify({
            'ok': False, 'state': STATE_RECOVERY, 'storage_degraded': True,
            'response': 'Primary chat storage is unavailable. Recovery chat permits local-only, non-relayed messages.',
        }), 503
    else:
        routable_rows = _reg_routable()

    # Force parallel dispatch when user explicitly selects multiple agents.
    # Sequential stalling is for relay chains, not multi-agent fan-out.
    if isinstance(requested_agents, list) and len(requested_agents) > 1:
        parallel_mode = True

    if history_mode not in {'full', 'recent', 'none'}:
        history_mode = 'full'

    try:
        history_limit = int(history_limit_raw) if history_limit_raw is not None else 8
    except Exception:
        history_limit = 8
    history_limit = max(1, min(30, history_limit))

    # Routable view: excludes Ghost (human tier), Scholar + Seeker (silent-api
    # services used by local agents for internet access), disabled agents.
    allowed_agents = {a['name'].lower() for a in routable_rows}

    explicit_agent_selection = bool(explicit_agent_field or (isinstance(requested_agents, list) and requested_agents))
    if isinstance(requested_agents, list) and requested_agents:
        normalized_agents = []
        for item in requested_agents:
            name = str(item or '').strip().lower()
            if name and name not in normalized_agents:
                normalized_agents.append(name)
        if not normalized_agents:
            return jsonify({'ok': False, 'response': 'No agents selected'}), 400
    else:
        mentioned_agents = _chat_extract_explicit_agent_mentions(message, allowed_agents)
        followup_agents = (
            _chat_followup_agents(requested_conv_id, allowed_agents)
            if not explicit_agent_selection and not mentioned_agents and not force_new_thread and not relay_from
            else []
        )
        if not explicit_agent_field and mentioned_agents:
            normalized_agents = mentioned_agents
        elif followup_agents:
            normalized_agents = followup_agents
        elif not explicit_agent_selection and _chat_prompt_needs_clarification(message):
            normalized_agents = ['watchdog']
        else:
            normalized_agents = [agent]

    bad_agents = [name for name in normalized_agents if name not in allowed_agents]
    if bad_agents == ['watchdog']:
        bad_agents = []
    if bad_agents:
        return jsonify({'ok': False, 'response': f"Unsupported agent(s): {', '.join(bad_agents)}"}), 400

    if data.get('local_only') is True:
        local_agents = {
            row['name'].lower() for row in routable_rows
            if str(row.get('tier') or '').lower() == 'local'
        }
        if any(name not in local_agents for name in normalized_agents):
            return jsonify({
                'ok': False,
                'response': 'Local chat cannot dispatch to a non-local agent.',
            }), 400
        auto_relay = False

    identity, err = _resolve_identity_or_response(data)
    if err:
        return err
    current_user = get_current_user()

    # Per-request dedup flag: prevents multiple agents in a single multi-agent
    # chat turn from each auto-creating their own proposal.  Only the first agent
    # whose response matches proposal structure gets to create one; the rest skip.
    _proposal_created_this_request = [False]

    def _execute_agent_skill_lines(selected_agent, response_text, request_data):
        from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY
        from utils.local_runtime_policy import (
            is_read_only_agent,
            is_explicitly_no_tools_request,
            normalize_read_only_response,
        )

        if is_read_only_agent(selected_agent):
            commands = _extract_skill_lines_from_text(response_text)
            for skill_name, skill_args in commands:
                _record_vortex_action(
                    'tool_call',
                    source_agent=selected_agent,
                    target_agent=skill_name,
                    status='rejected',
                    context_parts=(skill_args,),
                    thread_id=conv_id,
                    details={'tool_name': skill_name, 'reason': 'read_only_profile'},
                    source='fridays.tool',
                )
            return (
                normalize_read_only_response(selected_agent, response_text)
                if commands else ''
            )

        # Developer Agents (Nine, Ten, Eleven, Twelve, Thirteen) execute Ghost One-directed
        # requests immediately — no proposal gate, no ALM confirmation loop.
        # Worker Agents (Gemma, LLaMA, Qwen, Mistral, Eight, Duck, Sniffles, Librarian)
        # must route through proposals and wait for approval.
        _developer_agents = _get_ghost_agent_names()
        is_developer_agent = selected_agent in _developer_agents
        informational_request = _chat_user_prompt_is_informational(message)
        no_tools_request = is_explicitly_no_tools_request(message)

        allowed_auto_skills = {'alm_create_proposal', 'ticket_create'}
        if is_developer_agent:
            allowed_auto_skills = allowed_auto_skills | {'fs_write', 'fs_patch', 'fs_readonly'}
        if informational_request:
            allowed_auto_skills = {'fs_readonly'} if is_developer_agent else set()
        if no_tools_request:
            allowed_auto_skills = set()

        cmds = _extract_skill_lines_from_text(response_text)
        if not cmds:
            # Developer agents: do NOT auto-create proposals from structured text.
            # Their responses are execution narration, not proposal drafts.
            if is_developer_agent:
                return ''
            if informational_request or no_tools_request:
                return ''
            # Dedup: only one auto-derived proposal per chat request across all agents
            if _proposal_created_this_request[0]:
                return ''
            derived = _derive_proposal_from_text(selected_agent, response_text, message)
            if not derived:
                return ''
            title, desc = derived
            safe_title = str(title).replace('"', "'")
            safe_desc = str(desc).replace('"', "'")
            synthetic_args = f'"{safe_title}" "{safe_desc}"'
            ok, out = skill_call('alm_create_proposal', args=synthetic_args, agent=selected_agent, source_conv_id=conv_id)
            _record_vortex_action(
                'tool_call',
                source_agent=selected_agent,
                target_agent='alm_create_proposal',
                status='completed' if ok else 'failed',
                context_parts=(message, synthetic_args),
                thread_id=conv_id,
                details={'tool_name': 'alm_create_proposal'},
                source='fridays.tool',
            )
            if ok:
                _proposal_created_this_request[0] = True
            preview = str(out or '')[:3000]
            return f"[skill:alm_create_proposal] {'OK' if ok else 'FAILED'}\\n{preview}"

        lines = []
        for skill_name, skill_args in cmds:
            if skill_name not in allowed_auto_skills:
                _record_vortex_action(
                    'tool_call', source_agent=selected_agent, target_agent=skill_name,
                    status='skipped', context_parts=(message, skill_args), thread_id=conv_id,
                    details={'tool_name': skill_name, 'reason': 'not_allowed'},
                    source='fridays.tool',
                )
                lines.append(f'[skill:{skill_name}] SKIPPED\\nAuto-execution only allows proposal skills.')
                continue

            meta = SKILL_REGISTRY.get(skill_name)
            if not meta:
                _record_vortex_action(
                    'tool_call', source_agent=selected_agent, target_agent=skill_name,
                    status='failed', context_parts=(message, skill_args), thread_id=conv_id,
                    details={'tool_name': skill_name, 'reason': 'unknown_tool'},
                    source='fridays.tool',
                )
                lines.append(f'[skill:{skill_name}] FAILED\\nUnknown skill')
                continue

            if not can_user_invoke_skill(selected_agent, skill_name, default_allow=True):
                _record_vortex_action(
                    'tool_call', source_agent=selected_agent, target_agent=skill_name,
                    status='rejected', context_parts=(message, skill_args), thread_id=conv_id,
                    details={'tool_name': skill_name, 'reason': 'not_authorized'},
                    source='fridays.tool',
                )
                lines.append(f'[skill:{skill_name}] FAILED\\nNot authorized for user {selected_agent}')
                continue

            trust_level = int(meta.get('trust_level', 0) or 0)
            # Developer agents bypass the ALM gate for Ghost One-directed chat requests.
            # Worker agents and self-initiated background work still go through the gate.
            if trust_level >= 1 and skill_name not in {'ticket_create', 'alm_create_proposal'} and not is_developer_agent:
                gate = _alm_gate_or_response(request_data, f'chat_skill_{skill_name}')
                if gate:
                    _record_vortex_action(
                        'tool_call', source_agent=selected_agent, target_agent=skill_name,
                        status='rejected', context_parts=(message, skill_args), thread_id=conv_id,
                        details={'tool_name': skill_name, 'reason': 'approval_required'},
                        source='fridays.tool',
                    )
                    lines.append(f'[skill:{skill_name}] FAILED\\nALM gate blocked execution (approval required).')
                    continue

            # Dedup: if another agent already created a proposal this request, skip
            if skill_name == 'alm_create_proposal' and _proposal_created_this_request[0]:
                _record_vortex_action(
                    'tool_call', source_agent=selected_agent, target_agent=skill_name,
                    status='skipped', context_parts=(message, skill_args), thread_id=conv_id,
                    details={'tool_name': skill_name, 'reason': 'proposal_already_created'},
                    source='fridays.tool',
                )
                lines.append(f'[skill:{skill_name}] SKIPPED\\nProposal already created this turn.')
                continue

            ok, out = skill_call(skill_name, args=skill_args, agent=selected_agent,
                                source_conv_id=conv_id if skill_name == 'alm_create_proposal' else None)
            _record_vortex_action(
                'tool_call',
                source_agent=selected_agent,
                target_agent=skill_name,
                status='completed' if ok else 'failed',
                context_parts=(message, skill_args),
                thread_id=conv_id,
                details={'tool_name': skill_name, 'trust_level': trust_level},
                source='fridays.tool',
            )
            if ok and skill_name == 'alm_create_proposal':
                _proposal_created_this_request[0] = True
            preview = str(out or '')[:3000]
            lines.append(f"[skill:{skill_name}] {'OK' if ok else 'FAILED'}\\n{preview}")

        return '\\n\\n'.join(lines)

    def _run_ghost_layer_chat(selected_agent, prompt, history, stage_cb=None):
        from claude_api import _load_api_key, CLAUDE_MODEL
        import anthropic
        import config as _config_mod
        from fridays.skills import call as skill_call

        def _emit_stage(text):
            if callable(stage_cb):
                try:
                    stage_cb(text, None)
                except Exception:
                    pass

        api_key = _load_api_key()
        if not api_key:
            return None, 0, 'ANTHROPIC_API_KEY not configured'

        # Dynamic system prompt lookup: try <NAME>_SYSTEM_PROMPT in config, fall back to DB
        _prompt_const = f'{selected_agent.upper()}_SYSTEM_PROMPT'
        base_system = getattr(_config_mod, _prompt_const, None)
        if not base_system:
            try:
                _db_conn = get_connection()
                _db_row = _db_conn.execute(
                    "SELECT system_prompt FROM agents WHERE name=?", (selected_agent,)
                ).fetchone()
                _db_conn.close()
                base_system = (_db_row['system_prompt'] or '') if _db_row else ''
            except Exception:
                base_system = ''
        if not base_system:
            base_system = getattr(_config_mod, 'TEN_SYSTEM_PROMPT', '')
        _emit_stage('loading ghost-layer memory')

        try:
            recent_memories = get_agent_memory(selected_agent, query='', limit=6)
            if recent_memories:
                mem_lines = []
                for row in recent_memories:
                    subj = str(row['subject'] or '').strip()[:120]
                    body = str(row['content'] or '').strip()[:400]
                    mem_lines.append(f'- [{subj}] {body}')
                memory_block = (
                    '\n\n=== Your recent memory (most important first) ===\n'
                    + '\n'.join(mem_lines)
                    + '\n=== End memory ===\n'
                    + 'Use this for continuity but do not narrate or repeat it verbatim.'
                )
                system_prompt = base_system.rstrip() + memory_block
            else:
                system_prompt = base_system
        except Exception:
            system_prompt = base_system

        informational_request = _chat_user_prompt_is_informational(message)
        if informational_request:
            system_prompt = system_prompt.rstrip() + _chat_read_only_guard(prefix_for_system_prompt=True)

        client = anthropic.Anthropic(api_key=api_key)

        def _run_skill_lines(cmds):
            def _route_shell_to_fs_readonly(shell_args):
                cmd = (shell_args or '').strip()
                if not cmd:
                    return None

                match = re.match(r'^ls(?:\s+-[a-zA-Z]+)?\s+(.+)$', cmd)
                if match:
                    return f'ls {match.group(1).strip()}'

                match = re.match(r'^cat\s+(.+)$', cmd)
                if match:
                    return f'read {match.group(1).strip()} 5000'

                match = re.match(r'^head\s+-n\s+(\d+)\s+(.+)$', cmd)
                if match:
                    return f'head {match.group(2).strip()} {match.group(1)}'

                match = re.match(r'^tail\s+-n\s+(\d+)\s+(.+)$', cmd)
                if match:
                    return f'tail {match.group(2).strip()} {match.group(1)}'

                return None

            lines = []
            for skill_name, skill_args in cmds:
                _emit_stage(f'executing skill: {skill_name}')
                effective_name = skill_name
                effective_args = skill_args
                if skill_name == 'shell':
                    mapped = _route_shell_to_fs_readonly(skill_args)
                    if mapped:
                        effective_name = 'fs_readonly'
                        effective_args = mapped

                if informational_request and effective_name != 'fs_readonly':
                    lines.append(
                        f'[skill:{effective_name}] SKIPPED\n'
                        'Watchdog read-only guard: status/informational prompts cannot run write, proposal, approval, or completion skills.'
                    )
                    continue

                if not can_user_invoke_skill(selected_agent, effective_name, default_allow=True):
                    lines.append(f'[skill:{effective_name}] FAILED\\nNot authorized for user {selected_agent}')
                    continue
                ok, out = skill_call(effective_name, args=effective_args, agent=selected_agent)
                preview = str(out or '')[:3000]
                lines.append(f"[skill:{effective_name}] {'OK' if ok else 'FAILED'}\\n{preview}")
            return '\\n\\n'.join(lines)

        _emit_stage('sending model request')
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=(history[-10:] if history else []) + [{'role': 'user', 'content': prompt}],
        )
        first_answer = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens

        answer = first_answer
        skill_cmds = _extract_skill_lines_from_text(first_answer)
        if skill_cmds:
            _emit_stage('running requested skills')
            skill_results = _run_skill_lines(skill_cmds)
            followup_messages = (history[-10:] if history else []) + [
                {'role': 'user', 'content': prompt},
                {'role': 'assistant', 'content': first_answer},
                {
                    'role': 'user',
                    'content': (
                        'Executed skill outputs are below. Use these concrete results to produce your final answer. '
                        'Do not ask to run the same commands again in this response.\\n\\n'
                        + skill_results
                    ),
                },
            ]
            _emit_stage('synthesizing final answer')
            second = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=followup_messages,
            )
            answer = second.content[0].text + '\\n\\n---\\nExecuted skill output:\\n' + skill_results
            tokens += second.usage.input_tokens + second.usage.output_tokens

        _emit_stage('persisting response memory')
        save_agent_memory(
            agent_name=selected_agent,
            subject=message[:100],
            content=answer,
            tags='chat,shared-thread',
            importance=7,
            source='terminal_chat'
        )
        log_activity('terminal', f'{selected_agent}_chat', f'tokens={tokens} | {message[:80]}')
        return answer, tokens, None

    def _run_single_agent(selected_agent, prompt, history, reply_context, persistent_mode=False, stage_cb=None):
        execution_receipts = []
        runtime_nudges = 0

        def _duck_fast_check(text):
            t = (text or '').strip()
            if not t:
                return 'Sanity check: no claim provided.'
            cues = []
            if '?' in t:
                cues.append('contains a question; verify assumptions before acting')
            if any(k in t.lower() for k in ['always', 'never', 'guaranteed', 'impossible']):
                cues.append('absolute wording detected; high risk of overclaim')
            if any(k in t.lower() for k in ['maybe', 'probably', 'i think']):
                cues.append('uncertainty markers found; ask for evidence')
            if not cues:
                cues.append('no obvious red flags; still verify with one independent source')
            return 'Duck quick sanity: ' + '; '.join(cues) + '.'

        def _stage(text, eta_seconds=None):
            nonlocal runtime_nudges
            now = time.time()
            text_s = str(text or '')
            if text_s.startswith('execution_receipt:'):
                try:
                    receipt = json.loads(text_s.partition(':')[2])
                    if (
                        isinstance(receipt, dict)
                        and isinstance(receipt.get('skill'), str)
                        and receipt.get('status') in {'succeeded', 'failed', 'denied', 'skipped'}
                    ):
                        execution_receipts.append(receipt)
                    else:
                        _LOG.error('Invalid execution receipt from %s', selected_agent)
                except (TypeError, ValueError):
                    _LOG.exception('Could not parse execution receipt from %s', selected_agent)
                return
            if text_s.startswith('nudging for '):
                runtime_nudges += 1
            lower = text_s.lower()
            active_cues = (
                'generating',
                'synthesizing',
                'finalizing',
                'writing',
                'streaming',
                'thinking',
                'drafting',
                'sending model request',
            )
            if any(cue in lower for cue in active_cues):
                progress_state['last_progress_ts'] = now
                progress_state['active_progress_seen'] = True
            if 'generating' in lower and '·' in text_s:
                snippet = text_s.split('·', 1)[1].strip()
                if snippet:
                    progress_state['snippets'].append(snippet[-900:])
                    del progress_state['snippets'][:-8]
            if callable(stage_cb):
                try:
                    stage_cb(text_s, eta_seconds)
                except Exception:
                    pass

        response_text = None
        tokens_used = 0
        started_at = time.time()
        progress_state = {
            'last_progress_ts': started_at,
            'active_progress_seen': False,
            'snippets': [],
        }
        _record_vortex_action(
            'agent_execution',
            source_agent=relay_from or 'user',
            target_agent=selected_agent,
            status='started',
            context_parts=(prompt, history),
            thread_id=conv_id,
            details={'runtime_class': 'chat'},
        )
        executor = _CHAT_WORKER_EXECUTOR
        est_eta = _chat_eta_seconds(selected_agent)

        # ── Circuit breaker: fast-fail if agent is tripped ───────────────────
        if _CB_AVAILABLE:
            _cb_ok_disp, _cb_reason = _cb_check(selected_agent)
            if not _cb_ok_disp:
                _trace(conv_id, selected_agent, 'error', f'circuit_open: {_cb_reason}')
                _record_vortex_action(
                    'agent_execution', source_agent=relay_from or 'user',
                    target_agent=selected_agent, status='failed',
                    context_parts=(prompt, history), thread_id=conv_id,
                    details={'reason': 'circuit_open'},
                )
                return _cb_reason, 0, int((time.time() - started_at) * 1000)
            _hp_ok, _hp_detail = _cb_probe(selected_agent)
            if not _hp_ok:
                _cb_fail(selected_agent, _hp_detail)
                _trace(conv_id, selected_agent, 'error', f'health_probe_fail: {_hp_detail}')
                _record_vortex_action(
                    'agent_execution', source_agent=relay_from or 'user',
                    target_agent=selected_agent, status='failed',
                    context_parts=(prompt, history), thread_id=conv_id,
                    details={'reason': 'health_probe_failed'},
                )
                return (
                    f'[{selected_agent}] is unreachable ({_hp_detail}). '
                    'Check that the service is running and try again.'
                ), 0, int((time.time() - started_at) * 1000)

        # ── A.2.3: Auto-reroute if target agent is busy/down ────────────────
        _original_agent = selected_agent
        if auto_relay:
            try:
                from utils.agent_coordination import check_and_reroute
                _coord_agent, _coord_rerouted, _coord_reason = check_and_reroute(
                    selected_agent, exclude={'ghost', 'user'}
                )
                if _coord_rerouted and _coord_agent:
                    _trace(conv_id, selected_agent, 'reroute',
                           f'{selected_agent}→{_coord_agent}: {_coord_reason}')
                    selected_agent = _coord_agent
                    est_eta = _chat_eta_seconds(selected_agent)
            except Exception:
                pass  # coordination unavailable — proceed with original target

        local_timeout = _chat_agent_timeout_seconds(selected_agent, persistent_mode)

        def _partial_self_handoff(reason):
            elapsed = int(time.time() - started_at)
            snippets = [s for s in progress_state.get('snippets') or [] if s]
            if snippets:
                observed = '\n\n'.join(f'- {s}' for s in snippets[-4:])
            else:
                observed = '- The agent was still reporting active generation, but no safe partial text was captured.'
            return (
                f'[{selected_agent}] reached the handoff deadline after {elapsed}s while still showing active progress.\n\n'
                'Partial output observed before handoff:\n'
                f'{observed}\n\n'
                'SELF-HANDOFF:\n'
                f'- Current status: {reason}; active progress was observed, so this was not treated as a dead stall.\n'
                '- Next action: continue from the partial output above and produce the final answer in the next chat window.\n'
                '- Files/tables touched: none by the timeout controller.\n'
                '- Risk: the previous local runner may have been stopped to free the model slot; verify any unfinished action before applying changes.\n'
                f'- Continue prompt: Continue {selected_agent}\'s previous answer from thread #{conv_id}, using the partial output above as context, and finish with concise next steps.'
            )

        def _await_agent_future(future, *, text_only=False):
            poll_seconds = 5.0
            idle_stall_seconds = 300.0
            local_runtime = selected_agent in _all_local_ollama_chat_agents()
            while True:
                try:
                    return future.result(timeout=poll_seconds)
                except FuturesTimeoutError:
                    now = time.time()
                    elapsed = now - started_at
                    idle = now - float(progress_state.get('last_progress_ts') or started_at)
                    if elapsed < float(local_timeout):
                        continue
                    active_recently = (
                        bool(progress_state.get('active_progress_seen'))
                        and idle <= idle_stall_seconds
                    )
                    should_handoff = bool(persistent_mode and local_runtime)
                    if active_recently or should_handoff:
                        if active_recently:
                            handoff_stage = 'handoff deadline reached with active generation'
                            handoff_reason = (
                                f'deadline {int(local_timeout)}s reached with heartbeat idle {int(idle)}s'
                            )
                        else:
                            handoff_stage = 'handoff deadline reached without fresh heartbeat'
                            handoff_reason = (
                                f'deadline {int(local_timeout)}s reached; no generation heartbeat for {int(idle)}s'
                            )
                        _trace(
                            conv_id,
                            selected_agent,
                            'handoff',
                            f'local handoff after {int(elapsed)}s idle={int(idle)}s active={active_recently}',
                        )
                        _stage(handoff_stage, 0)
                        try:
                            future.cancel()
                        except Exception:
                            pass
                        try:
                            if local_runtime:
                                _chat_try_hard_kill_local_agent(selected_agent)
                        except Exception:
                            pass
                        handoff_text = _partial_self_handoff(handoff_reason)
                        return handoff_text if text_only else (handoff_text, 0)
                    raise

        def _agent_stage_cb(stage_text, eta_seconds=None):
            _stage(stage_text, est_eta if eta_seconds is None else eta_seconds)

        effective_prompt = _build_local_agent_prompt(selected_agent, prompt, message, reply_context, conv_id=conv_id, auto_relay=auto_relay)
        effective_prompt = apply_local_chat_profile(
            agent_name=selected_agent,
            base_prompt=effective_prompt,
            deadline_seconds=local_timeout,
            auto_relay=auto_relay,
            informational_request=_chat_user_prompt_is_informational(message),
            execution_confirmation=_is_execution_confirmation(message),
        )
        _stage('queued', est_eta)
        # Live web lookup for factual/current questions so local models cite sources instead of guessing.
        if selected_agent in WEB_LOOKUP_AGENTS:
            effective_prompt = _with_live_web_context(effective_prompt, message, _stage, est_eta)

        # ── Resource gate — one Ollama model at a time, Eight exclusive ──────────
        if selected_agent in _local_ollama_chat_agents():
            try:
                from utils.resource_gate import acquire, release as rg_release
                _stage(f'waiting for model slot · {selected_agent}', est_eta)
                _rg_ok, _rg_reason = acquire(selected_agent, wait=True)
                if not _rg_ok:
                    raise RuntimeError(_rg_reason)
                _rg_acquired = True
            except ImportError:
                _rg_acquired = False
                rg_release = None
        else:
            _rg_acquired = False
            rg_release = None

        try:
            _trace(conv_id, selected_agent, 'dispatch', f'route={selected_agent} prompt_len={len(effective_prompt)}')
            if selected_agent in {'gemma', 'qwen', 'eight', 'seven', 'twenty', 'fred'} or is_worker_agent(selected_agent):
                # Route through agent .chat() directly — enables skills_loop
                if selected_agent == 'seven':
                    _stage('dispatching to Seven Runtime · seven', est_eta)
                else:
                    _stage(f'dispatching to local ollama · {selected_agent}', est_eta)
                try:
                    import importlib
                    _mod = importlib.import_module(f'agents.{selected_agent}.{selected_agent}_agent')
                except Exception as _imp_err:
                    response_text = f'[{selected_agent}] module failed to load: {_imp_err}'
                else:
                    if selected_agent == 'seven':
                        future = executor.submit(
                            _mod.chat,
                            effective_prompt,
                            history,
                            _agent_stage_cb,
                            conv_id,
                        )
                    else:
                        future = executor.submit(_run_in_conversation, conv_id, _mod.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or f'[{selected_agent} unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent in {'librarian', 'duck', 'sniffles'}:
                # Utility agents — no .chat() module; use orchestrator
                _model_name = orchestrator.AGENTS.get(selected_agent, selected_agent)
                if selected_agent in {'duck', 'sniffles'}:
                    _stage(f'building audit context · {_model_name}', est_eta)
                else:
                    _stage(f'preparing prompt · {_model_name}', est_eta)
                future = executor.submit(orchestrator.ask_agent, selected_agent, effective_prompt, allow_skills=True)
                _stage(f'generating · {_model_name}', est_eta)
                response_text = _await_agent_future(future, text_only=True)
                tokens_used = orchestrator._LAST_EVAL_COUNT.get(selected_agent, 0)
                _stage('writing to memory', 0)
                _persist_local_agent_memory(selected_agent, message, response_text)
            elif selected_agent == 'mistral':
                _stage('dispatching to local ollama · mistral', est_eta)
                try:
                    from agents.mistral import mistral_agent
                except Exception as _imp_err:
                    response_text = f'[mistral] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(_run_in_conversation, conv_id, mistral_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[mistral] No response — check server logs.'
                    tokens_used = tokens or 0
            elif selected_agent == 'nine':
                _stage('dispatching to Groq', est_eta)
                try:
                    from agents.nine import nine_agent
                except Exception as _imp_err:
                    response_text = f'[nine] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(nine_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[nine unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'ten':
                _stage('dispatching to ghost datacenter', est_eta)
                try:
                    from agents.ten import copilot_agent
                except Exception as _imp_err:
                    response_text = f'[ten] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(copilot_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[ten] No response — check server logs.'
                    tokens_used = tokens or 0
            elif selected_agent == 'eleven':
                _stage('dispatching to ghost datacenter', est_eta)
                try:
                    from agents.eleven import grok_agent
                except Exception as _imp_err:
                    response_text = f'[eleven] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(grok_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[eleven unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'twelve':
                _stage('dispatching to ghost datacenter', est_eta)
                try:
                    from agents.twelve import twelve_agent
                except Exception as _imp_err:
                    response_text = f'[twelve] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(twelve_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[twelve unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'gemini':
                _stage('dispatching to Google Gemini', est_eta)
                try:
                    from agents.gemini import gemini_agent
                except Exception as _imp_err:
                    response_text = f'[gemini] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(gemini_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[gemini unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'scholar':
                _stage('dispatching to ghost datacenter', est_eta)
                try:
                    from agents.scholar import scholar_agent
                except Exception as _imp_err:
                    response_text = f'[scholar] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(scholar_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[scholar unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'seeker':
                _stage('dispatching to ghost datacenter', est_eta)
                try:
                    from agents.seeker import seeker_agent
                except Exception as _imp_err:
                    response_text = f'[seeker] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(seeker_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[seeker unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent in ('llama', 'llama3'):
                _stage('dispatching to llama3.2 (local)', est_eta)
                try:
                    from agents.llama import llama_agent
                except Exception as _imp_err:
                    response_text = f'[llama] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(llama_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[llama unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'phi3':
                _stage('dispatching to phi3:mini (local)', est_eta)
                try:
                    from agents.phi3 import phi3_agent
                except Exception as _imp_err:
                    response_text = f'[phi3] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(phi3_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[phi3 unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent in ('deepseek_local', 'deepseek-local'):
                _stage('dispatching to deepseek-r1:7b (local)', est_eta)
                try:
                    from agents.deepseek_local import deepseek_local_agent
                except Exception as _imp_err:
                    response_text = f'[deepseek-local] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(deepseek_local_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[deepseek-local unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'lmstudio':
                _stage('dispatching to LM Studio (local)', est_eta)
                try:
                    from agents.lmstudio import lmstudio_agent
                except Exception as _imp_err:
                    response_text = f'[lmstudio] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(lmstudio_agent.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[lmstudio unavailable — is LM Studio running?]'
                    tokens_used = tokens or 0
            elif selected_agent == 'ghost_coder':
                _stage('dispatching to Ghost Coder', est_eta)
                try:
                    from agents.ghost_coder import ghost_coder_agent
                except Exception as _imp_err:
                    response_text = f'[ghost_coder] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(ghost_coder_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[ghost_coder unavailable]'
                    tokens_used = tokens or 0
            elif selected_agent == 'nineteen':
                _stage('dispatching to o4-mini (GitHub Models)', est_eta)
                try:
                    from agents.nineteen import nineteen_agent
                except Exception as _imp_err:
                    response_text = f'[nineteen] module failed to load: {_imp_err}'
                else:
                    future = executor.submit(nineteen_agent.chat, effective_prompt, history, _agent_stage_cb, conv_id)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or '[nineteen unavailable]'
                    tokens_used = tokens or 0
            else:
                # Dynamic dispatch — any agent with agents/<name>/<name>_agent.py auto-routes here
                import importlib
                try:
                    mod = importlib.import_module(f'agents.{selected_agent}.{selected_agent}_agent')
                    _stage(f'dispatching to {selected_agent}', est_eta)
                    future = executor.submit(mod.chat, effective_prompt, history, _agent_stage_cb)
                    answer, tokens = _await_agent_future(future)
                    response_text = answer or f'[{selected_agent} unavailable]'
                    tokens_used = tokens or 0
                except ModuleNotFoundError:
                    response_text = f'[{selected_agent}] agent module not found — bootstrap may be incomplete'
                except Exception as _dyn_err:
                    response_text = f'[{selected_agent}] error: {_dyn_err}'
            _stage('finalizing answer', 0)
            if _chat_error_should_disable_agent(response_text):
                _disable_agent_for_chat(selected_agent, response_text)
                response_text = (
                    f'[{selected_agent}] was taken offline because it reported a runtime/auth failure. '
                    'Re-enable it from the Agents tile after checking credentials, timeout, context, or model settings.\n\n'
                    + (response_text or '')
                )
        except FuturesTimeoutError:
            _trace(conv_id, selected_agent, 'error', f'timeout after {local_timeout}s persistent={persistent_mode}')
            _stage('timed out waiting for completion', 0)
            if _CB_AVAILABLE:
                _cb_fail(selected_agent, f'timeout after {local_timeout}s')
            if persistent_mode:
                _disable_agent_for_chat(selected_agent, f'timed out after {local_timeout}s')
                _record_vortex_action(
                    'agent_execution', source_agent=relay_from or 'user',
                    target_agent=selected_agent, status='timed_out',
                    context_parts=(effective_prompt, history), thread_id=conv_id,
                    details={'timeout_seconds': local_timeout},
                )
                raise RuntimeError(f'{selected_agent} timed out after {local_timeout}s')
            if selected_agent == 'duck':
                response_text = _duck_fast_check(message)
            else:
                response_text = (
                    f'[{selected_agent}] is taking longer than expected. '
                    'Try again in a moment or switch to another agent.'
                )
        finally:
            # Always release the resource gate slot, even on error or timeout
            if _rg_acquired and rg_release:
                try:
                    rg_release(selected_agent)
                except Exception:
                    pass
        if response_text is None:
            response_text = f'[{selected_agent}] no response'

        # ── Auto-relay enforcement ─────────────────────────────────────────────
        # When auto_relay is OFF, strip any agent-routing language the model
        # produced anyway. This is the hard gate — prompt hints alone are not
        # reliable enough with API models.
        if not auto_relay:
            response_text = _strip_relay_routing(response_text)

        # Always strip the leaked '[Auto Relay: ENABLED|DISABLED]' banner —
        # it is a system-prompt artefact echoed back by some local agents
        # (Gemma, LLaMA) and bleeds into creative output. Never user-facing.
        response_text = _strip_auto_relay_banner(response_text)
        response_text = _strip_placeholder_relay(response_text)
        if data.get('local_only') is True:
            response_text += _chat_execution_breakdown(execution_receipts, runtime_nudges)

        elapsed_ms = int((time.time() - started_at) * 1000)
        if _CB_AVAILABLE:
            _cb_ok(selected_agent)
        _trace(conv_id, selected_agent, 'complete', f'tokens={tokens_used} elapsed={elapsed_ms}ms len={len(response_text or "")}')

        # Prepend a visible reroute notice so the user knows which agent actually responded
        if _original_agent != selected_agent:
            response_text = (
                f'⚡ *Rerouted from {_original_agent} → {selected_agent}* '
                f'({_original_agent} was unavailable)\n\n'
                + (response_text or '')
            )

        _record_vortex_action(
            'agent_execution',
            source_agent=relay_from or 'user',
            target_agent=selected_agent,
            status=(
                'timed_out' if _chat_response_is_timeout_handoff(response_text, tokens_used)
                else 'failed' if _chat_error_should_disable_agent(response_text)
                else 'completed'
            ),
            context_parts=(effective_prompt, history),
            thread_id=conv_id,
            details={'elapsed_ms': elapsed_ms, 'tokens': tokens_used, 'response_length': len(response_text or '')},
        )
        return response_text, tokens_used, elapsed_ms

    selected_model = APEX_AGENT['model']  # bootstrap model for storage recovery only
    try:
        continuity = ContinuityChat()
        continuing_recovery = continuity.owns_id(requested_conv_id)
        fault = primary_chat_fault
        if continuing_recovery and not fault and apex_lane:
            from core.apex_permissions import autonomous_writes_allowed, resume_recovery_with_tools
            recovery_operator = _tool_operator()
            if recovery_operator and autonomous_writes_allowed(recovery_operator[0]):
                resumed = resume_recovery_with_tools(
                    continuity, requested_conv_id, recovery_operator[0], get_connection)
                requested_conv_id = resumed['conversation_id']
                data['conversation_id'] = requested_conv_id
                continuing_recovery = False
        from core import llm

        from core.apex_tools import TURN_SECONDS
        apex_deadline = time.monotonic() + TURN_SECONDS

        def apex_model(model, messages):
            remaining = int(apex_deadline - time.monotonic())
            if remaining <= 0:
                raise RuntimeError('APEX turn deadline exceeded; inference not submitted')
            from core.apex_tools import response_format_for_turn
            from core.apex_context import APEX_REASONING_EFFORT, context_tokens, generation_budget
            output_tokens = generation_budget(messages) if apex_lane and not (fault or continuing_recovery) else 1800
            remaining = int(apex_deadline - time.monotonic())
            if remaining <= 0:
                raise RuntimeError('APEX turn deadline exceeded during context budgeting; inference not submitted')
            options = {'num_ctx': context_tokens(), 'num_predict': output_tokens,
                       'require_complete_output': apex_lane and not (fault or continuing_recovery)}
            if apex_lane and not (fault or continuing_recovery):
                options['reasoning_effort'] = APEX_REASONING_EFFORT
            return llm.chat_via_gateway(
                model, messages, temperature=0.2, idle_timeout_s=min(60, remaining), absolute_timeout_s=remaining,
                queue_timeout_s=1,
                options=options,
                response_format=response_format_for_turn() if apex_lane and not (fault or continuing_recovery) else None,
            )

        def _offline_response(exc, conversation_id=None, *, recovery=False):
            _LOG.error('APEX offline: %s', exc)
            payload = {
                'ok': False, 'state': STATE_OFFLINE, 'agent': APEX_AGENT['name'],
                'model': selected_model, 'storage_degraded': bool(recovery),
                'response': f"APEX is offline: {exc}",
                'routed_from': routed_from,
            }
            if conversation_id is not None:
                payload['conversation_id'] = conversation_id
            return jsonify(payload), 503

        if fault or continuing_recovery:
            if data.get('local_only') is not True or relay_from:
                return jsonify({
                    'ok': False, 'state': STATE_RECOVERY, 'storage_degraded': True,
                    'response': 'Primary chat storage is unavailable. Recovery chat permits local-only, non-relayed messages.',
                }), 503
            rows = {row['name'].lower(): row for row in routable_rows}
            selected = [rows[name] for name in normalized_agents if name in rows]
            if len(selected) != len(normalized_agents) or not selected:
                return jsonify({'ok': False, 'state': STATE_RECOVERY, 'response': 'No registered local recovery agent available.'}), 503

            try:
                result = continuity.send(
                    data, selected, identity['effective_user'],
                    fault or 'Continuing a separately persisted recovery thread.', apex_model)
            except ApexOffline as exc:
                return _offline_response(exc, recovery=True)
            result['routed_from'] = routed_from
            _sse_chat(result['conversation_id'], APEX_AGENT['name'], 'completed',
                      state=STATE_RECOVERY, model=selected_model)
            return jsonify(result)
        conv_id = None
        if requested_conv_id is not None:
            try:
                parsed = int(requested_conv_id)
                conn = get_connection()
                try:
                    exists = conn.execute('SELECT 1 FROM conversations WHERE id=?', (parsed,)).fetchone()
                finally:
                    conn.close()
                if exists:
                    conv_id = parsed
            except Exception:
                conv_id = None

        if conv_id is None and not force_new_thread:
            conn = get_connection()
            try:
                latest = conn.execute(
                    "SELECT id FROM conversations WHERE source='terminal-ui' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if latest:
                conv_id = int(latest['id'])

        if conv_id is None:
            title_agents = ','.join(normalized_agents[:2])
            _env_tag = os.environ.get('SWARM_ENV', 'prod').upper()
            conv_id = new_conversation(f'{title_agents}: {message[:90]}', source=f'terminal-ui:{_env_tag}')

        if not relay_from:
            _log_human_ghost_thought(message, identity, conversation_id=conv_id, current_user=current_user)

        to_agent = normalized_agents[0] if len(normalized_agents) == 1 else ','.join(normalized_agents)
        msg_sender = relay_from if relay_from else 'user'
        log_message(conv_id, msg_sender, message, to_agent=to_agent, message_type='relay' if relay_from else 'chat')
        operator_message_id = None
        if apex_lane and not relay_from:
            _id_conn = get_connection()
            try:
                _row = _id_conn.execute(
                    "SELECT MAX(id) FROM messages WHERE conversation_id=? AND from_agent=?",
                    (conv_id, msg_sender)).fetchone()
                operator_message_id = _row[0] if _row else None
                if operator_message_id:
                    from core import hb_tasks
                    hb_tasks.ensure_schema(_id_conn)
                    reply_task = None if data.get('task_id') else hb_tasks.reply_target(_id_conn, conv_id, message)   # B39
                    # Owner 14 Nov: a remark or a go-ahead is not new work (core/hb_owner_intent): it joins "Chat with JD";
                    # a go-ahead also starts HB's queue driver (core/hb_queue).
                    from core import hb_owner_intent
                    owner_intent = None if (data.get('task_id') or reply_task or data.get('step_id')) else hb_owner_intent.classify(message)
                    try:   # owner 14 Nov: JD's next line tells HB whether an agent's question back was needed
                        from core.hb_question_check import resolve as resolve_question
                        resolve_question(_id_conn, conv_id, message, owner_intent)
                    except Exception:
                        pass
                    if owner_intent:
                        tracked_task = hb_owner_intent.chat_task(_id_conn, conv_id, operator_message_id)
                        hb_tasks.event(_id_conn, tracked_task, 'hummingbird', 'owner_intent', {'intent': owner_intent, 'message_id': operator_message_id})
                        if owner_intent == 'remark':
                            try:   # owner 14 Nov: negative feedback is "try better next time", recorded; nothing stops
                                from core.hb_owner_intent import _FEELING
                                if _FEELING.search(message):
                                    from core import hb_merits
                                    hb_merits.try_better(_id_conn, message)
                            except Exception:
                                pass
                        if owner_intent == 'drive' and (current_user or {}).get('role') == 'owner':
                            from core import hb_queue
                            _drive_text = hb_queue.drive_on(_id_conn, f"{current_user.get('username') or 'owner'} via chat go-ahead", conv_id, operator_message_id)
                            _id_conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) "
                                             "VALUES (?,'hummingbird','user',?,'response',0)", (conv_id, _drive_text))
                    else:
                        tracked_task = hb_tasks.bind(_id_conn,conv_id,operator_message_id,task_id=data.get('task_id') or reply_task,project_id=data.get('project_id'),step_id=data.get('step_id'))
                    bound_task = tracked_task
                    from core.hb_inline_tasks import implementation_request,start as start_inline
                    operator=_tool_operator()
                    if operator and not owner_intent and implementation_request(message,data.get('task_id')):
                        from core.apex_permissions import autonomous_writes_allowed
                        g.hb_inline_execution=start_inline(_id_conn,tracked_task,owner=operator[0],allow_writes=autonomous_writes_allowed(operator[0]))
                    _id_conn.commit()
            finally:
                _id_conn.close()

        if normalized_agents == ['watchdog']:
            clarify = (
                'What do you mean? I need a target agent or a more specific action before I route this. '
                'Name the agent, thread, or system area you want checked.'
            )
            log_message(conv_id, 'watchdog', clarify, to_agent='user', message_type='response')
            try:
                _trace(conv_id, 'watchdog', 'clarification', 'no explicit agent and ambiguous prompt')
            except Exception:
                pass
            return jsonify({
                'ok': True,
                'mode': 'clarification',
                'agent': 'watchdog',
                'response': clarify,
                'tokens': 0,
                'responses': [{
                    'agent': 'watchdog',
                    'response': clarify,
                    'tokens': 0,
                    'elapsed_ms': 0,
                }],
                'agents': ['watchdog'],
                'conversation_id': conv_id,
            })

        parsed_skill = _parse_chat_skill_command(message)
        if parsed_skill and apex_lane:
            _LOG.warning('APEX lane refused legacy SKILL invocation: %s', parsed_skill[0])
            return jsonify({
                'ok': False, 'state': STATE_OK, 'conversation_id': conv_id,
                'response': 'APEX exposes only structured read-only repository tools; legacy SKILL execution is disabled.',
            }), 403
        if parsed_skill:
            from fridays.skills import call as skill_call, REGISTRY as SKILL_REGISTRY

            skill_name, skill_args = parsed_skill
            meta = SKILL_REGISTRY.get(skill_name)

            if not meta:
                known = ', '.join(sorted(SKILL_REGISTRY.keys()))
                skill_ok = False
                skill_output = f"Unknown skill: {skill_name!r}. Known skills: {known}"
            else:
                effective_user = identity['effective_user']
                if not can_user_invoke_skill(effective_user, skill_name, default_allow=True):
                    return jsonify({
                        'ok': False,
                        'error': f'user {effective_user} is not authorized for skill {skill_name}'
                    }), 403
                trust_level = int(meta.get('trust_level', 0) or 0)
                if trust_level >= 1 and skill_name not in {'ticket_create', 'alm_create_proposal'}:
                    gate = _alm_gate_or_response(data, f'chat_skill_{skill_name}')
                    if gate:
                        return gate
                caller_agent = effective_user
                skill_ok, skill_output = skill_call(skill_name, args=skill_args, agent=caller_agent)
                _record_vortex_action(
                    'tool_call',
                    source_agent=caller_agent,
                    target_agent=skill_name,
                    status='completed' if skill_ok else 'failed',
                    context_parts=(skill_args,),
                    thread_id=conv_id,
                    details={'tool_name': skill_name, 'trust_level': trust_level},
                    source='fridays.tool',
                )

            skill_response = (
                f"[skill:{skill_name}] {'OK' if skill_ok else 'FAILED'}\n"
                f'{skill_output}'
            )
            log_message(conv_id, 'fridays', skill_response, to_agent='user', message_type='response')

            return jsonify({
                'ok': True,
                'mode': 'skill',
                'skill': {
                    'name': skill_name,
                    'args': skill_args,
                    'ok': skill_ok,
                },
                'identity': {
                    'acting_user': identity['acting_user'],
                    'proxy_as': identity['proxy_as'],
                    'effective_user': identity['effective_user'],
                },
                'agent': 'fridays',
                'response': skill_response,
                'tokens': 0,
                'responses': [{
                    'agent': 'fridays',
                    'response': skill_response,
                    'tokens': 0,
                    'elapsed_ms': 0,
                }],
                'agents': normalized_agents,
                'conversation_id': conv_id,
            })

        if history_mode == 'none':
            thread_rows = []
        elif history_mode == 'recent':
            thread_rows = _fetch_chat_thread_rows(conv_id, limit=history_limit)
        else:
            thread_rows = _fetch_chat_thread_rows(conv_id, limit=60)
        if bound_task:
            from core import hb_tasks
            with __import__('contextlib').closing(get_connection()) as task_conn:
                thread_rows=hb_tasks.history(task_conn,bound_task)
        history = _chat_history_from_rows(thread_rows)

        if apex_lane:
            from core.apex_tools import run_apex_tools, receipt_text
            from core.apex_context import prepare_context, budget_receipts
            from core.chat_continuity import apex_request_history
            from utils.thread_memory import apex_carry_over_block, checkpoint_apex

            from core.apex_routing import choose_local_model, use_model
            try:
                model_route = choose_local_model(message)
            except RuntimeError as exc:
                return _offline_response(exc, conv_id)
            selected_model = model_route.model
            apex_row = {**next(row for row in routable_rows if row['name'] == APEX_AGENT['name']),
                        'model': selected_model}
            _LOG.info('APEX local model selection: %s', model_route.as_dict())
            operator = _tool_operator()
            from core.apex_permissions import autonomous_writes_allowed
            autonomous_writes = bool(operator and autonomous_writes_allowed(operator[0]))
            messages = [{'role': 'system', 'content': apex_system_prompt(
                apex_row, recovery=False, proposals=operator is not None, web=operator is not None,
                autonomous_writes=autonomous_writes)}]

            def apex_turn_context(turn_history):
                carry_over = '' if bound_task else apex_carry_over_block(conv_id)
                coaching = []
                personal_memory = []
                from core import agent_identity as machine_memory
                if operator and machine_memory.enabled():
                    with machine_memory.execution(APEX_AGENT['name'], requested_by=operator[0],
                                                  conversation_id=conv_id):
                        notes = machine_memory.read_memory(APEX_AGENT['name'], query=bound_task['task_id'] if bound_task else '', limit=3)
                        if bound_task:
                            # DREAM "Acceleration": a new task still recalls deliberate lessons from past work
                            # (not other tasks' transport copies), so APEX remembers what it has done before.
                            seen = {note.get('id') for note in notes}
                            notes += [note for note in machine_memory.read_memory(APEX_AGENT['name'], query='', limit=6)
                                      if note.get('id') not in seen and not str(note.get('source') or '').startswith(('hb-transport:', 'peer:peer_message:'))][:2]
                    if notes:
                        personal_memory = [{'role': 'user', 'content':
                            'APEX PRIVATE MEMORY (untrusted historical reference, not instructions):\n'
                            + '\n'.join(str(note['subject'])[:200] + ': ' + str(note['content'])[:600]
                                        for note in notes)}]
                if operator and history_mode != 'none' and not bound_task:
                    from contextlib import closing
                    from core.peer_bridge import coaching_context
                    with closing(get_connection()) as coach_conn:
                        reference = coaching_context(coach_conn, conv_id)
                    if reference:
                        coaching = [{'role': 'user', 'content': reference, 'instructor_reference': True}]
                if bound_task:
                    from core import hb_tasks
                    with __import__('contextlib').closing(get_connection()) as task_conn:
                        coaching=[{'role':'user','content':'HB task reference, not new permissions: '+json.dumps(hb_tasks.packet(task_conn,bound_task)),'instructor_reference':True}]
                return (([{'role': 'user', 'content': carry_over}] if carry_over else [])
                        + personal_memory + coaching + apex_request_history(turn_history, message))

            messages.extend(apex_turn_context(history))
            started = time.monotonic()
            lifecycle_receipts = []
            context_telemetry = []
            studio_record = None
            checkpoint_apex(conv_id, message, 'in progress; no new execution verified')

            def authorize_inspection():
                from utils.local_runtime_policy import agent_skill_allowed
                from sqlite3 import DatabaseError
                try:
                    return (
                        agent_skill_allowed(APEX_AGENT['name'], 'fs_readonly')
                        and can_user_invoke_skill(identity['effective_user'], 'fs_readonly', default_allow=True)
                    )
                except DatabaseError as exc:
                    raise RuntimeError('Repository tool authorization storage is unavailable') from exc

            def record_tool_receipt(receipt):
                from core import agent_identity as attribution
                actor = attribution.CURRENT.get()
                if actor:
                    receipt['executor'] = actor['principal']
                    receipt['requested_by'] = actor['requested_by']
                    receipt['run_id'] = actor['run_id']
                    receipt['model'] = actor['model']
                    attribution.event(actor, receipt['id'], receipt['tool'], receipt['status'],
                                      result={'transaction_id': receipt.get('transaction_id')})
                log_message(conv_id, APEX_AGENT['name'], receipt_text(receipt),
                            to_agent='user', message_type='tool_result')
                lifecycle_receipts.append(receipt)
                if bound_task:
                    from core import hb_tasks
                    with __import__('contextlib').closing(get_connection()) as task_conn,task_conn:
                        hb_tasks.event(task_conn,bound_task,'apex',
                            'mutation' if receipt.get('tool') in {'propose_patch','propose_write_file'} and receipt.get('status') in {'succeeded','executed'} else 'tool_result',
                            {**{key:receipt[key] for key in ('id','tool','status','output','transaction_id') if key in receipt},
                             'arguments':__import__('core.hb_learning',fromlist=['safe_arguments']).safe_arguments(receipt.get('arguments'))})
                    hb_tasks.flush_memory()

                record_studio('tool_receipt')
                checkpoint_apex(conv_id, message, 'in progress', lifecycle_receipts)
                # Outputs stay in the authenticated thread, not the broadcast SSE feed.
                _sse_chat(conv_id, APEX_AGENT['name'], 'tool_receipt',
                          receipt={key: receipt[key] for key in ('id', 'tool', 'status', 'truncated')})

            def web_tool(args):
                from lib.search.internet import search_provider
                from utils.local_runtime_policy import agent_skill_allowed
                from sqlite3 import DatabaseError
                if not operator or _tool_operator() != operator:
                    raise PermissionError('Authenticated owner session required for web search')
                try:
                    allowed = (
                        agent_skill_allowed(APEX_AGENT['name'], 'web_search')
                        and can_user_invoke_skill(identity['effective_user'], 'web_search', default_allow=True)
                    )
                except DatabaseError as exc:
                    raise RuntimeError('Web search authorization storage is unavailable') from exc
                if not allowed:
                    raise PermissionError('Web search is not authorized')
                return search_provider(args['query'], args['provider'])

            def propose_tool(repository, tool, args):
                from core.tool_approval import APPROVALS, ApprovalConflict
                if not operator or _tool_operator() != operator:
                    raise PermissionError('Authenticated owner session required for proposals')
                owner, session_id = operator
                from core.apex_permissions import WRITE_TOOLS, execute_authorized_write
                if tool in WRITE_TOOLS and autonomous_writes:
                    def authorize_write(_tool):
                        return (_tool_operator() == operator
                                and can_user_invoke_skill(owner, 'fs_write', default_allow=True))
                    return execute_authorized_write(
                        APPROVALS, repository, tool, args, operator, conv_id, authorize_write)
                try:
                    durable_operation=None
                    if bound_task and tool in {'propose_patch','propose_write_file'}:
                        from core import hb_task_operations,agent_identity as identity_runtime
                        with __import__('contextlib').closing(get_connection()) as operation_conn,operation_conn:
                            transaction,durable_operation,reused=hb_task_operations.prepare_owner_proposal(
                                operation_conn,APPROVALS,repository,bound_task,tool,args,owner,session_id,conv_id,
                                (identity_runtime.CURRENT.get() or {}).get('execution_id'))
                        if reused:return reused
                    else:
                        transaction = APPROVALS.propose(repository, tool, args, owner, session_id, conv_id)
                except ApprovalConflict as exc:
                    raise ValueError(str(exc)) from exc
                waiting = time.monotonic()
                try:
                    _sse_module().publish('tool_approval_pending', transaction.public(), audience=session_id)
                    result = APPROVALS.wait(transaction)
                    if durable_operation:
                        with __import__('contextlib').closing(get_connection()) as operation_conn,operation_conn:
                            result=hb_task_operations.finish(operation_conn,durable_operation,result)
                except Exception:
                    APPROVALS.cancel(transaction, 'Proposal delivery failed; no execution authorized')
                    raise
                finally:
                    nonlocal apex_deadline
                    apex_deadline += time.monotonic() - waiting
                return result

            def studio_tool(tool, args):
                from core.apex_studio import save_handoff, read_handoff
                from sqlite3 import DatabaseError
                if not operator or _tool_operator() != operator:
                    raise PermissionError('Authenticated owner session required for Studio continuity')
                owner, _ = operator
                try:
                    from core.hb_agent_tools import READ_TOOLS, WRITE_TOOLS, call
                    if tool in READ_TOOLS | WRITE_TOOLS:
                        return call(tool,args)
                    if tool in {'backlog_list','runtime_status','archive_status','archive_ingest','archive_mirror_pause','archive_mirror_resume','archive_mirror_curate','memory_search','memory_save','terminal_run'}:
                        from core.hb_workflow import call_control
                        return call_control(tool,args)
                    if tool == 'knowledge_search':
                        from core.apex_knowledge import search
                        if set(args) != {'query'}:
                            raise ValueError('knowledge_search accepts only query')
                        return search(args['query'])
                    if tool == 'knowledge_read':
                        from core.apex_knowledge import read
                        if set(args) - {'document_id', 'offset'} or 'document_id' not in args:
                            raise ValueError('knowledge_read requires document_id and optional offset')
                        return read(args['document_id'], args.get('offset', 0))
                    if tool == 'ask_instructor':
                        from contextlib import closing
                        from core import peer_bridge as peers
                        if set(args) != {'peer', 'question', 'context'}:
                            raise ValueError('ask_instructor requires peer, question and context')
                        try:
                            with closing(get_connection()) as peer_conn, peer_conn:
                                result = peers.request_help(peer_conn, conv_id, **args)
                        except peers.PeerError as exc:
                            raise ValueError(str(exc)) from None
                        _sse_chat(conv_id, 'apex', 'instructor_requested', recipient=result['recipient'])
                        return result
                    if tool == 'studio_evidence_get':
                        from core.apex_evidence import read_evidence
                        if set(args) != {'evidence_id'}:
                            raise ValueError('studio_evidence_get accepts only evidence_id')
                        return read_evidence(conv_id, owner, args['evidence_id'])
                    if tool == 'alm_step_get':
                        from core.apex_alm import read_step
                        if set(args) != {'step_id'}:
                            raise ValueError('alm_step_get accepts only step_id')
                        return read_step(args['step_id'])
                    if tool == 'studio_resume':
                        if set(args) - {'offset'}:
                            raise ValueError('studio_resume accepts only offset')
                        return read_handoff(conv_id, owner, offset=args.get('offset', 0), raw=False)
                    if tool not in {'studio_handoff', 'studio_capacity_handoff'} or set(args) != {'title', 'summary', 'tasks'}:
                        raise ValueError('studio_handoff requires title, summary and tasks')
                    return save_handoff(conv_id, owner, message, context=messages,
                                        receipts=lifecycle_receipts,
                                        preserve_tasks=tool == 'studio_capacity_handoff', **args)
                except DatabaseError as exc:
                    _LOG.exception('APEX Studio continuity storage failed')
                    raise RuntimeError(f'APEX Studio continuity storage failed: {exc}') from exc

            def record_studio(state, response='', tokens=0):
                nonlocal studio_record
                from core.apex_studio import record_turn
                from sqlite3 import DatabaseError
                if not operator:
                    return
                if _tool_operator() != operator:
                    raise PermissionError('Authenticated operator session changed during Studio recording')
                try:
                    studio_record = record_turn(
                        conv_id, operator[0], message, messages, lifecycle_receipts,
                        state=state, response=response, tokens=tokens, telemetry=context_telemetry,
                        message_id=operator_message_id)
                except DatabaseError as exc:
                    _LOG.exception('APEX automatic Studio recording failed')
                    raise RuntimeError(f'APEX automatic Studio recording failed: {exc}') from exc

            def test_tool(args):
                if bound_task:
                    from core.hb_agent_tools import call
                    return call('run_tests',args)
                from core.apex_test_runner import run_tests
                if not operator or _tool_operator() != operator:
                    raise PermissionError('Authenticated owner session required for test runs')
                if isinstance(args, dict) and 'case_id' in args:
                    from core.apex_alm import run_recorded_tests
                    return run_recorded_tests(args, run_tests)
                return run_tests(args)

            history_pointer = None
            try:  # DOES: where compacted history can be read again (KC chat transcript + task record)
                from core.hb_kc_records import pointer as kc_pointer
                with __import__('contextlib').closing(get_connection()) as kc_conn:
                    history_pointer = kc_pointer(kc_conn, conv_id, bound_task['task_id'] if bound_task else None)
            except Exception:
                _LOG.exception('DOES history pointer unavailable')
            task_notes = []
            if bound_task:
                try:  # DREAM: HB's clipboard for this task (goal, done criteria, step, last failure, related work, method)
                    from core.hb_dream_method import card as dream_card
                    from core import hb_tasks as _dream_tasks
                    with __import__('contextlib').closing(get_connection()) as dream_conn:
                        task_notes.append({'role': 'user', 'content': dream_card(dream_conn, _dream_tasks.get(dream_conn, bound_task['task_id']))})
                except Exception:
                    _LOG.exception('DREAM clipboard unavailable')
                if history_pointer:
                    # Task turns only carry the task's latest messages; always say where the rest is saved.
                    from core.apex_context import POINTER_HEADER
                    task_notes.append({'role': 'user', 'content': POINTER_HEADER + history_pointer})
            messages[1:1] = task_notes

            def prepare_working_context(current):
                return prepare_context(current, archive_history=operator is not None,
                                       telemetry=context_telemetry.append, pointer=history_pointer)

            def prepare_tool_receipts(current, receipts):
                return budget_receipts(current, receipts, archive_history=operator is not None,
                                       telemetry=context_telemetry.append, pointer=history_pointer)

            def model_progress(event):
                stage = str(event.get('stage') or 'running').replace('_', ' ')
                _sse_chat(conv_id, APEX_AGENT['name'], 'running', model=selected_model,
                          stage=stage + ': ' + selected_model)

            queued_turn = []

            def wait_for_turn(position):
                queued_turn.append(position)
                _sse_chat(conv_id, APEX_AGENT['name'], 'queued', model=selected_model, position=position)

            from core.hb_process_lock import ProcessLock
            process_turn=ProcessLock('apex-turn')
            slot_held = _APEX_TURNS.acquire(APEX_QUEUE_SECONDS, on_wait=wait_for_turn)
            try:
                process_held=process_turn.acquire(APEX_QUEUE_SECONDS,on_wait=wait_for_turn) if slot_held else False
                if not slot_held or not process_held:
                    busy = (f'APEX was still busy with earlier turns after {APEX_QUEUE_SECONDS}s; your message '
                            'is saved in this thread but was not answered. Send it again when APEX is free.')
                    record_studio('blocked', busy)
                    checkpoint_apex(conv_id, message, f'blocked: {busy}', lifecycle_receipts)
                    _sse_chat(conv_id, APEX_AGENT['name'], 'failed', state='busy', error=busy)
                    return jsonify({
                        'ok': False, 'state': 'busy', 'agent': APEX_AGENT['name'],
                        'model': selected_model, 'conversation_id': conv_id,
                        'response': busy, 'routed_from': routed_from,
                    }), 503
                if queued_turn and history_mode != 'none':
                    # Queued behind another turn: include that turn's answer.
                    fresh_rows = _fetch_chat_thread_rows(
                        conv_id, limit=history_limit if history_mode == 'recent' else 60)
                    if bound_task:
                        from core import hb_tasks
                        with __import__('contextlib').closing(get_connection()) as task_conn:
                            fresh_rows=hb_tasks.history(task_conn,bound_task)
                    messages[1:] = apex_turn_context(_chat_history_from_rows(fresh_rows))
                    messages[1:1] = task_notes
                apex_deadline = time.monotonic() + TURN_SECONDS
                try:
                    record_studio('running')
                    if operator and not bound_task:
                        from core.apex_studio import working_state
                        # Archive only old context, never the latest operator request or in-loop receipts.
                        for old in messages[1:-1]:
                            if not old.get('instructor_reference'):
                                old['studio_archived'] = True
                        messages.insert(1, {'role': 'user', 'content': working_state(conv_id, operator[0])})
                    from core.agent_identity import execution
                    from core.hb_workflow import memory_snapshot, record_run
                    measured_started=time.monotonic()
                    measured_memory=memory_snapshot()
                    model_progress({'stage': 'running'})
                    with use_model(model_route, progress=model_progress), execution(APEX_AGENT['name'], model=selected_model,
                                   requested_by=operator[0] if operator else '', conversation_id=conv_id) as agent_run:
                        if agent_run and bound_task:
                            from core.hb_chat_controls import continuation as _continuation
                            from core import hb_tasks as _hb_tasks
                            with __import__('contextlib').closing(get_connection()) as _rev_conn:
                                _revision=_continuation(_rev_conn,_hb_tasks.get(_rev_conn,bound_task['task_id']))['revision']
                            # The owner's direct turn runs under the control state it started with.
                            agent_run.update(task_id=bound_task['task_id'],task_version=bound_task['version'],control_revision=_revision)
                            if getattr(g,'hb_inline_execution',None):agent_run['execution_id']=g.hb_inline_execution
                        response_text, tokens_used, tool_receipts = run_apex_tools(
                            apex_model, messages, authorize_inspection, record_tool_receipt,
                            proposal_handler=propose_tool if operator else None,
                            prepare_messages=prepare_working_context, prepare_receipts=prepare_tool_receipts,
                            studio_handler=studio_tool if operator else None,
                            web_handler=web_tool if operator else None,
                            test_handler=test_tool if operator else None)
                        from core.hb_agent_tools import ground_answer
                        response_text=ground_answer(response_text,tool_receipts)
                        run_measurement=record_run(conv_id,selected_model,model_route.category,
                            'completed_with_tool_failures' if any(r.get('status')=='failed' for r in tool_receipts) else 'completed',
                            measured_started,measured_memory,tokens_used,tool_receipts)
                        _sse_chat(conv_id,'apex','measurement',model=selected_model,measurement=run_measurement)
                        if agent_run:
                            from core.agent_identity import save_memory
                            save_memory(APEX_AGENT['name'], message[:200], response_text,
                                        tags='chat,apex', source='chat:' + str(conv_id) + ':run:' + agent_run['run_id'])
                except ApexOffline as exc:
                    if 'measured_started' in locals():
                        record_run(conv_id,selected_model,model_route.category,'failed',
                            measured_started,measured_memory,0,lifecycle_receipts)
                    record_studio('offline', str(exc))
                    checkpoint_apex(conv_id, message, f'offline: {exc}', lifecycle_receipts)
                    _sse_chat(conv_id, APEX_AGENT['name'], 'failed', state=STATE_OFFLINE, error=str(exc))
                    if operator:
                        _share_apex_exchange(conv_id, operator_message_id, message, f'APEX offline: {exc}',
                                             lifecycle_receipts, peer_targets)
                    return _offline_response(exc, conv_id)
                except RuntimeError as exc:
                    if 'measured_started' in locals():
                        record_run(conv_id,selected_model,model_route.category,'failed',
                            measured_started,measured_memory,0,lifecycle_receipts)
                    record_studio('blocked', str(exc))
                    checkpoint_apex(conv_id, message, f'blocked: {exc}', lifecycle_receipts)
                    _sse_chat(conv_id, APEX_AGENT['name'], 'failed', state='error', error=str(exc))
                    _LOG.error('APEX runtime error: %s', exc)
                    if operator:
                        _share_apex_exchange(conv_id, operator_message_id, message, f'APEX error: {exc}',
                                             lifecycle_receipts, peer_targets)
                    return jsonify({
                        'ok': False, 'state': 'error', 'agent': APEX_AGENT['name'],
                        'model': selected_model, 'conversation_id': conv_id,
                        'response': f'APEX error: {exc}', 'routed_from': routed_from,
                    }), 500
                elapsed_ms = int((time.monotonic() - started) * 1000)
                log_message(conv_id, APEX_AGENT['name'], response_text, to_agent='user',
                            message_type='response', tokens_used=tokens_used)
                if operator:
                    _share_apex_exchange(conv_id, operator_message_id, message, response_text,
                                         tool_receipts, peer_targets)
                if operator and '[DISPATCH:' in response_text:
                    _dispatch_apex_peers(conv_id, APEX_AGENT['name'], response_text)
                checkpoint_apex(conv_id, message, 'turn completed; receipt statuses are authoritative',
                                lifecycle_receipts)
                if not _record_exchange(conv_id, APEX_AGENT['name'], message, response_text):
                    raise RuntimeError('APEX durable exchange persistence failed')
                from core import hb_tasks
                with __import__('contextlib').closing(get_connection()) as task_conn,task_conn:
                    tracked=hb_tasks.for_message(task_conn,operator_message_id) if operator_message_id else None
                    if tracked:
                        last=task_conn.execute("SELECT MAX(id) FROM messages WHERE conversation_id=? AND from_agent=?",(conv_id,APEX_AGENT['name'])).fetchone()[0]
                        if last and not hb_tasks.for_message(task_conn,last):
                            hb_tasks.bind(task_conn,conv_id,last,task_id=tracked['task_id'],parent_message_id=operator_message_id,kind='reply')
                            hb_tasks.event(task_conn,tracked,'apex','reply',{'content':response_text,'output_tokens':tokens_used},message_id=last)
                hb_tasks.flush_memory()
                record_studio('completed', response_text, tokens_used)
                _sse_chat(conv_id, APEX_AGENT['name'], 'completed', state=STATE_OK, tokens=tokens_used)
                entry = {
                    'agent': APEX_AGENT['name'], 'response': response_text, 'tokens': tokens_used,
                    'elapsed_ms': elapsed_ms, 'runtime_class': 'local', 'eta_seconds': 0,
                    'pending': False, 'job_id': None, 'model': selected_model,
                    'tool_receipts': tool_receipts, 'task':bound_task,
                    'usage':{'source':'measured','output_tokens':tokens_used},
                }
                return jsonify({
                    'ok': True, 'state': STATE_OK, 'mode': 'apex', 'storage_degraded': False,
                    'agent': APEX_AGENT['name'], 'model': selected_model,
                    'response': response_text, 'tokens': tokens_used, 'responses': [entry],
                    'pending_jobs': [], 'agents': normalized_agents, 'routed_from': routed_from,
                    'history_mode': history_mode,
                    'history_limit': history_limit if history_mode == 'recent' else None,
                    'conversation_id': conv_id,
                    'tool_receipts': tool_receipts,
                    'studio': studio_record, 'context_telemetry': context_telemetry, 'task':bound_task,
                    'model_routing': model_route.as_dict(),
                })
            finally:
                process_turn.release()
                if slot_held:
                    _APEX_TURNS.release()

        transcript = _thread_transcript_from_rows(thread_rows[-12:])
        reply_contexts = {
            selected_agent: _conversation_reply_context_from_rows(thread_rows, selected_agent)
            for selected_agent in normalized_agents
        }
        threaded_prompt = (
            '=== Shared conversation thread (latest) ===\n'
            f"{transcript or 'No previous messages.'}\n\n"
            '=== New user message ===\n'
            f'{message}'
        )
        if _should_attach_ticket_snapshot(message, thread_rows):
            threaded_prompt += _build_ticket_snapshot_block(limit=10)

        responses_map = {}
        pending_jobs = []
        deferred_agents = set()
        runnable_agents = list(normalized_agents)
        if 'sniffles' in runnable_agents and len(runnable_agents) > 1:
            runnable_agents = [a for a in runnable_agents if a != 'sniffles']
            deferred_agents.add('sniffles')

        def _register_persistent_job(selected_agent, future, reply_context, job_ref=None):
            job_id = f'chatjob-{uuid.uuid4().hex[:12]}'
            started_ts = time.time()
            now_iso = _chat_now_iso()
            eta_seconds = _chat_eta_seconds(selected_agent)
            with _CHAT_JOB_LOCK:
                _cleanup_chat_jobs_locked()
                _CHAT_JOBS[job_id] = {
                    'job_id': job_id,
                    'conversation_id': conv_id,
                    'agent': selected_agent,
                    'status': 'running',
                    'runtime_class': _chat_runtime_class(selected_agent),
                    'stage': _chat_stage_for(selected_agent, 0),
                    'eta_seconds': eta_seconds,
                    'started_ts': started_ts,
                    'updated_ts': started_ts,
                    'started_at': now_iso,
                    'updated_at': now_iso,
                    'future': future,
                    'cancel_requested': False,
                    'stage_trace': [],
                }
            # Persist to DB so the frontend can learn job outcome after a restart.
            persist_chat_job(
                job_id=job_id,
                conversation_id=conv_id,
                agent=selected_agent,
                runtime_class=_chat_runtime_class(selected_agent),
                eta_seconds=eta_seconds,
                started_at=now_iso,
            )
            if isinstance(job_ref, dict):
                job_ref['job_id'] = job_id
            try:
                _sse_chat(conv_id, selected_agent, 'running', job_id=job_id, eta_seconds=eta_seconds)
            except Exception:
                pass

            def _finish_job(done_future):
                updated_ts = time.time()
                updated_iso = _chat_now_iso()
                try:
                    response_text, tokens_used, elapsed_ms = done_future.result()
                    if (
                        _chat_response_is_unusable(selected_agent, response_text)
                        or _chat_response_echoes_prompt(message, response_text)
                    ):
                        raise RuntimeError(
                            f'{selected_agent} returned no usable answer: '
                            f'{str(response_text or "").strip()[:120] or "empty response"}'
                        )
                    handoff_failure = _chat_response_is_timeout_handoff(response_text, tokens_used)
                    if selected_agent in _get_ghost_agent_names() and _is_execution_confirmation(message):
                        try:
                            skill_output = _execute_agent_skill_lines(selected_agent, response_text, data)
                            if skill_output:
                                response_text = f"{response_text}\n\n---\nAuto-executed skill output:\n{skill_output}"
                        except Exception as skill_exc:
                            response_text = (
                                f"{response_text}\n\n---\n"
                                f"Auto-executed skill output:\n[skill:auto] FAILED\\n{skill_exc}"
                            )
                    with _CHAT_JOB_LOCK:
                        existing = _CHAT_JOBS.get(job_id)
                        terminal_status = str((existing or {}).get('status') or '')
                    if terminal_status in {'cancelled', 'failed'}:
                        return
                    response_target = _gate_relay_target(
                        _resolve_chat_reply_target(selected_agent, response_text, reply_context),
                        set(normalized_agents),
                    )
                    log_message(
                        conv_id,
                        selected_agent,
                        response_text,
                        to_agent=response_target,
                        message_type='response',
                        tokens_used=int(tokens_used or 0),
                    )
                    if selected_agent in _THREAD_HATS:
                        _update_thread_state(conv_id, selected_agent, message, response_text)
                        _record_exchange(conv_id, selected_agent, message, response_text)
                    # Session 29 — spine emit for relay handoffs only (skips self-replies).
                    if response_target and response_target != selected_agent:
                        try:
                            from core import spine as _spine
                            _spine.log(
                                _spine.EventKind.RELAY_STEP,
                                f'{selected_agent} → {response_target}',
                                severity=_spine.Severity.INFO,
                                source='chat',
                                agent=selected_agent,
                                thread_id=str(conv_id) if conv_id else None,
                                payload={
                                    'from': selected_agent,
                                    'to': response_target,
                                    'job_id': job_id,
                                },
                            )
                        except Exception:
                            pass
                    _trace_json = None
                    with _CHAT_JOB_LOCK:
                        job = _CHAT_JOBS.get(job_id)
                        if job and job.get('status') not in {'cancelled', 'failed'}:
                            final_status = 'failed' if handoff_failure else 'completed'
                            final_stage = 'handoff' if handoff_failure else 'completed'
                            final_error = (
                                'handoff deadline reached without a final agent answer'
                                if handoff_failure else ''
                            )
                            job.update({
                                'status': final_status,
                                'stage': final_stage,
                                'eta_seconds': 0,
                                'updated_ts': updated_ts,
                                'updated_at': updated_iso,
                                'elapsed_ms': int(elapsed_ms or 0),
                                'tokens': int(tokens_used or 0),
                                'error': final_error,
                                'response': response_text or '',
                            })
                            _trace_json = json.dumps(job.get('stage_trace') or [])
                            # Workstream: agent health watchdog. Record the
                            # completion in the per-agent ring buffer so p50/p95
                            # and stall counts stay current.
                            try:
                                _record_job_health_locked(job)
                            except Exception:
                                pass
                    update_chat_job_db(
                        job_id,
                        status='failed' if handoff_failure else 'completed',
                        stage='handoff' if handoff_failure else 'completed',
                        error=(
                            'handoff deadline reached without a final agent answer'
                            if handoff_failure else ''
                        ),
                        elapsed_ms=int(elapsed_ms or 0),
                        tokens=int(tokens_used or 0),
                        stage_trace_json=_trace_json,
                    )
                    if handoff_failure:
                        try:
                            ensure_chat_relay_recovery(
                                job_id=job_id,
                                conversation_id=conv_id,
                                stalled_agent=selected_agent,
                                reason='handoff deadline reached without a final agent answer',
                                stage_trace=(json.loads(_trace_json or '[]') if _trace_json else []),
                            )
                        except Exception:
                            pass
                        try:
                            _sse_chat(
                                conv_id,
                                selected_agent,
                                'failed',
                                job_id=job_id,
                                error='handoff deadline reached without a final agent answer',
                            )
                        except Exception:
                            pass
                        return
                    try:
                        _sse_chat(conv_id, selected_agent, 'completed', job_id=job_id, tokens=int(tokens_used or 0))
                    except Exception:
                        pass
                except Exception as exc:
                    err_text = str(exc or '').strip() or exc.__class__.__name__
                    agent_taken_offline = False
                    if _chat_error_should_disable_agent(err_text):
                        agent_taken_offline = _disable_agent_for_chat(selected_agent, err_text)
                    with _CHAT_JOB_LOCK:
                        existing = _CHAT_JOBS.get(job_id)
                        cancelled = bool(existing and existing.get('status') == 'cancelled')
                    if cancelled:
                        return
                    fail_msg = f'[{selected_agent}] background run failed: {err_text}'
                    if agent_taken_offline:
                        fail_msg += (
                            '\n\nThis agent has been taken offline and removed from Chat routing. '
                            'Re-enable it from the Agents tile after checking timeout/context settings.'
                        )
                    try:
                        response_target = _gate_relay_target(
                            _resolve_chat_reply_target(selected_agent, fail_msg, reply_context),
                            set(normalized_agents),
                        )
                        log_message(
                            conv_id,
                            selected_agent,
                            fail_msg,
                            to_agent=response_target,
                            message_type='response',
                            tokens_used=0,
                        )
                    except Exception:
                        pass
                    _trace_json_f = None
                    with _CHAT_JOB_LOCK:
                        job = _CHAT_JOBS.get(job_id)
                        if job and job.get('status') != 'cancelled':
                            job.update({
                                'status': 'failed',
                                'stage': 'failed',
                                'eta_seconds': 0,
                                'error': err_text,
                                'updated_ts': updated_ts,
                                'updated_at': updated_iso,
                            })
                            _trace_json_f = json.dumps(job.get('stage_trace') or [])
                            try:
                                _record_job_health_locked(job)
                            except Exception:
                                pass
                    if _chat_runtime_class(selected_agent) == 'local':
                        try:
                            _stop_result, _trace_after_stop, err_text = _chat_apply_runtime_stop_to_job(
                                job_id,
                                selected_agent,
                                err_text,
                                stage_trace=(json.loads(_trace_json_f or '[]') if _trace_json_f else _agent_stage_trace),
                                conversation_id=conv_id,
                                action='watchdog_unusable_answer_stop',
                            )
                            _trace_json_f = json.dumps(_trace_after_stop)
                        except Exception:
                            update_chat_job_db(job_id, status='failed', stage='failed', error=err_text,
                                               stage_trace_json=_trace_json_f)
                    else:
                        update_chat_job_db(job_id, status='failed', stage='failed', error=err_text,
                                           stage_trace_json=_trace_json_f)
                    try:
                        ensure_chat_relay_recovery(
                            job_id=job_id,
                            conversation_id=conv_id,
                            stalled_agent=selected_agent,
                            reason=err_text,
                            stage_trace=(json.loads(_trace_json_f or '[]') if _trace_json_f else _agent_stage_trace),
                        )
                    except Exception:
                        pass
                    try:
                        _sse_chat(conv_id, selected_agent, 'failed', job_id=job_id, error=err_text)
                    except Exception:
                        pass

            future.add_done_callback(_finish_job)
            return job_id

        debate_turn = []

        def _agent_label(agent_key):
            key = str(agent_key or '').strip().lower()
            return _get_agent_labels().get(key, key.capitalize() or 'Agent')

        def _build_debate_prompt(selected_agent):
            one_model = os.environ.get('SWARM_ONE_MODEL', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
            if len(runnable_agents) <= 1 or not parallel_mode or (one_model and is_worker_agent(selected_agent)):
                # Single-agent, sequential, or Fred (the only local worker, no peers to debate): no peer pressure
                return threaded_prompt

            active_labels = [_agent_label(a) for a in runnable_agents]
            if debate_turn:
                turn_lines = '\n'.join(
                    f"{_agent_label(item['agent'])}: {str(item['response'])[:800]}"
                    for item in debate_turn
                )
            else:
                turn_lines = 'No peer responses yet in this turn.'

            return (
                threaded_prompt
                + '\n\n=== Multi-Agent Debate Mode (Current Turn) ===\n'
                + f"You are {_agent_label(selected_agent)}.\n"
                + f"ACTIVE AGENTS IN THIS CHAT: {', '.join(active_labels)}.\n"
                + 'RULES: Only address agents from the list above. Do NOT mention, ask, or direct questions to '
                + 'any agent, person, or entity not in ACTIVE AGENTS. Do NOT ask Ghost to respond — '
                + 'Ghost has already sent their message above.\n'
                + 'Read the peer responses below and reply to them where useful. '
                + 'When another active agent already covered a point, extend or challenge it instead of restating it. '
                + 'If you agree or disagree, name the agent and explain in 1-2 lines. '
                + 'Then give your own answer.\n\n'
                + 'Peer responses so far this turn:\n'
                + turn_lines
            )

        # In sequential mode, once any agent goes pending we stop dispatching
        # further agents so they don't pile in simultaneously.
        # EXCEPTION: when the user explicitly selected multiple agents, we
        # always fan out to all of them — sequential stalling only applies
        # to relay-chain scenarios, not multi-agent fan-out.
        _sequential_stalled = False
        # Sequential mode is the safe default for local workers. If the first
        # local agent goes pending, stop and let the operator continue from the
        # live thread instead of fanning out more local jobs into the resource
        # gate and creating predictable "system busy" failures.
        _multi_agent_fanout = bool(parallel_mode) and len(runnable_agents) > 1

        for selected_agent in runnable_agents:
            if _sequential_stalled and not _multi_agent_fanout:
                # Mark remaining agents as queued — not dispatched this turn.
                responses_map[selected_agent] = {
                    'agent': selected_agent,
                    'response': (
                        f'[{selected_agent}] queued — waiting for previous agent to complete '
                        '(sequential mode). Re-send your message to continue.'
                    ),
                    'tokens': 0,
                    'elapsed_ms': 0,
                    'runtime_class': _chat_runtime_class(selected_agent),
                    'eta_seconds': _chat_eta_seconds(selected_agent),
                    'pending': False,
                    'sequential_queued': True,
                    'job_id': None,
                }
                debate_turn.append({'agent': selected_agent, 'response': ''})
                continue

            selected_agent_key = str(selected_agent or '').strip().lower()
            if selected_agent_key in _reg_stl():
                with _CHAT_JOB_LOCK:
                    _cleanup_chat_jobs_locked()
                    running_job = _chat_find_running_job_for_agent_locked(selected_agent_key)
                if running_job:
                    busy_conv = int(running_job.get('conversation_id') or 0)
                    busy_job_id = str(running_job.get('job_id') or '').strip()
                    busy_stage = str(running_job.get('stage') or 'running').strip()
                    responses_map[selected_agent] = {
                        'agent': selected_agent,
                        'response': (
                            f'[{selected_agent}] is already assigned to one active task '
                            f'(thread #{busy_conv}, job {busy_job_id or "unknown"}, stage: {busy_stage}). '
                            'Each local worker can run one task at a time. Cancel that run to move this agent to another thread now.'
                        ),
                        'tokens': 0,
                        'elapsed_ms': 0,
                        'runtime_class': _chat_runtime_class(selected_agent),
                        'eta_seconds': 0,
                        'pending': False,
                        'job_id': None,
                    }
                    continue

            job_ref = {'job_id': None}
            _agent_stage_trace = []

            def _stage_cb(stage_text, eta_seconds=None, _job_ref=job_ref, _trace=_agent_stage_trace):
                _trace.append({'text': str(stage_text), 'ts': time.time()})
                job_id = _job_ref.get('job_id')
                if not job_id:
                    return
                _chat_update_job(job_id, stage=stage_text, eta_seconds=eta_seconds)

            agent_prompt = _build_debate_prompt(selected_agent)
            future = _CHAT_DISPATCH_EXECUTOR.submit(
                _run_single_agent,
                selected_agent,
                agent_prompt,
                history,
                reply_contexts[selected_agent],
                True,
                _stage_cb,
            )
            try:
                wait_timeout = 20 if selected_agent == 'sniffles' else 10
                response_text, tokens_used, elapsed_ms = future.result(timeout=wait_timeout)
                pending = False
                pending_job_id = None
            except FuturesTimeoutError:
                pending_job_id = _register_persistent_job(selected_agent, future, reply_contexts[selected_agent], job_ref)
                pending_jobs.append(pending_job_id)
                # Sync stages that fired before job_id was set into the job record.
                if _agent_stage_trace and pending_job_id:
                    with _CHAT_JOB_LOCK:
                        _pj = _CHAT_JOBS.get(pending_job_id)
                        if _pj is not None:
                            existing = _pj.get('stage_trace') or []
                            # Merge pre-timeout trace entries at the front.
                            _pj['stage_trace'] = [e for e in _agent_stage_trace if e not in existing] + existing
                            # Show the last known stage rather than the default 'loading local memory'
                            _pj['stage'] = _agent_stage_trace[-1]['text']
                pending = True
                if not parallel_mode:
                    _sequential_stalled = True  # stop dispatching further agents this turn
                eta_seconds = _chat_eta_seconds(selected_agent)
                response_text, tokens_used = (
                    f'[{selected_agent}] acknowledged. Running now. ETA ~{eta_seconds}s; monitor shows live stage.',
                    0,
                )
                elapsed_ms = int(wait_timeout * 1000)
            except Exception as exc:
                response_text, tokens_used = (f'[{selected_agent}] Unavailable: {_friendly_api_error(exc)}', 0)
                elapsed_ms = 0
                pending = False
                pending_job_id = None

            responses_map[selected_agent] = {
                'agent': selected_agent,
                'response': response_text,
                'tokens': tokens_used,
                'elapsed_ms': elapsed_ms,
                'runtime_class': _chat_runtime_class(selected_agent),
                'eta_seconds': _chat_eta_seconds(selected_agent) if pending else 0,
                'pending': pending,
                'job_id': pending_job_id,
                'stage_trace': [] if pending else _agent_stage_trace,
            }

            if (not pending) and selected_agent in _get_ghost_agent_names() and _is_execution_confirmation(message):
                skill_output = _execute_agent_skill_lines(selected_agent, response_text, data)
                if skill_output:
                    responses_map[selected_agent]['response'] = (
                        f"{response_text}\n\n---\nAuto-executed skill output:\n{skill_output}"
                    )

            debate_turn.append({'agent': selected_agent, 'response': response_text})

        for agent_name in deferred_agents:
            responses_map[agent_name] = {
                'agent': agent_name,
                'response': (
                    '[sniffles] deferred: heavyweight auditor runs on-demand. '
                    'Send to sniffles alone for a full audit.'
                ),
                'tokens': 0,
                'elapsed_ms': 0,
                'runtime_class': _chat_runtime_class(agent_name),
                'eta_seconds': 0,
                'pending': False,
                'job_id': None,
            }

        responses = [responses_map[a] for a in normalized_agents if a in responses_map]
        total_tokens = sum(int(r.get('tokens') or 0) for r in responses)
        for entry in responses:
            if entry.get('pending') or entry.get('sequential_queued'):
                continue
            response_target = _gate_relay_target(
                _resolve_chat_reply_target(entry['agent'], entry['response'], reply_contexts[entry['agent']]),
                set(normalized_agents),
            )
            log_message(
                conv_id,
                entry['agent'],
                entry['response'],
                to_agent=response_target,
                message_type='response',
                tokens_used=int(entry.get('tokens') or 0),
            )

        primary = responses[0] if responses else {'agent': normalized_agents[0], 'response': '', 'tokens': 0}

        return jsonify({
            'ok': True,
            'agent': primary['agent'],
            'response': primary['response'],
            'tokens': total_tokens,
            'responses': responses,
            'pending_jobs': pending_jobs,
            'agents': normalized_agents,
            'history_mode': history_mode,
            'history_limit': history_limit if history_mode == 'recent' else None,
            'conversation_id': conv_id,
        })
    except Exception as exc:
        _LOG.exception('Live chat request failed')
        return jsonify({'ok': False, 'response': f'Error: {str(exc)}'}), 500



@chat_bp.route('/api/chat/jobs/status')
def api_chat_jobs_status():
    """Poll status for long-running chat jobs.

    Query params:
    - conversation_id (optional)
    - job_ids (optional comma-separated list)
    """
    conv_id = request.args.get('conversation_id')
    raw_job_ids = (request.args.get('job_ids') or '').strip()
    want_ids = {x.strip() for x in raw_job_ids.split(',') if x.strip()} if raw_job_ids else set()

    conv_id_int = None
    if conv_id:
        try:
            conv_id_int = int(conv_id)
        except Exception:
            conv_id_int = None

    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        # Workstream: watchdog. Mark any job past its budget as failed BEFORE
        # building the response payload so the UI sees the stall on its very
        # next poll. Stalled jobs are also recorded in the health ring.
        _stalled = _watchdog_mark_stalled_jobs_locked()
        for _s_job in _stalled:
            _job_obj = _CHAT_JOBS.get(_s_job['job_id'])
            if _job_obj is not None:
                try:
                    _record_job_health_locked(_job_obj)
                except Exception:
                    pass
        jobs = []
        for job in _CHAT_JOBS.values():
            if conv_id_int is not None and int(job.get('conversation_id') or -1) != conv_id_int:
                continue
            if want_ids and job.get('job_id') not in want_ids:
                continue
            jobs.append(_chat_job_public(job))

    # Persist + best-effort hard-kill outside the lock. Failures are tolerated:
    # the in-memory state already shows stalled, so the UI is not blocked.
    recoveries = []
    for _s in _stalled:
        stop_trace = _s.get('stage_trace') or []
        stop_error = _s.get('error')
        try:
            _stop_result, stop_trace, stop_error = _chat_apply_runtime_stop_to_job(
                _s.get('job_id'),
                _s.get('agent') or '',
                _s.get('error'),
                elapsed_ms=int(_s.get('elapsed_ms') or 0),
                stage_trace=stop_trace,
                conversation_id=_s.get('conversation_id'),
                action='watchdog_stall_stop',
            )
        except Exception:
            try:
                update_chat_job_db(
                    _s['job_id'],
                    status='failed',
                    stage='stalled',
                    error=_s['error'],
                    elapsed_ms=int(_s.get('elapsed_ms') or 0),
                )
            except Exception:
                pass
        try:
            _sse_chat(_s.get('conversation_id'), _s.get('agent'), 'failed',
                      job_id=_s.get('job_id'), error=stop_error)
        except Exception:
            pass
        try:
            recovery_result = ensure_chat_relay_recovery(
                job_id=_s.get('job_id'),
                conversation_id=_s.get('conversation_id'),
                stalled_agent=_s.get('agent'),
                reason=stop_error,
                stage_trace=stop_trace,
            )
            recovery = recovery_result.get('recovery') if isinstance(recovery_result, dict) else None
            if recovery:
                recoveries.append(recovery)
                if recovery_result.get('created'):
                    log_activity(
                        'vortex',
                        'relay_recovery_checkpoint',
                        f"job_id={_s.get('job_id')} agent={_s.get('agent')} conversation={_s.get('conversation_id')}",
                    )
                    log_activity(
                        'terminal',
                        'relay_recovery_created',
                        f"job_id={_s.get('job_id')} recovery={recovery.get('recovery_id')}",
                    )
        except Exception:
            pass

    # For any explicitly requested IDs not found in memory, fall back to DB.
    # This surfaces outcomes for jobs that finished after a server restart.
    if want_ids:
        found_in_memory = {j['job_id'] for j in jobs}
        missing_ids = want_ids - found_in_memory
        if missing_ids:
            for row in get_chat_jobs_by_ids(missing_ids):
                elapsed = int(row.get('elapsed_ms') or 0)
                _db_trace = []
                try:
                    _db_trace = json.loads(row.get('stage_trace_json') or '[]')
                except Exception:
                    pass
                row_status = str(row.get('status') or '').lower()
                if row_status in {'running', 'dispatched', 'processing'}:
                    error = (
                        'Watchdog: job was still marked running in SQLite but '
                        'is missing from the live runtime. Automatic orphan recovery.'
                    )
                    _db_trace.append({'text': 'orphaned runtime job (watchdog)', 'ts': time.time()})
                    try:
                        _stop_result, _db_trace, error = _chat_apply_runtime_stop_to_job(
                            row.get('job_id'),
                            row.get('agent') or '',
                            error,
                            elapsed_ms=elapsed,
                            stage_trace=_db_trace,
                            conversation_id=row.get('conversation_id'),
                            action='watchdog_orphan_stop',
                        )
                    except Exception:
                        try:
                            update_chat_job_db(
                                row.get('job_id'),
                                status='failed',
                                stage='stalled',
                                error=error,
                                elapsed_ms=elapsed,
                                stage_trace_json=json.dumps(_db_trace),
                            )
                        except Exception:
                            pass
                    try:
                        recovery_result = ensure_chat_relay_recovery(
                            job_id=row.get('job_id'),
                            conversation_id=row.get('conversation_id'),
                            stalled_agent=row.get('agent'),
                            reason=error,
                            stage_trace=_db_trace,
                        )
                        recovery = recovery_result.get('recovery') if isinstance(recovery_result, dict) else None
                        if recovery:
                            recoveries.append(recovery)
                    except Exception:
                        pass
                    row = dict(row)
                    row['status'] = 'failed'
                    row['stage'] = 'stalled'
                    row['error'] = error
                    row['stage_trace_json'] = json.dumps(_db_trace)
                jobs.append({
                    'job_id': row.get('job_id'),
                    'conversation_id': row.get('conversation_id'),
                    'agent': row.get('agent'),
                    'status': row.get('status') or 'failed',
                    'runtime_class': row.get('runtime_class') or _chat_runtime_class(row.get('agent')),
                    'stage': row.get('stage') or 'unknown',
                    'eta_seconds': int(row.get('eta_seconds') or 0),
                    'eta_remaining_seconds': 0,
                    'started_at': row.get('started_at'),
                    'updated_at': row.get('updated_at'),
                    'elapsed_ms': elapsed,
                    'error': row.get('error') or '',
                    'response': row.get('response') or '',
                    'stage_trace': _db_trace,
                })

    if conv_id_int is not None:
        try:
            _chat_schedule_unowned_runner_reconcile(conv_id_int)
            has_running = any(str(j.get('status') or '') == 'running' for j in jobs)
            if not has_running:
                silent_result = ensure_silent_chat_thread_recovery(
                    conv_id_int,
                    reason=(
                        'Thread has cancelled/failed chat jobs and no visible '
                        'agent reply after the latest user turn.'
                    ),
                )
                recovery = silent_result.get('recovery') if isinstance(silent_result, dict) else None
                if recovery:
                    recoveries.append(recovery)
                    if silent_result.get('created'):
                        log_activity(
                            'terminal',
                            'silent_thread_recovery_created',
                            f"conversation={conv_id_int} recovery={recovery.get('recovery_id')}",
                        )
                quality_result = _chat_ensure_unusable_thread_recovery(conv_id_int)
                quality_recovery = (
                    quality_result.get('recovery')
                    if isinstance(quality_result, dict) else None
                )
                if quality_recovery:
                    recoveries.append(quality_recovery)
                    if quality_result.get('created'):
                        log_activity(
                            'terminal',
                            'unusable_thread_recovery_created',
                            f"conversation={conv_id_int} recovery={quality_recovery.get('recovery_id')}",
                        )
        except Exception:
            pass
        try:
            existing_ids = {str(r.get('recovery_id') or '') for r in recoveries}
            for recovery in get_open_chat_relay_recoveries(conv_id_int, limit=10):
                rid = str(recovery.get('recovery_id') or '')
                if rid and rid not in existing_ids:
                    recoveries.append(recovery)
                    existing_ids.add(rid)
        except Exception:
            pass

    jobs.sort(key=lambda j: (j.get('status') != 'running', j.get('agent') or ''))
    return jsonify({'ok': True, 'jobs': jobs, 'recoveries': recoveries})


@chat_bp.route('/api/chat/recoveries/<recovery_id>/status', methods=['POST'])
def api_chat_recovery_status(recovery_id):
    """Update a relay recovery card from the runtime panel or agent tooling."""
    data = request.get_json(silent=True) or {}
    status = str(data.get('status') or '').strip().lower()
    if status not in {'open', 'reviewed', 'ignored', 'escalated'}:
        return jsonify({
            'ok': False,
            'error': 'status must be one of: open, reviewed, ignored, escalated',
        }), 400

    actor = str(data.get('actor') or 'chat').strip()[:80] or 'chat'
    summary = str(data.get('summary') or '').strip()
    if not summary:
        summary = f'Relay recovery marked {status} by {actor}.'

    ok = update_chat_relay_recovery_status(recovery_id, status, summary=summary)
    if not ok:
        return jsonify({'ok': False, 'error': 'recovery not found'}), 404

    try:
        log_activity(
            'terminal',
            'relay_recovery_status',
            f'recovery={recovery_id} status={status} actor={actor}',
        )
    except Exception:
        pass

    return jsonify({'ok': True, 'recovery_id': recovery_id, 'status': status})


@chat_bp.route('/api/chat/agents/health')
def api_chat_agents_health():
    """Per-agent latency + stall snapshot from the in-memory health ring.

    Returns: {ok, agents: {agent_name: {count, completed, failed, stalled,
    p50_ms, p95_ms}}, watchdog: {budget_min_seconds, budget_max_seconds,
    eta_multiplier}}.

    Cheap to call; designed to be polled by the Monitor tile / Health Digest.
    """
    snapshot = get_chat_agent_health_snapshot()
    return jsonify({
        'ok': True,
        'agents': snapshot,
        'watchdog': {
            'eta_multiplier': 4.0,
            'budget_min_seconds': 300,
            'budget_max_seconds': _CHAT_LOCAL_HANDOFF_DEADLINE_SECONDS,
        },
    })


@chat_bp.route('/api/chat/jobs/cancel', methods=['POST'])
def api_chat_jobs_cancel():
    """Owner Stop holds durable tasks even when no legacy chat job exists."""
    from importlib import import_module
    from urllib.parse import urlsplit
    bridge=import_module(__package__+'.peer_bridge')
    user=bridge.get_current_user()
    origin=request.headers.get('Origin')
    if not user or user.get('role')!='owner':
        return jsonify(ok=False,error='Owner authentication required'),403
    if (request.headers.get('Sec-Fetch-Site')=='cross-site'
            or origin and urlsplit(origin).netloc!=request.host):
        return jsonify(ok=False,error='Use the authenticated main chat to Stop'),403
    if not request.is_json:return jsonify(ok=False,error='JSON Stop command required'),400
    data=request.get_json() or {}
    try:
        conv_id_int=int(data['conversation_id'])
        if conv_id_int<=0:raise ValueError()
    except (KeyError,TypeError,ValueError):
        return jsonify(ok=False,error='A positive conversation_id is required'),400
    raw_ids=data.get('job_ids') or []
    if isinstance(raw_ids,str):raw_ids=[x.strip() for x in raw_ids.split(',') if x.strip()]
    if not isinstance(raw_ids,list):return jsonify(ok=False,error='job_ids must be an array'),400
    want_ids={str(x).strip() for x in raw_ids if str(x).strip()}
    # Commit the same task holds used by chat bubble controls before cancelling
    # futures. Stop never unloads a model resident shared with another task.
    held=bridge._owner_chat_stop({'conversation_id':conv_id_int},'Stop',conv_id_int,user).get_json()
    cancelled=[];skipped=[]
    with _CHAT_JOB_LOCK:
        _cleanup_chat_jobs_locked()
        for job_id,job in list(_CHAT_JOBS.items()):
            if want_ids and job_id not in want_ids:continue
            if int(job.get('conversation_id') or -1)!=conv_id_int:continue
            status=str(job.get('status') or 'running')
            if status in {'completed','failed','cancelled'}:
                skipped.append({'job_id':job_id,'reason':f'already {status}'});continue
            future=job.get('future');signalled=False
            if future is not None:
                try:signalled=bool(future.cancel())
                except Exception:pass
            job.update(status='cancelled',stage='cancelled by user',eta_seconds=0,
                error='cancelled by user',cancel_requested=True,updated_ts=time.time(),updated_at=_chat_now_iso())
            update_chat_job_db(job_id,status='cancelled',stage='cancelled by user',error='cancelled by user')
            cancelled.append({'job_id':job_id,'agent':job.get('agent'),'cancel_signal_sent':signalled})
    return jsonify(ok=True,cancelled=cancelled,skipped=skipped,count=len(cancelled),
        held_tasks=held['held_tasks'],control_receipts=held['control_receipts'],interrupted=held['interrupted'],
        hard_kill=False,hard_kill_results=[])


@chat_bp.route('/api/chat/librarian/review', methods=['POST'])
def api_chat_librarian_review():
    """
    Ask Librarian to detect implicit relay candidates that the regex relay missed.
    The call runs synchronously but with a hard timeout — the frontend should call
    this async/debounced and not block the chat UI on the result.

    Body:
    - text: the agent response text to review (required, max 1200 chars trimmed)
    - from_agent: who sent the message (required)
    - conversation_id: for logging (optional)
    """
    data = request.get_json(silent=True) or {}
    text = str(data.get('text') or '').strip()
    from_agent = str(data.get('from_agent') or 'agent').strip().lower()
    conversation_id = data.get('conversation_id')

    if not text or len(text) < 20:
        return jsonify({'ok': True, 'candidates': []})
    if len(text) > 2000:
        text = text[:2000]

    try:
        candidates = orchestrator.librarian_relay_review(text, from_agent, timeout_s=18)
        log_activity('terminal', 'librarian_relay_review',
                     f'from={from_agent} conv={conversation_id} found={len(candidates)}')
        return jsonify({'ok': True, 'candidates': candidates})
    except Exception as e:
        log_activity('terminal', 'librarian_relay_review_error', str(e)[:200])
        return jsonify({'ok': True, 'candidates': [], 'error': str(e)[:120]})


# ── Chunk 8B — Intent Classifier ─────────────────────────────────────────────

@chat_bp.route('/api/chat/classify', methods=['POST'])
def api_chat_classify():
    """Classify a user message and return agent/model/relay recommendation.

    Body: {message: str}
    Returns: {ok, category, agents, model_tier, relay, confidence, reasoning, models}
    """
    data = request.get_json(silent=True) or {}
    message = str(data.get('message') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'No message provided'}), 400

    from utils.intent_classifier import classify_message
    from utils.model_selector import select_models_for_agents
    result = classify_message(message)

    # Resolve per-agent model selections (8E)
    try:
        from utils.db.registry import get_agent_models
        user_models = get_agent_models()
    except Exception:
        user_models = {}
    result['models'] = select_models_for_agents(
        result['agents'], result['category'], user_models,
    )

    # Phase 3 parallel signal: deterministic router decision (non-breaking).
    # Surfaces explicit-target / @mention / role-keyword precedence so callers
    # can diff against classify_message() and eventually migrate.
    try:
        from core.routing import route as _route
        from utils.db.registry import get_routable_agents as _reg_routable
        _decision = _route(message, sender='user', routable_agents=_reg_routable())
        result['router'] = {
            'target': _decision.target,
            'category': _decision.category,
            'confidence': _decision.confidence,
            'rationale': _decision.rationale,
            'candidates': list(_decision.candidates),
        }
    except Exception as _e:
        result['router'] = {'error': str(_e)[:160]}

    # Session 29 — Seven-as-guardian signal. Callers (chat UI) can render a
    # "Seven is taking this" card when guardian=true without changing the
    # underlying classify_message result.
    try:
        from core import spine as _spine
        from utils.db.registry import get_routable_agents as _reg_routable
        _spine_decision = _spine.route(
            message, sender='user', routable_agents=_reg_routable(),
        )
        result['guardian'] = {
            'active': bool(_spine_decision.guardian),
            'target': _spine_decision.target,
            'original_target': _spine_decision.original_target,
            'confidence': _spine_decision.confidence,
            'rationale': _spine_decision.rationale,
        }
    except Exception as _g:
        result['guardian'] = {'error': str(_g)[:160]}

    result['ok'] = True
    return jsonify(result)


@chat_bp.route('/api/chat/action-intent', methods=['POST'])
def api_chat_action_intent():
    """Detect a Siri-style client action in a chat message.

    Body: {message: str}
    Returns: {ok: True, intent: {...} | None}

    Pure rules (core.chat_actions) — no LLM, no state mutation. The UI shows
    a confirmation pill and only performs the action on user click.
    """
    data = request.get_json(silent=True) or {}
    message = str(data.get('message') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'No message provided'}), 400
    try:
        from core.chat_actions import detect_action
        intent = detect_action(message)
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({'ok': False, 'error': str(exc)[:160]}), 500
    return jsonify({'ok': True, 'intent': intent})
