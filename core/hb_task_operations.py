"""Durable source-operation receipts; a fresh agent turn cannot repeat a write."""
import hashlib
import json
import time

from core.tool_approval import ApprovalStore


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS hb_task_operations(
        operation_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,tool TEXT NOT NULL,
        state TEXT NOT NULL,paths TEXT NOT NULL,before_hashes TEXT NOT NULL,
        after_hashes TEXT NOT NULL,transaction_id TEXT NOT NULL,receipt TEXT,updated_at REAL)''')
    if 'execution_id' not in {r[1] for r in conn.execute('PRAGMA table_info(hb_task_operations)')}:
        conn.execute('ALTER TABLE hb_task_operations ADD COLUMN execution_id TEXT')


def operation_id(task,tool,args):
    return hashlib.sha256(json.dumps([task['task_id'],tool,args],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def replay(conn,repository,task,tool,args):
    ensure_schema(conn)
    key=operation_id(task,tool,args)
    row=conn.execute('SELECT state,paths,before_hashes,after_hashes,transaction_id,receipt,execution_id FROM hb_task_operations WHERE operation_id=?',(key,)).fetchone()
    if not row:return None
    paths=json.loads(row[1]);expected=json.loads(row[3])
    current={path:ApprovalStore._hash(ApprovalStore._state(repository,path,
        patch=tool=='propose_patch',create=tool=='propose_write_file')) for path in paths}
    if current==expected:
        receipt=json.loads(row[5]) if row[5] else {'transaction_id':row[4],'status':'succeeded',
            'output':'Previously started source operation verified from its saved after-hash; no write was replayed.'}
        receipt.update(status='succeeded',operation_id=key,replayed=True,executed=False)
        conn.execute("UPDATE hb_task_operations SET state='succeeded',receipt=?,updated_at=? WHERE operation_id=?",(json.dumps(receipt),time.time(),key))
        return receipt
    if row[0]=='succeeded':raise ValueError('Source changed after this completed operation. Read current source and propose a new exact change; the old write was not replayed.')
    if row[0]=='pending':
        from core import hb_executions
        hb_executions.reconcile(conn)
        executor=conn.execute('SELECT state FROM hb_executions WHERE execution_id=?',(row[6],)).fetchone() if row[6] else None
        if executor and executor[0] in {'interrupted','failed'} and current==json.loads(row[2]):
            from core.hb_process_lock import ProcessLock
            with ProcessLock('source-write',repository.root):
                # The old process is gone and its write never occurred. A fresh guarded proposal may run.
                checked={path:ApprovalStore._hash(ApprovalStore._state(repository,path,
                    patch=tool=='propose_patch',create=tool=='propose_write_file')) for path in paths}
                if checked!=current:raise ValueError('Source changed during recovery; read current source before retrying')
                conn.execute("UPDATE hb_task_operations SET state='interrupted',updated_at=? WHERE operation_id=?",(time.time(),key))
            return None
        raise ValueError('This exact operation is already pending. Reconcile its source hashes and receipt before any retry; no duplicate write ran.')
    return None


def begin(conn,task,tool,args,transaction,*,execution_id=None):
    ensure_schema(conn)
    key=operation_id(task,tool,args)
    path=transaction.paths[0];state=transaction.states[path]
    before=state[0].decode() if state else ''
    after=before.replace(args['exact_old_text'],args['new_text'],1) if tool=='propose_patch' else args['content']
    expected={path:ApprovalStore._hash((after.encode(),state[1] if state else 0o644))}
    previous=conn.execute('SELECT state FROM hb_task_operations WHERE operation_id=?',(key,)).fetchone()
    if previous and previous[0] in {'pending','succeeded'}:raise ValueError('This source operation already has a live or successful receipt; no duplicate write ran')
    conn.execute('''INSERT INTO hb_task_operations(operation_id,task_id,tool,state,paths,before_hashes,after_hashes,transaction_id,receipt,updated_at,execution_id)
        VALUES (?,?,?,'pending',?,?,?,?,NULL,?,?)
        ON CONFLICT(operation_id) DO UPDATE SET state='pending',before_hashes=excluded.before_hashes,
        after_hashes=excluded.after_hashes,transaction_id=excluded.transaction_id,receipt=NULL,updated_at=excluded.updated_at,execution_id=excluded.execution_id''',
        (key,task['task_id'],tool,json.dumps(transaction.paths),json.dumps(transaction.hashes),json.dumps(expected),transaction.id,time.time(),execution_id))
    return key


def finish(conn,key,receipt):
    saved={**receipt,'operation_id':key,'executed':receipt['status']=='succeeded','replayed':False}
    conn.execute('UPDATE hb_task_operations SET state=?,receipt=?,updated_at=? WHERE operation_id=?',
        ('succeeded' if receipt['status']=='succeeded' else 'failed',json.dumps(saved),time.time(),key))
    return saved


def prepare_owner_proposal(conn,store,repository,task,tool,args,owner,session,conversation_id,execution_id):
    """Use the same durable intent before a human-popup proposal waits for approval."""
    reused=replay(conn,repository,task,tool,args)
    if reused:return None,None,reused
    transaction=store.propose(repository,tool,args,owner,session,conversation_id)
    key=begin(conn,task,tool,args,transaction,execution_id=execution_id)
    return transaction,key,None
