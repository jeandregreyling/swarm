"""Acquire only the exact owner-approved pinned shortlist, with real KC/FTS receipts."""
from pathlib import Path,PurePosixPath
from contextlib import closing
import hashlib,json,os,time,shutil
from utils.db._connection import get_connection
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'ops/hf_shortlist.json'
VAULT=Path('/mnt/archive/hf_archive')


def manifest():
    if MANIFEST.is_symlink():raise ValueError('Shortlist manifest cannot be a symlink')
    raw=MANIFEST.read_bytes();spec=json.loads(raw)
    if len(spec['files'])!=6:raise ValueError('The approved shortlist must contain exactly six files')
    scope={
      'HuggingFaceTB/smoltalk':('5feaf2fd3ffca7c237fc38d1861bc30365d48ffa',{'README.md','data/apigen-80k/train-00000-of-00001.parquet','data/self-oss-instruct/train-00000-of-00001.parquet','data/smol-constraints/train-00000-of-00001.parquet'}),
      'google-research-datasets/mbpp':('4bb6404fdc6cacfda99d4ac4205087b89d32030c',{'README.md','sanitized/train-00000-of-00001.parquet'})}
    seen=set()
    for item in spec['files']:
        if item['repo'] not in scope or item['revision']!=scope[item['repo']][0] or item['path'] not in scope[item['repo']][1]:raise PermissionError('File is outside the exact owner-approved shortlist')
        p=PurePosixPath(item['path'])
        if p.is_absolute() or '..' in p.parts or '\\' in item['path'] or p.suffix not in {'.md','.parquet'}:
            raise ValueError('Invalid shortlist path')
        if len(item['revision'])!=40 or any(ch not in '0123456789abcdef' for ch in item['revision']):raise ValueError('Shortlist revision must be pinned')
        length=64 if item['source_hash_type']=='sha256' else 40
        if len(item['source_hash'])!=length or any(ch not in '0123456789abcdef' for ch in item['source_hash']):raise ValueError('Invalid pinned source hash')
        if item['source_hash_type'] not in {'sha256','git-sha1'} or type(item['size']) is not int or not 0<item['size']<60_000_000:raise ValueError('Invalid source verification metadata')
        identity=(item['repo'],item['revision'],item['path'])
        if identity in seen:raise ValueError('Duplicate shortlist file')
        seen.add(identity)
    spec['sha256']=hashlib.sha256(raw).hexdigest();return spec


def acquire(task,payload,stage,boundary,created):
    import hf_vault_heist as vault
    from core import hf_mirror,hf_library,hf_text_index
    from huggingface_hub import hf_hub_download
    spec=manifest()
    if spec['sha256']!=payload['manifest_sha256'] or task['project_id']!=spec['project_id'] or task['step_id']!=spec['step_id']:
        raise PermissionError('The approved acquisition manifest/task changed')
    vault.validate_destination(VAULT)
    grouped={}
    for item in spec['files']:grouped.setdefault((item['repo'],item['revision']),[]).append(item)
    plan={'vault':str(VAULT),'plan':[]};receipts=[]
    def cooperative():
        boundary()
        with closing(hf_mirror.connect()) as conn:paused_at=hf_mirror.setting(conn,'pause_requested_at') or 0
        if paused_at>created:raise InterruptedError('HF pause requested; stopped at a file boundary. Continue the assigned task to resume the exact shortlist.')
    for (repo,revision),files in grouped.items():
        directory=VAULT/'dataset'/repo/revision;directory.mkdir(parents=True,exist_ok=True)
        if directory.is_symlink() or not directory.resolve().is_relative_to(VAULT.resolve()):raise ValueError('Archive directory escaped the managed vault')
        verified=[]
        for item in files:
            cooperative();target=vault.contained(directory,item['path']);target.parent.mkdir(parents=True,exist_ok=True)
            expected={'path':item['path'],'size':item['size'],'source_hash':item['source_hash'],'source_hash_type':item['source_hash_type']}
            stage('Acquiring approved HF file '+repo+'/'+item['path'])
            if target.exists():
                # Never overwrite an existing mismatched file, even when a model asks.
                check=vault.verify_file(directory,expected)
            else:
                vault.check_space(VAULT,item['size']*2,30*1024**3)
                cache=VAULT/'.shortlist-cache'
                if cache.is_symlink():raise ValueError('Archive cache cannot be a symlink')
                saved=Path(hf_hub_download(repo_id=repo,repo_type='dataset',revision=revision,filename=item['path'],cache_dir=str(cache),token=False)).resolve()
                if not saved.is_relative_to(cache.resolve()):raise ValueError('Downloaded file escaped managed cache')
                check=vault.verify_file(saved.parent,{**expected,'path':saved.name})
                temporary=target.with_name(target.name+'.hb-part')
                if temporary.is_symlink():raise ValueError('Transfer staging file cannot be a symlink')
                with saved.open('rb') as source,temporary.open('wb') as dest:shutil.copyfileobj(source,dest);dest.flush();os.fsync(dest.fileno())
                os.replace(temporary,target);check=vault.verify_file(directory,expected)
            verified.append(check);receipts.append({'repository':repo,'revision':revision,'local_path':str(target),**check})
        receipt={'revision':revision,'download_verified':True,'files':verified}
        receipt_path=directory/'archive-receipt.json'
        if receipt_path.is_symlink():raise ValueError('Receipt cannot be a symlink')
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        plan['plan'].append({'repo_id':repo,'repo_type':'dataset','revision':revision,'license':spec['licenses'][repo],'directory':str(directory),'files':[{'path':x['path'],'size':x['size'],'source_hash':x['source_hash'],'source_hash_type':x['source_hash_type']} for x in files]})
    cooperative()
    selected=VAULT/('.hummingbird-shortlist-'+spec['sha256']+'.json')
    if selected.is_symlink():raise ValueError('Shortlist plan cannot be a symlink')
    selected.write_text(json.dumps(plan,indent=2)+'\n');stage('Indexing verified shortlist cards and manifests into KC')
    cards=hf_library.ingest(selected);indexes=[]
    for repo in plan['plan']:
        for item in repo['files']:
            if not item['path'].endswith('.parquet'):continue
            cooperative();reference='hf-archive:dataset:'+repo['repo_id']+'@'+repo['revision']+'/'+item['path']
            stage('Indexing approved Parquet text '+repo['repo_id']+'/'+item['path'])
            result=hf_text_index.index_parquet(vault.contained(Path(repo['directory']),item['path']),reference,item,priority=100)
            if result['state'] not in {'indexed','unchanged'}:raise RuntimeError('Shortlist indexing stopped: '+result['state'])
            indexes.append({'reference':reference,**result})
    examples=[]
    with closing(hf_text_index.connect()) as conn:
        for indexed in indexes:
            row=conn.execute('SELECT id,row_index,part,substr(text,1,650) FROM documents WHERE reference=? ORDER BY row_index,part LIMIT 1',(indexed['reference'],)).fetchone()
            if row:examples.append({'document_id':hf_text_index.DOCUMENT_ID+row['id'],'source_ref':indexed['reference']+'#row='+str(row['row_index'])+'&part='+str(row['part']),'excerpt':row[3]})
    return {'status':'verified_and_indexed','manifest_sha256':spec['sha256'],'files':receipts,'bytes_verified':sum(x['size'] for x in receipts),'knowledge':cards,'parquet_indexes':indexes,
        'retrieval_examples':examples,'broader_mirror_resumed':False,'notice':'Verified public reference data is searchable locally; indexing does not change model weights or authorize executing dataset code.'}
