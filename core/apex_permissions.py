"""Explicit owner grants for autonomous source-file writes in one workspace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from core.recovery_supervisor import ROOT

POLICY_PATH = Path.home() / '.config/hummingbird/apex-permissions.json'
WRITE_TOOLS = frozenset({'propose_write_file', 'propose_patch'})


def autonomous_writes_allowed(owner: str, workspace: Path | None = None) -> bool:
    """Only a private host-owned grant, outside model-writable source, enables writes."""
    workspace = ROOT if workspace is None else workspace
    try:
        descriptor = os.open(POLICY_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o022 or info.st_size > 4096):
                return False
            content = stream.read(4097)
        if len(content) > 4096:
            return False
        policy = json.loads(content)
        return (isinstance(policy, dict) and policy.get('autonomous_writes') is True
                and policy.get('owner') == owner and bool(owner)
                and isinstance(policy.get('workspace'), str)
                and Path(policy['workspace']).is_absolute()
                and Path(policy['workspace']).resolve() == Path(workspace).resolve()
                and not POLICY_PATH.resolve().is_relative_to(Path(workspace).resolve()))
    except (OSError, ValueError, TypeError):
        return False


def execute_authorized_write(store, repository, tool, args, operator, conversation_id, authorize):
    """Execute the owner's standing grant through the existing validated file executor."""
    owner, session = operator
    if tool not in WRITE_TOOLS or not autonomous_writes_allowed(owner, repository.root):
        raise PermissionError('No owner grant for autonomous writes in this workspace')
    if not authorize(tool):
        raise PermissionError('Workspace write permission is denied for this owner session')
    from core import agent_identity,hb_task_operations,hb_tasks
    from contextlib import closing
    from utils.db._connection import get_connection
    actor=agent_identity.CURRENT.get()
    task=None;operation=None
    if actor and actor.get('execution_id') and tool in {'propose_patch','propose_write_file'}:
        with closing(get_connection()) as conn,conn:
            task=hb_tasks.get(conn,actor['task_id'])
            reused=hb_task_operations.replay(conn,repository,task,tool,args)
        if reused:return reused
    transaction = store.propose(repository, tool, args, owner, session, conversation_id)
    if task:
        with closing(get_connection()) as conn,conn:
            operation=hb_task_operations.begin(conn,task,tool,args,transaction,execution_id=actor['execution_id'])
    try:
        result = store.decide(
            transaction.id, True, owner, session, transaction.csrf,
            lambda name: autonomous_writes_allowed(owner, repository.root) and authorize(name))
    except Exception:
        store.cancel(transaction, 'Write authorization failed; no further execution authorized')
        raise
    if operation:
        with closing(get_connection()) as conn,conn:
            result=hb_task_operations.finish(conn,operation,result)
            hb_tasks.event(conn,task,actor['principal'],'mutation',result)
    return {**result, 'authorization': 'owner_workspace_grant'}


def resume_recovery_with_tools(continuity, conversation_id, owner, connect):
    """Restore an authorized owner's tools without discarding the original journal."""
    import fcntl
    from contextlib import closing
    from core.recovery_resume import import_journal

    if not autonomous_writes_allowed(owner):
        raise PermissionError('Owner workspace grant required to resume recovery with tools')
    lock_path = continuity.path(conversation_id).with_suffix('.lock')
    if lock_path.is_symlink():
        raise PermissionError('Continuity lock cannot be a symlink')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        thread = continuity.read(conversation_id, owner)
        with closing(connect()) as conn:
            return import_journal(conn, thread, owner)
