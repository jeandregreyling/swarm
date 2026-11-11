from contextlib import closing
import hashlib,json,sqlite3,sys
from types import SimpleNamespace
import pytest
from core import hf_text_index as index,apex_knowledge


def test_dataset_text_is_searchable_cited_and_idempotent(tmp_path,monkeypatch):
    path=tmp_path/'text.sqlite';monkeypatch.setattr(index,'DATABASE',path)
    with closing(index.connect()) as conn:
        conn.execute("INSERT INTO files(reference,path,source_hash,state) VALUES ('dataset@sha/file.parquet','file','sha','pending')");conn.commit()
        rows=[{'question':'How do I verify tools?','response':'Check the actual action receipt.'},
              {'image':b'binary image','description':'Public sample'}, {'text':'x'*6200+' memory evidence'}]
        assert index.index_rows(conn,'dataset@sha/file.parquet','Dataset',rows,total=3)
        count=conn.execute('SELECT count(*) FROM documents').fetchone()[0]
        index.index_rows(conn,'dataset@sha/file.parquet','Dataset',rows,total=3)
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0]==count
    found=index.search('actual receipt')
    assert found and found[0]['document_id']>=index.DOCUMENT_ID
    page=apex_knowledge.read(found[0]['document_id'])
    assert 'receipt' in page['content'] and '#row=' in page['source_ref']
    assert index.status()['dataset_rows_processed']==3
    assert index.search('" OR *')==[]


def test_capacity_pause_keeps_checkpoint_before_uncommitted_rows(tmp_path):
    with closing(index.connect(tmp_path/'text.sqlite')) as conn:
        conn.execute("INSERT INTO files(reference,state) VALUES ('source','pending')");conn.commit()
        checks=iter([True,False])
        assert not index.index_rows(conn,'source','Source',[{'text':'one'},{'text':'two'}],space_check=lambda:next(checks))
        assert tuple(conn.execute('SELECT next_row,state FROM files').fetchone())==(0,'capacity_blocked')
        assert index.index_rows(conn,'source','Source',[{'text':'one'},{'text':'two'}])
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0]==2


def test_parquet_resume_skips_already_processed_row_groups(tmp_path,monkeypatch):
    file=tmp_path/'data.parquet';body=b'parquet fixture';file.write_bytes(body)
    db=tmp_path/'index.sqlite';expected={'size':len(body),'source_hash':hashlib.sha256(body).hexdigest(),'source_hash_type':'sha256'}
    seen=[]
    class Parquet:
        def __init__(self,path):
            self.metadata=SimpleNamespace(num_rows=6,num_row_groups=2,row_group=lambda _:SimpleNamespace(num_rows=3))
        def iter_batches(self,**kwargs):
            seen.append(kwargs)
            yield SimpleNamespace(to_pylist=lambda:[{'text':'four'},{'text':'five'},{'text':'six'}])
    fake=SimpleNamespace(ParquetFile=Parquet)
    monkeypatch.setitem(sys.modules,'pyarrow',SimpleNamespace(parquet=fake))
    monkeypatch.setitem(sys.modules,'pyarrow.parquet',fake)
    monkeypatch.setattr(index.shutil,'disk_usage',lambda _:SimpleNamespace(free=index.RESERVE_BYTES+1))
    with closing(index.connect(db)) as c:
        c.execute("INSERT INTO files(reference,path,source_hash,next_row,total_rows,state) VALUES ('source',?,?,3,6,'indexing')",(str(file),expected['source_hash']));c.commit()
    result=index.index_parquet(file,'source',expected,database=db)
    assert result['rows']==6 and seen[0]['row_groups']==[1]
    assert seen[0]['use_threads'] is False
