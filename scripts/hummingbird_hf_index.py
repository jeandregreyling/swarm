#!/usr/bin/env python3
"""Index verified downloaded Parquet examples locally, with visible HB progress."""
from pathlib import Path
from contextlib import closing
import json,sys,time,threading,fcntl
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'frontend'),str(ROOT/'utils')]
from core import hf_text_index as index,hf_library,hf_mirror
from scripts.hummingbird_apex_live_check import AgentAPI


def sources():
    plan=json.loads(hf_library.PLAN.read_text())
    for repo in plan['plan']:
        if repo['repo_type']!='dataset':continue
        directory=Path(repo['directory'])
        receipt=json.loads((directory/'archive-receipt.json').read_text())
        if receipt.get('revision')!=repo['revision'] or not receipt.get('download_verified'):continue
        verified={row['path'] for row in receipt['files'] if row.get('source_integrity_verified')}
        for item in repo['files']:
            if item['path'].endswith('.parquet') and item['path'] in verified:
                import hf_vault_heist as vault
                path=vault.contained(directory,item['path'])
                yield path,'hf-archive:dataset:'+repo['repo_id']+'@'+repo['revision']+'/'+item['path'],item
    catalogue=hf_mirror.ROOT/'catalogue.sqlite'
    if catalogue.is_file():
        with closing(__import__('sqlite3').connect('file:'+str(catalogue)+'?mode=ro',uri=True)) as conn:
            rows=conn.execute("SELECT repo,revision,path,size,source_hash,hash_type,local_path FROM files WHERE kind='dataset' AND state='verified' AND path LIKE '%.parquet'").fetchall()
            rows=[row for row in rows if hf_mirror.dataset_repo_allowed(row[0],conn=conn)]
        for repo,revision,path,size,digest,kind,local in rows:
            yield Path(local),'hf-mirror:dataset:'+repo+'@'+revision+'/'+path,{'size':size,'source_hash':digest,'source_hash_type':kind}


def main():
    index.DATABASE.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock=(index.DATABASE.parent/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    api=AgentAPI('apex')
    def progress():
        while True:
            try:
                status=index.status()
                paused=hf_mirror.downloads_paused()
                complete=bool(status.get('file_states') and set(status['file_states'])=={'indexed'})
                activity_status='completed' if complete else ('queued' if paused else 'running')
                stage='Dataset index: '+('paused; ' if paused and not complete else '')+str(status.get('dataset_rows_processed',0))+' rows processed'
                api.call('/api/agent/v1/progress',{'conversation_id':2833,'activity_id':'hf-dataset-index',
                    'status':activity_status,'stage':stage})
            except Exception:pass
            time.sleep(30)
    threading.Thread(target=progress,daemon=True).start()
    while True:
        if hf_mirror.downloads_paused():
            time.sleep(10)
            continue
        for path,reference,expected in sources():
            try:index.index_parquet(path,reference,expected)
            except Exception as exc:
                with closing(index.connect()) as conn,conn:
                    conn.execute('INSERT OR IGNORE INTO files(reference,path,source_hash,state) VALUES (?,?,?,\'blocked\')',
                        (reference,str(path),expected['source_hash']))
                    conn.execute("UPDATE files SET state='blocked',error=? WHERE reference=?",(type(exc).__name__+': dataset indexing failed',reference))
        time.sleep(60)


if __name__=='__main__':main()
