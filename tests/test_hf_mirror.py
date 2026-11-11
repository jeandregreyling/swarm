from pathlib import Path
from types import SimpleNamespace
import hashlib
import pytest
from core import hf_mirror as mirror


class Page:
    def __init__(self,data,next_url=None):
        self.data=data;self.links={'next':{'url':next_url}} if next_url else {}
    def raise_for_status(self):pass
    def json(self):return self.data


def test_inventory_cursor_is_durable_and_rejects_external_pagination(tmp_path):
    conn=mirror.connect(tmp_path/'mirror')
    replies=iter([Page([{'id':'owner/public'},{'id':'owner/private','private':True}],
        'https://huggingface.co/api/models?cursor=page2'),Page([{'id':'owner/second'}])])
    urls=[]
    session=SimpleNamespace(get=lambda url,timeout:urls.append(url) or next(replies))
    mirror.inventory_page(conn,'model',session)
    mirror.inventory_page(conn,'model',session)
    assert 'cursor=page2' in urls[1]
    assert {r[0] for r in conn.execute('SELECT id FROM repos')}=={'owner/public','owner/second'}
    assert mirror.inventory_page(conn,'model',session)==0
    with pytest.raises(ValueError):mirror._url('https://evil.example/api/models','model')
    conn.close()


def test_whole_manifest_pins_every_file_and_verifies_git_and_lfs_content(tmp_path,monkeypatch):
    root=tmp_path/'mirror';conn=mirror.connect(root)
    body=b'public source data'
    git=hashlib.sha1(f'blob {len(body)}\0'.encode()+body).hexdigest()
    sha=hashlib.sha256(body).hexdigest()
    files=[SimpleNamespace(rfilename='README.md',size=len(body),lfs=None,blob_id=git),
           SimpleNamespace(rfilename='weights.bin',size=len(body),lfs=SimpleNamespace(sha256=sha),blob_id=None)]
    seen=[]
    api=SimpleNamespace(repo_info=lambda repo,**kwargs:seen.append(kwargs) or
                        SimpleNamespace(sha='a'*40,private=False,gated=False,siblings=files))
    conn.execute("INSERT INTO repos(kind,id) VALUES ('model','owner/model')");conn.commit()
    mirror.manifest(conn,'model','owner/model',api)
    assert seen[0]['files_metadata'] and seen[0]['token'] is False
    monkeypatch.setattr(mirror.shutil,'disk_usage',lambda _:SimpleNamespace(free=10000))
    def download(**kwargs):
        assert kwargs['revision']=='a'*40 and kwargs['token'] is False
        path=root/'hub-cache'/kwargs['filename'];path.parent.mkdir(exist_ok=True);path.write_bytes(body);return str(path)
    for row in conn.execute('SELECT * FROM files').fetchall():
        assert mirror.transfer_one(conn,row,download,root,reserve=1)
    assert conn.execute("SELECT state FROM repos").fetchone()[0]=='verified'
    assert mirror.status(root)['files_verified']==2
    assert mirror.catalogue_search('model',root)[0]['document_id']>=mirror.CATALOGUE_ID
    assert 'owner/model' in mirror.catalogue_read(mirror.CATALOGUE_ID+1,root=root)['content']
    conn.close()


def test_capacity_pause_does_not_start_download_or_claim_completion(tmp_path,monkeypatch):
    root=tmp_path/'mirror';conn=mirror.connect(root)
    conn.execute("INSERT INTO files(kind,repo,revision,path,size,source_hash,hash_type) VALUES ('model','a/b','r','large.bin',100,'abc','sha256')");conn.commit()
    row=conn.execute('SELECT * FROM files').fetchone()
    monkeypatch.setattr(mirror.shutil,'disk_usage',lambda _:SimpleNamespace(free=90))
    assert not mirror.transfer_one(conn,row,lambda **_:pytest.fail('must not download'),root,reserve=10)
    assert mirror.status(root)['state']=='capacity_blocked'
    assert mirror.status(root)['files_verified']==0
    conn.close()


def test_manifest_rejects_escaping_paths_and_records_gated_access(tmp_path):
    conn=mirror.connect(tmp_path/'mirror')
    conn.execute("INSERT INTO repos(kind,id) VALUES ('dataset','a/b')");conn.commit()
    api=SimpleNamespace(repo_info=lambda *_a,**_k:SimpleNamespace(sha='a'*40,gated=True,private=False))
    mirror.manifest(conn,'dataset','a/b',api)
    assert conn.execute('SELECT state FROM repos').fetchone()[0]=='access_blocked'
    api.repo_info=lambda *_a,**_k:SimpleNamespace(sha='a'*40,gated=False,private=False,siblings=[SimpleNamespace(rfilename='../escape')])
    with pytest.raises(ValueError):mirror.manifest(conn,'dataset','a/b',api)
    conn.close()
