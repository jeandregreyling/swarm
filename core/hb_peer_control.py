"""Fixed HB worker maintenance for the authenticated local APEX task."""
from pathlib import Path
from contextlib import closing
import os,signal,sqlite3,json,tempfile,time
from core import agent_identity,hb_local_jobs
from utils.db._connection import get_connection
ROOT=Path(__file__).resolve().parents[1]


def _gemini_pids():
    expected=str((ROOT/'scripts/hummingbird_gemini_peer.py').resolve())
    matches=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            if entry.stat().st_uid!=os.getuid():continue
            args=(entry/'cmdline').read_bytes().decode(errors='replace').split('\0')
            if len(args)>1 and Path(args[0]).name.startswith('python') and args[1]==expected:
                matches.append(int(entry.name))
        except (OSError,ValueError):continue
    return matches


def gemini_reload(args):
    if set(args)-{'provider_model'} or args.get('provider_model','gemini-4-argon')!='gemini-4-argon':raise ValueError('gemini_reload accepts only provider_model gemini-4-argon')
    with closing(get_connection()) as conn:
        _,task=hb_local_jobs.assigned(conn)
        if task['state'] in {'paused','cancelled','completed'}:
            raise PermissionError('Worker reload requires an active assigned task')
        if conn.execute("SELECT 1 FROM hb_peer_work WHERE principal='gemini-advisor' AND state IN ('queued','running') LIMIT 1").fetchone():
            raise ValueError('Gemini has an active invitation; wait for its recorded result before reload')
    journal=agent_identity.directory('gemini-advisor')/'hb-worker.sqlite'
    if journal.is_symlink():raise PermissionError('Gemini journal cannot be a symlink')
    if journal.is_file():
        with closing(sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True)) as worker:
            if worker.execute("SELECT 1 FROM jobs WHERE state IN ('running','reply_pending','awaiting_provider') LIMIT 1").fetchone():
                raise ValueError('Gemini is generating, delivering or waiting for provider recovery; reload deferred')
    pids=_gemini_pids()
    if len(pids)>1:raise RuntimeError('Multiple Gemini workers found; no process was stopped')
    if args.get('provider_model'):
        target=agent_identity.directory('gemini-advisor')/'hb-provider-model.json'
        if target.is_symlink():raise PermissionError('Gemini provider selection cannot be a symlink')
        actor=agent_identity.CURRENT.get() or {}
        record={'model':args['provider_model'],'selected_by':actor.get('principal'),'task_id':task['task_id'],'selected_at':time.time(),'reason':'Explicit owner-authorized repair after configured3.8Flash generation504 and successful2.5Flash diagnostic'}
        fd,tmp=tempfile.mkstemp(prefix='.hb-provider-',dir=target.parent)
        try:
            with os.fdopen(fd,'w') as stream:json.dump(record,stream);stream.flush();os.fsync(stream.fileno())
            os.chmod(tmp,0o600);os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    if pids:os.kill(pids[0],signal.SIGTERM)

    return {'status':'restart_requested' if pids else 'supervisor_start_pending','principal':'gemini-advisor',
            'task_id':task['task_id'],**({'provider_model':args['provider_model']} if args.get('provider_model') else {}),'notice':'HB supervises this fixed worker. Confirm worker_running using gemini_status before a fresh test. No root command, credentials or old invitations were replayed.'}
