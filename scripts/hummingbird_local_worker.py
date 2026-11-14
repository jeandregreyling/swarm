#!/usr/bin/env python3
"""Fixed local-job worker; no arbitrary command or provider selection."""
from pathlib import Path
from contextlib import closing
import sys,time,fcntl,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'frontend'),str(ROOT/'utils')]
from core import hb_local_jobs as jobs,agent_identity
from utils.db._connection import get_connection

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=sorted(jobs.KINDS),required=True);args=parser.parse_args()
    folder=agent_identity.directory('apex');path=folder/('hb-local-'+args.kind+'.lock')
    if path.is_symlink():raise PermissionError('Worker lock cannot be a symlink')
    with path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with closing(get_connection()) as conn,conn:
            jobs.ensure_schema(conn)
            # Review has no side effects; archive verifies/reuses files/checkpoints.
            conn.execute("UPDATE hb_local_jobs SET status='queued',stage='Resuming saved local work' WHERE kind=? AND status='running'",(args.kind,))
        with agent_identity.execution('apex',requested_by='HB authenticated queued local work'):
            while jobs.run_one(args.kind):pass
if __name__=='__main__':main()
