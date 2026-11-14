from pathlib import Path
import hashlib,json,sqlite3
from core import hf_library,apex_knowledge
from lib.knowledge import store
import pytest


def archive(tmp_path):
    root=tmp_path/'vault';folder=root/'dataset'/'example'/'revision';folder.mkdir(parents=True)
    body=b'# Useful data\nThis dataset teaches local retrieval with verified provenance.\n'
    (folder/'README.md').write_bytes(body)
    item={'path':'README.md','size':len(body),'source_hash':hashlib.sha256(body).hexdigest(),'source_hash_type':'sha256'}
    repo={'repo_id':'example/dataset','repo_type':'dataset','revision':'abc','license':'mit',
          'directory':str(folder),'files':[item]}
    (folder/'archive-receipt.json').write_text(json.dumps({'download_verified':True,'revision':'abc',
        'files':[{**item,'source_integrity_verified':True}]}))
    plan=root/'.hummingbird-archive-plan.json';plan.write_text(json.dumps({'vault':str(root),'plan':[repo]}))
    return plan,folder


def test_verified_archive_cards_are_searchable_and_ingest_is_idempotent(tmp_path,monkeypatch):
    path=tmp_path/'knowledge.sqlite'
    def connect():
        conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row;return conn
    monkeypatch.setattr(hf_library,'get_connection',connect)
    monkeypatch.setattr(apex_knowledge,'get_connection',connect)
    monkeypatch.setattr(store,'_conn',connect)
    plan,folder=archive(tmp_path)
    result=hf_library.ingest(plan)
    assert len(result['documents'])==2 and not result['dataset_rows_indexed']
    assert all(row['state']=='unchanged' for row in hf_library.ingest(plan)['documents'])
    items=apex_knowledge.search('retrieval')['items']
    assert items and 'verified provenance' in apex_knowledge.read(items[0]['document_id'])['content']
    assert 'hf-archive:' in items[0]['source_ref']
    (folder/'README.md').write_text('changed bytes')
    with pytest.raises(ValueError):hf_library.ingest(plan)


def test_receipt_must_match_revision_and_each_manifest_file(tmp_path):
    plan,folder=archive(tmp_path)
    receipt=folder/'archive-receipt.json';data=json.loads(receipt.read_text());data['revision']='different';receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='verified receipt'):list(hf_library._documents(plan))


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    from core import hf_text_index, hf_mirror
    plan, folder = archive(tmp_path)
    monkeypatch.setattr(hf_library, 'PLAN', plan)
    index_path = tmp_path/'index.sqlite'
    monkeypatch.setattr(hf_text_index, 'DATABASE', index_path)
    mirror = tmp_path/'mirror';mirror.mkdir()
    monkeypatch.setattr(hf_mirror, 'ROOT', mirror)
    knowledge_path = tmp_path/'knowledge.sqlite'
    def connect():
        conn=sqlite3.connect(knowledge_path);conn.row_factory=sqlite3.Row;return conn
    monkeypatch.setattr(hf_library, 'get_connection', connect)
    base='hf-archive:dataset:example/dataset@abc'
    with connect() as conn:
        conn.executescript('CREATE TABLE knowledge_sources(source_id INTEGER,source_ref TEXT,status TEXT); CREATE TABLE knowledge_chunks(source_id INTEGER);')
        for n, suffix in enumerate(['/manifest','/README.md'],1):
            conn.execute("INSERT INTO knowledge_sources VALUES (?,?,'active')",(n,base+suffix))
            conn.execute('INSERT INTO knowledge_chunks VALUES (?)',(n,))
    empty=mirror/'empty.parquet';empty.write_bytes(b'')
    with hf_text_index.connect(index_path) as conn:
        conn.execute("INSERT INTO files(reference,path,state,error) VALUES (?,?,'blocked','ArrowInvalid: dataset indexing failed')",
                     ('hf-mirror:dataset:example/mirror@def/empty.parquet',str(empty)))
    return plan, folder, index_path, knowledge_path


def test_inventory_separates_file_verification_knowledge_and_dataset_index(inventory):
    plan,folder,index_path,knowledge_path=inventory
    result=hf_library.archive_status(view='files')
    assert result['total']==1 and result['next_offset'] is None
    row=result['items'][0]
    assert row['filename']=='README.md' and row['revision']=='abc'
    assert row['download_state']=='receipt_verified_size_matches'
    assert row['knowledge_card']=={'state':'indexed','source_id':2,'chunks':1}
    assert row['text_index']['state']=='not_applicable'
    assert result['manifests'][0]['knowledge_manifest']['source_id']==1
    (folder/'README.md').write_bytes(b'changed')
    assert hf_library.archive_status(view='files')['items'][0]['download_state']=='needs_verification'


def test_blocked_inventory_names_empty_mirror_files_without_claiming_pinned_failure(inventory):
    _,_,index_path,knowledge_path=inventory
    before={p:p.read_bytes() for p in [index_path,knowledge_path]}
    result=hf_library.archive_status(view='blocked')
    row=result['items'][0]
    assert row['source_scope']=='mirror' and row['observed_bytes']==0
    assert row['file_diagnosis']=='empty_file_cannot_be_parquet'
    assert row['error']=='ArrowInvalid: dataset indexing failed'
    assert 'example/mirror@def/empty.parquet' in row['reference']
    assert all(p.read_bytes()==body for p,body in before.items())


