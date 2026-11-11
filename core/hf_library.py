"""Index verified local archive metadata/cards into HB's existing Knowledge Library."""
from pathlib import Path
from contextlib import closing
import hashlib
import json
import sqlite3
from utils.db._connection import get_connection

PLAN=Path('/mnt/archive/hf_archive/.hummingbird-archive-plan.json')



def managed_plan(plan_path=None):
    """Merge only fixed-format sibling shortlist manifests; never change pinned plans."""
    import re
    plan_path=Path(plan_path or PLAN)
    if plan_path.is_symlink() or plan_path.stat().st_size>2_000_000:
        raise ValueError('Untrusted archive plan')
    primary=json.loads(plan_path.read_text())
    root=Path(primary['vault']).resolve()
    if plan_path.resolve().parent!=root or not isinstance(primary.get('plan'),list):
        raise ValueError('Archive plan must live in its declared vault')
    paths=[p for p in root.glob('.hummingbird-shortlist-*.json')
           if re.fullmatch(r'\.hummingbird-shortlist-[0-9a-f]{64}\.json',p.name)]
    if len(paths)>32:raise ValueError('Too many managed archive shortlists')
    plans=[primary]
    for path in sorted(paths):
        if path==plan_path:continue
        if path.is_symlink() or path.stat().st_size>2_000_000:
            raise ValueError('Untrusted archive shortlist')
        item=json.loads(path.read_text())
        if Path(item['vault']).resolve()!=root or not isinstance(item.get('plan'),list):
            raise ValueError('Archive shortlist does not match vault')
        plans.append(item)
    repos={}
    for plan in plans:
        for repo in plan['plan']:
            directory=Path(repo['directory'])
            if directory.is_symlink() or not directory.resolve().is_relative_to(root):
                raise ValueError('Archive directory escapes the vault')
            key=(repo.get('repo_type'),repo['repo_id'],repo['revision'])
            if key not in repos:
                repos[key]={**repo,'files':[]}
            elif Path(repos[key]['directory']).resolve()!=directory.resolve():
                raise ValueError('Conflicting archive repository directories')
            files={item['path']:item for item in repos[key]['files']}
            for item in repo['files']:
                relative=Path(item['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Archive file escapes repository')
                if item['path'] in files and files[item['path']]!=item:
                    raise ValueError('Conflicting pinned archive file')
                files[item['path']]=item
            repos[key]['files']=list(files.values())
    return {**primary,'plan':list(repos.values())}


def archive_status(view='summary', offset=0):
    if view not in {'summary', 'files', 'blocked'} or type(offset) is not int or not 0 <= offset <= 1_000_000:
        raise ValueError('archive_status accepts view summary/files/blocked and a nonnegative offset up to 1000000')
    if view != 'summary':
        return archive_inventory(view, offset)
    from core.hummingbird_status import _archive_progress
    status=_archive_progress()
    with closing(get_connection()) as conn:
        exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_sources'").fetchone()
        status['indexed_archive_documents']=(conn.execute("SELECT count(*) FROM knowledge_sources WHERE source_ref LIKE 'hf-archive:%' AND status='active'").fetchone()[0] if exists else 0)
    from core.hf_mirror import status as mirror_status
    status['full_public_hub']=mirror_status(include_totals=False)
    status['scope']='Pinned archive and managed acquisition shortlists; full-public-Hub mirror remains separate.'
    from core.hf_text_index import status as text_status
    status['dataset_row_indexing']=text_status(include_chunks=False)
    status['notice']='A verified download is not proof that dataset contents are indexed or that model weights have been trained.'
    status['file_inventory']={'tool':'archive_status','arguments':{'view':'files','offset':0},
        'blocked_arguments':{'view':'blocked','offset':0},
        'notice':'Use these paginated inventories for exact filenames and indexing errors. Source grep and dataset example searches are not file inventories.'}
    return status


def archive_inventory(view, offset):
    """Read fixed archive manifests and index journals; never scan arbitrary paths or download."""
    from core import hf_text_index, hf_mirror
    page_size = 8
    rows, manifests = [], []
    index_rows = {}
    if hf_text_index.DATABASE.is_file():
        if hf_text_index.DATABASE.is_symlink():
            raise ValueError('Symlinked text index is unavailable')
        with closing(sqlite3.connect(hf_text_index.DATABASE.as_uri()+'?mode=ro', uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            if view == 'blocked':
                total = conn.execute("SELECT count(*) FROM files WHERE state IN ('blocked','capacity_blocked')").fetchone()[0]
                rows = [dict(row) for row in conn.execute(
                    "SELECT reference,path,next_row,total_rows,state,error FROM files WHERE state IN ('blocked','capacity_blocked') ORDER BY reference LIMIT ? OFFSET ?",
                    (page_size, offset))]
            else:
                # Lookups below are limited to the pinned plan, not millions of example rows.
                for row in conn.execute("SELECT reference,next_row,total_rows,state,error FROM files WHERE reference LIKE 'hf-archive:%'"):
                    index_rows[row['reference']] = dict(row)
    elif view == 'blocked':
        total = 0

    plan = managed_plan()
    root = Path(plan['vault']).resolve()
    if PLAN.is_symlink() or PLAN.resolve().parent != root:
        raise ValueError('Archive plan must live in its declared vault')

    def observed_size(path, allowed_root):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(allowed_root.resolve()) or not path.is_file():
            return None
        return path.stat().st_size

    if view == 'blocked':
        for row in rows:
            source = 'pinned' if row['reference'].startswith('hf-archive:') else 'mirror'
            size = observed_size(row.pop('path'), root if source == 'pinned' else hf_mirror.ROOT)
            row.update(source_scope=source, observed_bytes=size,
                       file_diagnosis='empty_file_cannot_be_parquet' if size == 0 else 'requires_format_inspection')
        return {'view':view, 'items':rows, 'total':total,
                'next_offset':offset+page_size if offset+page_size < total else None,
                'next_action':'Separate pinned-plan failures from mirror failures. Empty files cannot supply Parquet rows; do not assume every blocked entry needs downloading again.',
                'notice':'Read-only journal and local-size observations. No downloads, index writes or repairs were executed.'}

    with closing(get_connection()) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def knowledge(reference):
            if not {'knowledge_sources','knowledge_chunks'} <= tables:
                return {'state':'not_indexed'}
            row = conn.execute("SELECT source_id FROM knowledge_sources WHERE source_ref=? AND status='active' ORDER BY source_id LIMIT 1", (reference,)).fetchone()
            if not row:
                return {'state':'not_indexed'}
            count = conn.execute('SELECT count(*) FROM knowledge_chunks WHERE source_id=?', (row[0],)).fetchone()[0]
            return {'state':'indexed' if count else 'source_without_chunks', 'source_id':row[0], 'chunks':count}

        for repo in plan['plan']:
            directory = Path(repo['directory'])
            if directory.is_symlink() or not directory.resolve().is_relative_to(root):
                raise ValueError('Archive directory escapes the vault')
            receipt_path = directory/'archive-receipt.json'
            if receipt_path.is_symlink():
                raise ValueError('Symlinked archive receipt is unavailable')
            receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
            verified = {item['path']:item for item in receipt.get('files', []) if item.get('source_integrity_verified')}
            base = 'hf-archive:'+repo['repo_type']+':'+repo['repo_id']+'@'+repo['revision']
            manifests.append({'repository':repo['repo_id'], 'revision':repo['revision'], 'knowledge_manifest':knowledge(base+'/manifest')})
            for item in repo['files']:
                import hf_vault_heist as vault
                path = vault.contained(directory, item['path'])
                size = observed_size(path, root)
                entry = verified.get(item['path'], {})
                matched = (receipt.get('download_verified') and receipt.get('revision') == repo['revision']
                           and all(entry.get(key) == item.get(key) for key in ('size','source_hash','source_hash_type')))
                reference = base+'/'+item['path']
                index = index_rows.get(reference)
                card = Path(item['path']).name.lower().startswith(('readme','license','notice'))
                rows.append({'repository':repo['repo_id'], 'revision':repo['revision'], 'filename':item['path'],
                    'expected_bytes':item['size'], 'observed_bytes':size,
                    'download_state':'receipt_verified_size_matches' if matched and size == item['size'] else 'needs_verification',
                    'text_index':{key:index[key] for key in ('state','next_row','total_rows','error')} if index else
                        {'state':'not_indexed' if item['path'].endswith('.parquet') else 'not_applicable'},
                    'knowledge_card':knowledge(reference) if card else {'state':'not_applicable'}})
    total = len(rows)
    text_files = [row for row in rows if row['filename'].endswith('.parquet')]
    cards = [row['knowledge_card'] for row in rows if row['knowledge_card']['state'] != 'not_applicable']
    metadata = cards + [row['knowledge_manifest'] for row in manifests]
    coverage = {'pinned_files':total,
                'recorded_verification_and_size_match':sum(row['download_state']=='receipt_verified_size_matches' for row in rows),
                'knowledge_documents_expected':len(metadata),
                'knowledge_documents_with_chunks':sum(row['state']=='indexed' for row in metadata),
                'parquet_files':len(text_files),
                'parquet_checkpoints_complete':sum(row['text_index']['state']=='indexed' and
                    row['text_index'].get('next_row') == row['text_index'].get('total_rows') for row in text_files)}
    return {'view':view, 'scope':'pinned_plan_and_managed_shortlists', 'items':rows[offset:offset+page_size], 'total':total,
            'coverage':coverage, 'manifests':manifests, 'next_offset':offset+page_size if offset+page_size < total else None,
            'next_action':'Report actual filenames and their separate download, Knowledge Centre and text-index states. Compare blocked mirror entries separately before proposing useful additions.',
            'notice':'Recorded source verification plus current file size; hashes were not recomputed by this read. Model weights are not text-index candidates. No downloads or indexing were started.'}


def _documents(plan_path):
    import hf_vault_heist as archive
    plan_path=Path(plan_path)
    plan=json.loads(plan_path.read_text())
    root=Path(plan['vault']).resolve()
    if plan_path.is_symlink() or plan_path.resolve().parent!=root:
        raise ValueError('Archive plan must live in its declared vault')
    for repo in plan['plan']:
        directory=Path(repo['directory'])
        if directory.is_symlink() or not directory.resolve().is_relative_to(root):
            raise ValueError('Archive directory escapes the vault')
        receipt_path=directory/'archive-receipt.json'
        if receipt_path.is_symlink():raise ValueError('Symlinked receipt is unavailable')
        receipt=json.loads(receipt_path.read_text())
        if not receipt.get('download_verified') or receipt.get('revision')!=repo['revision']:
            raise ValueError('Archive repository has no verified receipt: '+repo['repo_id'])
        verified={item['path']:item for item in receipt['files'] if item.get('source_integrity_verified')}
        if any(item['path'] not in verified or any(verified[item['path']].get(key)!=item.get(key)
               for key in ('size','source_hash','source_hash_type')) for item in repo['files']):
            raise ValueError('Archive receipt does not verify every planned file')
        base='hf-archive:'+repo['repo_type']+':'+repo['repo_id']+'@'+repo['revision']
        manifest={'repository':repo['repo_id'],'kind':repo['repo_type'],'revision':repo['revision'],
            'license':repo.get('license'),'download_verified':True,
            'files':[{'path':item['path'],'bytes':item['size']} for item in repo['files']],
            'dataset_rows_indexed':False,
            'reference_only':'Downloaded assets and cards; this does not train a model or grant execution permission.'}
        yield base+'/manifest',repo['repo_id']+' — local archive manifest',json.dumps(manifest,indent=2)
        for item in repo['files']:
            if not Path(item['path']).name.lower().startswith(('readme','license','notice')):
                continue
            if item['size']>1_000_000:
                raise ValueError('Archive metadata document exceeds 1 MB: '+item['path'])
            path=archive.contained(directory,item['path'])
            if path.is_symlink() or path.stat().st_size!=item['size']:
                raise ValueError('Archive metadata file changed: '+item['path'])
            archive.verify_file(directory,item)
            text=path.read_text(encoding='utf-8',errors='replace')
            yield base+'/'+item['path'],repo['repo_id']+' — '+item['path'],text


def ingest(plan_path=None):
    from lib.knowledge import store
    from lib.knowledge.ingest import chunk_text
    store.ensure_schema()
    rows=[]
    for reference,title,text in _documents(plan_path or PLAN):
        digest=store._hash_content(text)
        with closing(get_connection()) as conn:
            existing=conn.execute('SELECT source_id,content_hash FROM knowledge_sources WHERE source_ref=? ORDER BY source_id LIMIT 1',(reference,)).fetchone()
        if existing and existing[1]==digest:
            rows.append({'source_id':existing[0],'state':'unchanged','title':title})
            continue
        if existing:
            # Pinned references are immutable. Do not silently replace prior knowledge.
            raise ValueError('Pinned archive reference already has different content: '+reference)
        source_id=store.add_source(title,'text',text,source_ref=reference,
            domain_tags=['huggingface','verified-archive','reference-only'],added_by='apex',
            category='general',subcategory='huggingface')
        store.save_chunks(source_id,[(part,None) for part in chunk_text(text)])
        rows.append({'source_id':source_id,'state':'indexed','title':title})
    return {'status':'indexed','documents':rows,'search':'literal keyword retrieval available without embeddings',
            'dataset_rows_indexed':False,'notice':'Model/dataset cards and manifests indexed. Binary weights and full dataset rows are separate work.'}
