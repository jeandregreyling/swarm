"""Resumable public-Hub inventory and verified current-revision file mirroring.

No repository code is executed. Cataloguing, downloading and KC indexing are
separate states. The target includes public models, datasets and Spaces.
"""
from contextlib import closing
from pathlib import Path
import json
import os
import re
import shutil
import sqlite3
import time
from urllib.parse import quote,urlsplit

ROOT=Path(os.environ.get('HUMMINGBIRD_HF_MIRROR_ROOT','/mnt/archive/hf_mirror'))
RESERVE_BYTES=100*1024**3
CURATED_BUDGET_BYTES=150_000_000_000
KINDS={'model':'models','dataset':'datasets','space':'spaces'}
_UNIQUE_BUDGET_CACHE=None


def connect(root=ROOT):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    path=root/'catalogue.sqlite'
    if root.is_symlink() or path.is_symlink():raise ValueError('Mirror catalogue cannot be a symlink')
    conn=sqlite3.connect(path,timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''CREATE TABLE IF NOT EXISTS repos(kind TEXT,id TEXT,revision TEXT,state TEXT DEFAULT 'pending',error TEXT,metadata_json TEXT DEFAULT '{}',attempts INTEGER DEFAULT 0,next_attempt REAL DEFAULT 0,
        PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS files(kind TEXT,repo TEXT,revision TEXT,path TEXT,size INTEGER,source_hash TEXT,
        hash_type TEXT,state TEXT DEFAULT 'pending',local_path TEXT,local_sha256 TEXT,attempts INTEGER DEFAULT 0,error TEXT,next_attempt REAL DEFAULT 0,
        PRIMARY KEY(kind,repo,revision,path));
        CREATE TABLE IF NOT EXISTS pages(kind TEXT PRIMARY KEY,next_url TEXT,complete INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE INDEX IF NOT EXISTS idx_hf_files_state_size ON files(state,size);
    ''')
    return conn


def setting(conn,key,value=None):
    if value is not None:
        conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)));conn.commit()
    row=conn.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else None


def downloads_paused(conn=None):
    if conn is not None:return bool(setting(conn,'paused') or setting(conn,'downloads_paused'))
    with closing(connect()) as owned:return downloads_paused(owned)


def _url(url,kind):
    parsed=urlsplit(url)
    if (parsed.scheme!='https' or parsed.hostname!='huggingface.co' or parsed.username or parsed.password
            or parsed.path!='/api/'+KINDS[kind]):
        raise ValueError('Inventory pagination left the public Hub API')
    return url


def valid_id(repo):
    return bool(isinstance(repo,str) and re.fullmatch(r'[\w.-]+(?:/[\w.-]+)?',repo)
                and all(part not in {'.','..'} for part in repo.split('/')))


def inventory_page(conn,kind,session):
    page=conn.execute('SELECT next_url,complete FROM pages WHERE kind=?',(kind,)).fetchone()
    if page and page['complete']:return 0
    url=_url(page['next_url'] if page else 'https://huggingface.co/api/'+KINDS[kind]+'?limit=100',kind)
    response=session.get(url,timeout=30)
    response.raise_for_status()
    data=response.json()
    if not isinstance(data,list):raise ValueError('Hub inventory did not return a repository list')
    next_url=(response.links.get('next') or {}).get('url')
    if next_url:_url(next_url,kind)
    with conn:
        for entry in data:
            repo=entry.get('id')
            if not valid_id(repo) or entry.get('private'):continue
            conn.execute('INSERT OR IGNORE INTO repos(kind,id) VALUES (?,?)',(kind,repo))
            metadata={key:entry.get(key) for key in ('pipeline_tag','library_name','tags','downloads','likes','lastModified') if key in entry}
            conn.execute('UPDATE repos SET metadata_json=? WHERE kind=? AND id=?',(json.dumps(metadata),kind,repo))
        conn.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?)',(kind,next_url,int(next_url is None)))
    return len(data)


def manifest(conn,kind,repo,api):
    if kind not in KINDS or not valid_id(repo):raise ValueError('Invalid public repository')
    info=api.repo_info(repo,repo_type=kind,files_metadata=True,token=False)
    if getattr(info,'private',False) or getattr(info,'gated',False):
        with conn:conn.execute("UPDATE repos SET state='access_blocked',error='Public listing has restricted file access' WHERE kind=? AND id=?",(kind,repo))
        return
    revision=info.sha
    if not isinstance(revision,str) or not re.fullmatch(r'[0-9a-f]{40,64}',revision):
        raise ValueError('Repository has no immutable revision hash')
    import hf_vault_heist as vault
    rows=[]
    for item in info.siblings:
        # Validate paths before they reach the Hub download helper.
        vault.contained(Path('/safe-root'),item.rfilename)
        lfs=getattr(item,'lfs',None)
        digest=(getattr(lfs,'sha256',None) if lfs else getattr(item,'blob_id',None))
        kind_hash='sha256' if lfs else 'git-sha1'
        size=getattr(item,'size',None)
        if type(size) is not int or size<0 or not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}' if lfs else r'[0-9a-f]{40}',digest):
            raise ValueError('File size or integrity metadata is unavailable: '+item.rfilename)
        rows.append((kind,repo,revision,item.rfilename,size,digest,kind_hash))
    with conn:
        conn.executemany('INSERT OR IGNORE INTO files(kind,repo,revision,path,size,source_hash,hash_type) VALUES (?,?,?,?,?,?,?)',rows)
        conn.execute("UPDATE repos SET revision=?,state=?,error=NULL WHERE kind=? AND id=?",(revision,'manifested' if rows else 'verified',kind,repo))


def transfer_one(conn,row,download,root=ROOT,reserve=RESERVE_BYTES):
    global _UNIQUE_BUDGET_CACHE
    import hf_vault_heist as vault
    root=Path(root).resolve()
    cached=None
    # Reuse verified large blobs across repositories instead of duplicating weights.
    if row['hash_type']=='sha256':
        old=conn.execute("SELECT local_path FROM files WHERE source_hash=? AND hash_type='sha256' AND state='verified' AND size=? LIMIT 1",(row['source_hash'],row['size'])).fetchone()
        if old and old[0] and Path(old[0]).is_file():cached=Path(old[0]).resolve()
    cache=root/'hub-cache'
    if cache.is_symlink():raise ValueError('Mirror cache cannot be a symlink')
    cache.mkdir(exist_ok=True)
    if cached is None:
        policy=acquisition_policy(conn)
        if policy['mode']=='curated':
            if _UNIQUE_BUDGET_CACHE is None:
                _UNIQUE_BUDGET_CACHE=conn.execute("SELECT COALESCE(SUM(bytes),0) FROM (SELECT MAX(size) bytes FROM files WHERE state='verified' GROUP BY local_sha256)").fetchone()[0]
            if _UNIQUE_BUDGET_CACHE+row['size']>CURATED_BUDGET_BYTES:
                with conn:conn.execute("UPDATE files SET state='budget_blocked',error='Curated acquisition reached the 150 GB logical unique-content budget' WHERE kind=? AND repo=? AND revision=? AND path=?",
                    (row['kind'],row['repo'],row['revision'],row['path']))
                setting(conn,'budget_blocked',{'used_unique_bytes':_UNIQUE_BUDGET_CACHE,'budget_bytes':CURATED_BUDGET_BYTES,
                    'next_file_bytes':row['size'],'repository':row['repo'],'path':row['path']})
                return False
        free=shutil.disk_usage(root).free
        if row['size']+reserve>free:
            setting(conn,'capacity',{'state':'capacity_blocked','free_bytes':free,'reserve_bytes':reserve,
                'next_file_bytes':row['size'],'repository':row['repo'],'path':row['path']})
            return False
        setting(conn,'active',{'repo':row['repo'],'path':row['path'],'expected_bytes':row['size'],'started_at':time.time()})
        cached=Path(download(repo_id=row['repo'],filename=row['path'],repo_type=row['kind'],
            revision=row['revision'],cache_dir=str(cache),token=False)).resolve()
    if not cached.is_relative_to(root) or cached.is_symlink():raise ValueError('Downloaded path escaped mirror storage')
    verified=vault.verify_file(cached.parent,{'path':cached.name,'size':row['size'],
        'source_hash':row['source_hash'],'source_hash_type':row['hash_type']})
    duplicate=conn.execute("SELECT 1 FROM files WHERE state='verified' AND local_sha256=? LIMIT 1",(verified['local_sha256'],)).fetchone()
    with conn:
        conn.execute("UPDATE files SET state='verified',local_path=?,local_sha256=? WHERE kind=? AND repo=? AND revision=? AND path=?",
            (str(cached),verified['local_sha256'],row['kind'],row['repo'],row['revision'],row['path']))
    if acquisition_policy(conn)['mode']=='curated' and not duplicate:
        if _UNIQUE_BUDGET_CACHE is None:_UNIQUE_BUDGET_CACHE=0
        _UNIQUE_BUDGET_CACHE+=row['size']
    with conn:
        conn.execute("DELETE FROM settings WHERE key IN ('active','capacity')")
        if not conn.execute("SELECT 1 FROM files WHERE kind=? AND repo=? AND revision=? AND state!='verified' LIMIT 1",
                (row['kind'],row['repo'],row['revision'])).fetchone():
            conn.execute("UPDATE repos SET state='verified' WHERE kind=? AND id=? AND revision=?",
                (row['kind'],row['repo'],row['revision']))
    return True


def status(root=ROOT,*,include_totals=True):
    root=Path(root);path=root/'catalogue.sqlite'
    if not path.is_file():return {'state':'not_started','scope':'all public models, datasets and Spaces; files at pinned observed revisions'}
    if path.is_symlink():raise ValueError('Mirror catalogue cannot be a symlink')
    with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as c:
        if not include_totals:
            settings={k:json.loads(v) for k,v in c.execute("SELECT key,value FROM settings WHERE key IN ('paused','downloads_paused','active','capacity','error','acquisition_policy','budget_blocked')")}
            policy=settings.get('acquisition_policy',{'mode':'full','version':'legacy-full-v0','explicit_repositories':[]})
            paused=bool(settings.get('downloads_paused') or settings.get('paused'))
            return {'state':'paused' if paused else 'in_progress','downloads_paused':paused,'observed_at':time.time(),
                'scope':'broad Hub mirror control state','acquisition_policy':policy,'active_transfer':settings.get('active'),
                'capacity':settings.get('capacity'),'last_error':settings.get('error'),'totals_included':False,
                'notice':'Control state only; detailed catalogue totals are not scanned for a chat status request.'}
        repos=dict(c.execute('SELECT state,count(*) FROM repos GROUP BY state'))
        file_states=dict(c.execute('SELECT state,count(*) FROM files GROUP BY state'))
        total,verified,known,verified_bytes=c.execute("SELECT count(*),sum(state='verified'),sum(size),sum(CASE WHEN state='verified' THEN size ELSE 0 END) FROM files").fetchone()
        settings={k:json.loads(v) for k,v in c.execute('SELECT key,value FROM settings')}
        pages=list(c.execute('SELECT kind,complete FROM pages'))
        unique_bytes=c.execute("SELECT COALESCE(SUM(bytes),0) FROM (SELECT MAX(size) bytes FROM files WHERE state='verified' GROUP BY local_sha256)").fetchone()[0]
    complete=len(pages)==len(KINDS) and all(done for _,done in pages)
    mirror_complete=complete and bool(repos) and set(repos)<= {'verified'} and (verified or 0)==total
    state=('verified' if mirror_complete else 'paused' if settings.get('paused') or settings.get('downloads_paused') else
           'budget_blocked' if settings.get('budget_blocked') else
           'capacity_blocked' if settings.get('capacity') else 'in_progress')
    policy=settings.get('acquisition_policy',{'mode':'full','version':'legacy-full-v0','explicit_repositories':[]})
    return {'state':state,'observed_at':time.time(),
        'scope':'curated local LLM, coding-agent and tool-use references' if policy['mode']=='curated' else 'all public models, datasets and Spaces; files at pinned observed revisions',
        'repository_states':repos,'catalogue_enumeration_complete':complete,
        'acquisition_policy':policy,
        'downloads_paused':bool(settings.get('downloads_paused') or settings.get('paused')),
        'file_states':file_states,'verified_unique_content_bytes':unique_bytes,
        'curated_budget_bytes':CURATED_BUDGET_BYTES,
        'files_known':total,'files_verified':verified or 0,'known_logical_bytes':known or 0,
        'verified_logical_bytes':verified_bytes or 0,'active_transfer':settings.get('active'),
        'capacity':settings.get('capacity'),'last_error':settings.get('error'),
        'notice':'Known bytes cover manifests discovered so far and include duplicate references. Downloading is separate from KC text indexing and model training.'}


def pause(value):
    with closing(connect()) as conn:
        with conn:conn.execute("DELETE FROM settings WHERE key='paused'")
        setting(conn,'downloads_paused',bool(value))
        if value:setting(conn,'pause_requested_at',time.time())
    return {'pause_requested':bool(value),'takes_effect':'between files; an active transfer may finish, catalogue discovery continues'}


def acquisition_policy(conn=None):
    if conn is not None:
        return setting(conn,'acquisition_policy') or {'mode':'full','version':'legacy-full-v0','explicit_repositories':[]}
    with closing(connect()) as owned:return acquisition_policy(owned)


def set_acquisition_policy(mode,explicit_repositories=()):
    if mode not in {'curated','full'}:raise ValueError('Acquisition mode must be curated or full')
    values=[]
    for repo in explicit_repositories:
        if not valid_id(repo):raise ValueError('Selected repository must be a valid public Hub ID')
        values.append(repo)
    policy={'mode':mode,'version':'hb-local-agents-v1' if mode=='curated' else 'owner-full-v1',
        'explicit_repositories':sorted(set(values)),'updated_at':time.time()}
    with closing(connect()) as conn:
        setting(conn,'acquisition_policy',policy)
        if mode=='curated':
            with conn:
                conn.execute("DELETE FROM settings WHERE key='paused'")
                conn.execute("UPDATE files SET state='pending',error=NULL,next_attempt=0 WHERE state IN ('filtered','budget_blocked')")
            setting(conn,'downloads_paused',True)
    if mode=='curated':
        with closing(connect()) as conn:
            with conn:conn.execute("DELETE FROM settings WHERE key='budget_blocked'")
    return {'acquisition_policy':policy,'pause_requested':mode=='curated',
        'takes_effect':'after the current file transfer; catalogue discovery continues and verified files are retained'}


def file_allowed(row,root=ROOT,conn=None,metadata_cache=None):
    policy=acquisition_policy(conn)
    if policy['mode']!='curated':return True,'owner-selected full public mirroring'
    from core.hf_scope import file_selected
    path=Path(root)/'catalogue.sqlite'
    key=(row['kind'],row['repo'])
    if metadata_cache is not None and key in metadata_cache:metadata=metadata_cache[key]
    else:
        if conn is not None and Path(root).resolve()==ROOT.resolve():
            found=conn.execute('SELECT metadata_json FROM repos WHERE kind=? AND id=?',key).fetchone()
        else:
            with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as owned:
                found=owned.execute('SELECT metadata_json FROM repos WHERE kind=? AND id=?',key).fetchone()
        metadata=json.loads(found[0]) if found else {}
        if metadata_cache is not None:metadata_cache[key]=metadata
    return file_selected(row['kind'],row['repo'],row['path'],metadata,policy.get('explicit_repositories',()))


def dataset_repo_allowed(repo,root=ROOT,conn=None):
    policy=acquisition_policy(conn)
    if policy['mode']!='curated':return True
    from core.hf_scope import explain
    path=Path(root)/'catalogue.sqlite'
    if conn is not None and Path(root).resolve()==ROOT.resolve():
        found=conn.execute('SELECT metadata_json FROM repos WHERE kind=? AND id=?',('dataset',repo)).fetchone()
    else:
        with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as owned:
            found=owned.execute('SELECT metadata_json FROM repos WHERE kind=? AND id=?',('dataset',repo)).fetchone()
    metadata=json.loads(found[0]) if found else {}
    return explain('dataset',repo,metadata,policy.get('explicit_repositories',()))['include']


CATALOGUE_ID=1<<50


def catalogue_search(query,root=None):
    root=Path(root or ROOT);path=root/'catalogue.sqlite'
    if not path.is_file():return []
    with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as conn:
        rows=conn.execute('SELECT rowid,kind,id,revision,state FROM repos WHERE instr(lower(id),lower(?))>0 OR instr(lower(metadata_json),lower(?))>0 ORDER BY id LIMIT 5',(query,query)).fetchall()
    return [{'document_id':CATALOGUE_ID+r[0],'title':r[2],
             'excerpt':json.dumps({'repository_type':r[1],'revision':r[3],'mirror_state':r[4]}),
             'store':'hf_mirror_catalogue','source_ref':'https://huggingface.co/'+('' if r[1]=='model' else KINDS[r[1]]+'/')+r[2]} for r in rows]


def catalogue_read(document_id,offset=0,root=None):
    root=Path(root or ROOT);path=root/'catalogue.sqlite'
    if not path.is_file():return {'status':'not_found','document_id':document_id}
    with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as conn:
        row=conn.execute('SELECT kind,id,revision,state,error,metadata_json FROM repos WHERE rowid=?',(document_id-CATALOGUE_ID,)).fetchone()
        if not row:return {'status':'not_found','document_id':document_id}
        counts=conn.execute("SELECT count(*),sum(size),sum(state='verified') FROM files WHERE kind=? AND repo=? AND revision=?",row[:3]).fetchone()
    text=json.dumps({'repository_type':row[0],'repository':row[1],'revision':row[2],'state':row[3],
        'error':row[4],'metadata':json.loads(row[5] or '{}'),'known_files':counts[0],'known_bytes':counts[1],'verified_files':counts[2],
        'notice':'Public catalogue metadata; this is not proof that all repository text is indexed or that a model has learned its contents.'},indent=2)
    if offset>len(text):raise ValueError('Catalogue read offset exceeds document length')
    return {'status':'found','document_id':document_id,'title':row[1],'content':text[offset:offset+1500],
            'next_offset':offset+1500 if offset+1500<len(text) else None,'source':'hf_mirror_catalogue'}


def index_card(row,local_path):
    if row['size']>1_000_000 or not Path(row['path']).name.lower().startswith(('readme','license','notice')):
        return None
    from lib.knowledge import store
    from lib.knowledge.ingest import chunk_text
    store.ensure_schema()
    reference='hf-mirror:'+row['kind']+':'+row['repo']+'@'+row['revision']+'/'+row['path']
    with closing(store._conn()) as conn:
        old=conn.execute('SELECT source_id FROM knowledge_sources WHERE source_ref=?',(reference,)).fetchone()
    if old:return old[0]
    text=Path(local_path).read_text(encoding='utf-8',errors='replace')
    source=store.add_source(row['repo']+' — '+row['path'],'text',text,source_ref=reference,
        domain_tags=['huggingface','verified-public-mirror','reference-only'],added_by='apex',category='general',subcategory='huggingface')
    store.save_chunks(source,[(chunk,None) for chunk in chunk_text(text)])
    return source