def test_inventory_paginates_exact_filenames_and_keeps_row_checkpoints(inventory):
    from core import hf_text_index
    plan,folder,index_path,_=inventory
    data=json.loads(plan.read_text());receipt_path=folder/'archive-receipt.json';receipt=json.loads(receipt_path.read_text())
    for n in range(10):
        name=f'data-{n:02}.parquet';(folder/name).write_bytes(b'PAR1')
        item={'path':name,'size':4,'source_hash':'recorded-hash','source_hash_type':'sha256'}
        data['plan'][0]['files'].append(item);receipt['files'].append({**item,'source_integrity_verified':True})
    plan.write_text(json.dumps(data));receipt_path.write_text(json.dumps(receipt))
    with hf_text_index.connect(index_path) as conn:
        conn.execute("INSERT INTO files(reference,state,next_row,total_rows) VALUES (?,'indexed',12,12)",
                     ('hf-archive:dataset:example/dataset@abc/data-00.parquet',))
    first=hf_library.archive_status(view='files');second=hf_library.archive_status(view='files',offset=first['next_offset'])
    assert first['next_offset']==8 and second['next_offset'] is None and first['total']==11
    rows=first['items']+second['items']
    assert len({r['filename'] for r in rows})==11
    indexed=next(r for r in rows if r['filename']=='data-00.parquet')['text_index']
    assert indexed=={'state':'indexed','next_row':12,'total_rows':12,'error':None}
    assert next(r for r in rows if r['filename']=='data-01.parquet')['text_index']['state']=='not_indexed'


@pytest.mark.parametrize('args',[{'view':'../../etc'},{'offset':True},{'offset':-1},{'offset':1000001}])
def test_inventory_rejects_invalid_views_and_offsets(args):
    with pytest.raises(ValueError,match='archive_status accepts'):
        hf_library.archive_status(**args)


def test_managed_shortlist_is_visible_in_inventory_and_deduplicated(inventory):
    plan,folder,_,_=inventory
    data=json.loads(plan.read_text())
    added={**data['plan'][0],'repo_id':'example/second','revision':'def'}
    shortlist=plan.parent/('.hummingbird-shortlist-'+'a'*64+'.json')
    shortlist.write_text(json.dumps({'vault':str(plan.parent),'plan':[data['plan'][0],added]}))
    result=hf_library.archive_status(view='files')
    assert result['total']==2
    assert {x['repository'] for x in result['items']}=={'example/dataset','example/second'}
    assert result['scope']=='pinned_plan_and_managed_shortlists'
    assert json.loads(plan.read_text())==data
    shortlist.unlink();shortlist.symlink_to(plan)
    with pytest.raises(ValueError,match='Untrusted archive shortlist'):hf_library.managed_plan()


def test_managed_shortlist_cannot_change_pinned_file_or_escape_vault(inventory):
    plan,_,_,_=inventory
    data=json.loads(plan.read_text());repo=data['plan'][0]
    shortlist=plan.parent/('.hummingbird-shortlist-'+'b'*64+'.json')
    repo['files'][0]['size']+=1
    shortlist.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Conflicting pinned archive file'):hf_library.managed_plan()
    repo['directory']=str(plan.parent.parent)
    shortlist.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='escapes the vault'):hf_library.managed_plan()


def test_chat_summary_requests_only_bounded_control_and_row_checkpoints(inventory,monkeypatch):
    from core import hf_mirror,hf_text_index,hummingbird_status
    monkeypatch.setattr(hummingbird_status,'_archive_progress',lambda:{'state':'verified'})
    def mirror(**kwargs):
        assert kwargs=={'include_totals':False}
        return {'downloads_paused':True,'totals_included':False}
    def text(**kwargs):
        assert kwargs=={'include_chunks':False}
        return {'dataset_rows_processed':12}
    monkeypatch.setattr(hf_mirror,'status',mirror);monkeypatch.setattr(hf_text_index,'status',text)
    summary=hf_library.archive_status()
    assert summary['full_public_hub']['downloads_paused'] and summary['dataset_row_indexing']['dataset_rows_processed']==12


def test_fast_mirror_status_does_not_read_repository_or_file_tables(tmp_path):
    from core import hf_mirror
    with sqlite3.connect(tmp_path/'catalogue.sqlite') as c:
        c.execute('CREATE TABLE settings(key TEXT,value TEXT)')
        c.execute("INSERT INTO settings VALUES('downloads_paused','true')")
    result=hf_mirror.status(tmp_path,include_totals=False)
    assert result['downloads_paused'] is True and result['state']=='paused'
    assert result['totals_included'] is False and 'files_known' not in result


def test_fast_text_status_uses_checkpoints_without_scanning_documents(tmp_path,monkeypatch):
    from core import hf_text_index
    path=tmp_path/'index.sqlite';monkeypatch.setattr(hf_text_index,'DATABASE',path)
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE files(state TEXT,next_row INTEGER,total_rows INTEGER)')
        c.execute("INSERT INTO files VALUES('indexed',12,12)")
    result=hf_text_index.status(include_chunks=False)
    assert result['dataset_rows_processed']==12 and 'textual_chunks_indexed' not in result
