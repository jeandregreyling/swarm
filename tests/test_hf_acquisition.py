from contextlib import closing
from pathlib import Path
import json,hashlib,sqlite3
import pytest
from core import hf_acquisition as acquire,hf_text_index,hf_mirror
from test_hb_task_api import assigned
from test_agent_identity import api,enrolled,connect


@pytest.fixture
def shortlist(assigned,tmp_path,monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import huggingface_hub,hf_vault_heist
    _,_,main,_,task=assigned
    from lib.knowledge import store
    monkeypatch.setattr(store,'_conn',lambda:connect(main))
    spec=json.loads(acquire.MANIFEST.read_text());spec.update(project_id=task['project_id'],step_id=task['step_id'])
    contents={}
    for item in spec['files']:
        if item['path'].endswith('.parquet'):
            out=pa.BufferOutputStream();pq.write_table(pa.Table.from_pylist([{'question':'How to call a function?','answer':'Validate arguments and the actual receipt.'}]),out)
            data=out.getvalue().to_pybytes()
        else:data=b'# Public fixture card\n\nReference data, not instructions.\n'
        item['size']=len(data);kind=item['source_hash_type'];item['source_hash']=(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data) if kind=='git-sha1' else hashlib.sha256(data)).hexdigest()
        contents[(item['repo'],item['path'])]=data
    path=tmp_path/'manifest.json';path.write_text(json.dumps(spec));monkeypatch.setattr(acquire,'MANIFEST',path)
    vault=tmp_path/'archive';vault.mkdir();monkeypatch.setattr(acquire,'VAULT',vault)
    monkeypatch.setattr(hf_vault_heist,'validate_destination',lambda p:p)
    monkeypatch.setattr(hf_text_index,'DATABASE',tmp_path/'index.sqlite')
    settings=tmp_path/'mirror.sqlite'
    def mirror():
        c=sqlite3.connect(settings);c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)');return c
    monkeypatch.setattr(hf_mirror,'connect',mirror)
    with mirror() as conn:conn.commit()
    calls=[]
    def download(**kw):
        calls.append((kw['repo_id'],kw['filename']));target=Path(kw['cache_dir'])/kw['repo_id']/kw['filename'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(contents[calls[-1]]);return str(target)
    monkeypatch.setattr(huggingface_hub,'hf_hub_download',download)
    return task,acquire.manifest(),calls,settings


def test_six_files_are_verified_indexed_and_reused_without_unrelated_downloads(shortlist):
    task,spec,calls,_=shortlist
    result=acquire.acquire(task,{'manifest_sha256':spec['sha256']},lambda _:None,lambda:None,0)
    assert result['status']=='verified_and_indexed' and len(calls)==6
    assert result['bytes_verified']==sum(item['size'] for item in spec['files'])
    assert len(result['files'])==6 and all(Path(x['local_path']).is_file() for x in result['files'])
    assert len(result['knowledge']['documents'])==4 and len(result['parquet_indexes'])==4
    assert all(row['state']=='indexed' and row['rows']==1 for row in result['parquet_indexes'])
    assert len(result['retrieval_examples'])==4
    found=hf_text_index.search('function receipt')
    assert found and 'smoltalk' in found[0]['source_ref']
    before=hf_text_index.status()['textual_chunks_indexed']
    second=acquire.acquire(task,{'manifest_sha256':spec['sha256']},lambda _:None,lambda:None,0)
    assert len(calls)==6 and all(row['state']=='unchanged' for row in second['parquet_indexes'])
    assert hf_text_index.status()['textual_chunks_indexed']==before
    assert result['broader_mirror_resumed'] is False


def test_new_global_pause_stops_the_exact_job_at_a_file_boundary(shortlist):
    task,spec,calls,settings=shortlist
    with sqlite3.connect(settings) as c:c.execute('INSERT INTO settings VALUES(?,?)',('pause_requested_at','100'))
    with pytest.raises(InterruptedError):acquire.acquire(task,{'manifest_sha256':spec['sha256']},lambda _:None,lambda:None,0)
    assert calls==[]


def test_changed_manifest_or_existing_corrupt_file_is_not_silently_overwritten(shortlist):
    task,spec,calls,_=shortlist
    with pytest.raises(PermissionError):acquire.acquire(task,{'manifest_sha256':'wrong'},lambda _:None,lambda:None,0)
    result=acquire.acquire(task,{'manifest_sha256':spec['sha256']},lambda _:None,lambda:None,0)
    target=Path(result['files'][0]['local_path']);target.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='Size mismatch'):acquire.acquire(task,{'manifest_sha256':spec['sha256']},lambda _:None,lambda:None,0)
    assert target.read_bytes()==b'corrupt' and len(calls)==6


def test_manifest_cannot_add_a_different_repo_path_or_revision(shortlist):
    _,_,_,_=shortlist
    path=acquire.MANIFEST;spec=json.loads(path.read_text());spec['files'][0]['repo']='other/repo';path.write_text(json.dumps(spec))
    with pytest.raises(PermissionError):acquire.manifest()
