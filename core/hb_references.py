"""Local-first reference discovery and explicitly selected pinned text ingestion."""
from contextlib import closing
from pathlib import PurePosixPath
import hashlib
import re
from urllib.parse import quote, urlsplit


def lookup(query, allow_online=False):
    from core.apex_knowledge import search
    if type(allow_online) is not bool:
        raise ValueError('allow_online must be boolean')
    local=search(query)
    if local.get('items') or not allow_online:
        return {'local':local,'online_queried':False,
                'next_action':'Use local source tools for repository code; online metadata is optional when local references are insufficient.'}
    from huggingface_hub import HfApi
    api=HfApi(token=False)
    items=[]
    for kind, method in [('dataset',api.list_datasets),('model',api.list_models)]:
        for row in method(search=query,limit=3):
            items.append({'kind':kind,'repo':row.id,'revision':getattr(row,'sha',None)})
    return {'local':local,'online_queried':True,'repositories':items,
            'notice':'Discovery metadata only. Select a full revision and text path for reference_import; remote code is not executed.'}


def ingest(kind, repo, revision, path):
    from core.hf_mirror import valid_id
    from core import agent_identity, hb_tasks
    from utils.db._connection import get_connection
    if kind not in {'dataset','model','space'} or not valid_id(repo) or not re.fullmatch(r'[a-fA-F0-9]{40}',str(revision)):
        raise ValueError('Select a public repository kind/name and full 40-character pinned revision')
    if (not isinstance(path,str) or not path or '\\' in path or PurePosixPath(path).is_absolute()
        or any(part in {'.','..',''} for part in path.split('/'))
        or PurePosixPath(path).suffix.lower() not in {'.md','.txt','.rst','.json'}):
        raise ValueError('Only explicit repository-relative text-reference paths are supported')
    actor=agent_identity.CURRENT.get()
    if not actor or actor['principal']!='apex' or not (actor.get('peer_request_id') or actor.get('task_id')):
        raise PermissionError('Reference ingestion requires an assigned APEX task')
    with closing(get_connection()) as conn:
        task=hb_tasks.for_request(conn,actor['peer_request_id']) if actor.get('peer_request_id') else hb_tasks.get(conn,actor['task_id'])
    if not task or not task['project_id']:
        raise PermissionError('Reference ingestion requires a Studio-linked task')
    reference=f'hf-reference:{kind}:{repo}@{revision}:{path}'
    from lib.knowledge import store
    store.ensure_schema()
    with closing(get_connection()) as conn:
        cached=conn.execute('SELECT source_id,raw_text FROM knowledge_sources WHERE source_ref=? AND status=\'active\' ORDER BY source_id LIMIT 1',(reference,)).fetchone()
    if cached:
        raw=cached[1].encode('utf-8')
        result={'source_id':cached[0],'document_id':(1<<40)+cached[0],'source_ref':reference,
                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'status':'local_reference_reused'}
        with closing(get_connection()) as conn,conn:
            hb_tasks.event(conn,task,actor['principal'],'reference_reused',result,request_id=actor.get('peer_request_id'))
        return result
    prefix={'model':'','dataset':'datasets/','space':'spaces/'}[kind]
    url='https://huggingface.co/'+prefix+quote(repo,safe='/')+'/resolve/'+revision+'/'+quote(path,safe='/')
    import requests
    data=b''
    for _ in range(4):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.hostname not in {'huggingface.co'}:
            raise ValueError('Text-reference redirect left the public Hugging Face host')
        with requests.get(url,timeout=(5,25),stream=True,allow_redirects=False) as response:
            if response.is_redirect:
                from urllib.parse import urljoin
                url=urljoin(url,response.headers['Location'])
                continue
            response.raise_for_status()
            for chunk in response.iter_content(16384):
                data+=chunk
                if len(data)>256000:
                    raise ValueError('Text reference exceeds 256000 bytes')
            break
    else:
        raise ValueError('Too many text-reference redirects')
    if not data or b'\0' in data:
        raise ValueError('Reference is empty or binary')
    text=data.decode('utf-8')
    digest=hashlib.sha256(data).hexdigest()
    reference=f'hf-reference:{kind}:{repo}@{revision}:{path}'
    from lib.knowledge import store
    from lib.knowledge.ingest import chunk_text
    store.ensure_schema()
    with closing(get_connection()) as conn:
        previous=conn.execute('SELECT source_id,raw_text FROM knowledge_sources WHERE source_ref=? ORDER BY source_id LIMIT 1',(reference,)).fetchone()
    if previous:
        if previous[1]!=text:
            raise ValueError('Pinned reference content changed; existing KC document retained')
        source_id=previous[0]
    else:
        source_id=store.add_source(repo+' — '+path,'text',text,source_ref=reference,
            domain_tags=['huggingface','pinned-reference','reference-only'],added_by='apex',category='general',subcategory='huggingface')
        store.save_chunks(source_id,[(part,None) for part in chunk_text(text)])
    result={'source_id':source_id,'document_id':(1<<40)+source_id,'source_ref':reference,
            'sha256':digest,'bytes':len(data),'status':'indexed',
            'notice':'Text indexed as untrusted reference, not installed as executable tools. Broad acquisition remains unchanged.'}
    with closing(get_connection()) as conn,conn:
        hb_tasks.event(conn,task,actor['principal'],'reference_indexed',result,request_id=actor.get('peer_request_id'))
    return result
