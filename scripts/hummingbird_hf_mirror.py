#!/usr/bin/env python3
"""Run the resumable full-public-Hub inventory/mirror and report progress in HB."""
from pathlib import Path
import sys,time,threading,fcntl
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'frontend'),str(ROOT/'utils')]
from core import hf_mirror as mirror
from scripts.hummingbird_apex_live_check import AgentAPI


def main():
    import requests
    from huggingface_hub import HfApi,hf_hub_download
    from hf_vault_heist import validate_destination
    validate_destination(mirror.ROOT)
    mirror.ROOT.mkdir(exist_ok=True)
    lock=(mirror.ROOT/'mirror.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    api=AgentAPI('apex')
    if api.call('/api/agent/v1/whoami')['principal']!='apex':raise RuntimeError('APEX login mismatch')
    def progress():
        while True:
            try:
                current=mirror.status()
                transfer=current.get('active_transfer') or {}
                stage=('Hub mirror: '+current['state']+'; '+str(current.get('files_verified',0))+' files verified; '
                       +str(transfer.get('repo','cataloguing repositories')))
                api.call('/api/agent/v1/progress',{'conversation_id':2833,'status':'queued' if current['state'] in {'paused','capacity_blocked'} else 'running',
                    'activity_id':'hf-public-mirror','stage':stage[:200]})
            except Exception:pass
            time.sleep(30)
    def catalogue():
        session=requests.Session()
        with closing(mirror.connect()) as conn:
            while True:
                if not mirror.setting(conn,'paused'):
                    for kind in mirror.KINDS:
                        try:mirror.inventory_page(conn,kind,session)
                        except Exception as exc:mirror.setting(conn,'error',type(exc).__name__+': inventory request failed')
                time.sleep(10)
    threading.Thread(target=progress,daemon=True).start()
    threading.Thread(target=catalogue,daemon=True).start()
    with closing(mirror.connect()) as conn:
        hub=HfApi(token=False,endpoint='https://huggingface.co')
        while True:
            if mirror.setting(conn,'paused') or mirror.setting(conn,'downloads_paused'):
                time.sleep(5);continue
            pending=conn.execute("SELECT kind,id FROM repos WHERE state='pending' AND next_attempt<=? ORDER BY rowid LIMIT 1",(time.time(),)).fetchone()
            if pending:
                try:mirror.manifest(conn,pending['kind'],pending['id'],hub)
                except Exception as exc:
                    with conn:conn.execute("UPDATE repos SET state=?,error=?,attempts=attempts+1,next_attempt=? WHERE kind=? AND id=?",
                        ('manifest_blocked' if isinstance(exc,ValueError) else 'pending',
                         type(exc).__name__+': metadata unavailable or invalid',time.time()+300,pending['kind'],pending['id']))
            candidates=conn.execute("SELECT * FROM files WHERE state='pending' AND next_attempt<=? ORDER BY size ASC,rowid LIMIT 128",(time.time(),)).fetchall()
            file=None
            if candidates:
                policy=mirror.acquisition_policy(conn)
                cache={};filtered=[]
                for candidate in candidates:
                    if policy['mode']!='curated':file=candidate;break
                    allowed,reason=mirror.file_allowed(candidate,conn=conn,metadata_cache=cache)
                    if allowed:file=candidate;break
                    filtered.append((reason,candidate['kind'],candidate['repo'],candidate['revision'],candidate['path']))
                if filtered:
                    with conn:conn.executemany("UPDATE files SET state='filtered',error=? WHERE kind=? AND repo=? AND revision=? AND path=?",filtered)
            if file:
                try:
                    if not mirror.transfer_one(conn,file,hf_hub_download):
                        time.sleep(15)
                    else:
                        saved=conn.execute('SELECT local_path FROM files WHERE kind=? AND repo=? AND revision=? AND path=?',
                            (file['kind'],file['repo'],file['revision'],file['path'])).fetchone()
                        mirror.index_card(file,saved[0])
                except Exception as exc:
                    error=type(exc).__name__+': file transfer failed'
                    mirror.setting(conn,'error',error)
                    with conn:
                        conn.execute("UPDATE files SET attempts=attempts+1,state=?,error=?,next_attempt=? WHERE kind=? AND repo=? AND revision=? AND path=?",
                            ('transfer_blocked' if file['attempts']>=4 else 'pending',error,time.time()+300,
                             file['kind'],file['repo'],file['revision'],file['path']))
                        conn.execute("DELETE FROM settings WHERE key='active'")
                    time.sleep(30)
            else:time.sleep(5)


if __name__=='__main__':main()
