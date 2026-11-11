"""Conservative, explainable acquisition policy for local LLM and agent work."""
from pathlib import PurePosixPath
import json
import re

POLICY_VERSION='hb-local-agents-v1'
_RELEVANT={
 'model':('llm','language-model','text-generation','conversational','chat','instruct','coder','coding','code','gguf','llama','qwen','mistral','gemma','deepseek','phi','function-calling','tool-use','agent','agentic'),
 'dataset':('llm','language-model','instruction','chat','conversation','ultrachat','openorca','coder','coding','code','codeparrot','programming','agent','agentic','function-calling','tool-use','tool-calling','swe','benchmark','evaluation','human-eval','mbpp'),
 'space':('llm','language-model','agent','agentic','coding','code','inference','ollama','vllm','tool-use','function-calling'),
}
_IRRELEVANT=('image-to-3d','text-to-3d','3d-print','3d-printer','game-emulation','game-emulator','gaming','image-to-video','text-to-video','text-to-image','music-generation','speech-recognition')
_MODEL_TEXT_NAMES={'readme','license','license.md','notice','config.json','generation_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','added_tokens.json','chat_template.jinja','vocab.json','merges.txt','tokenizer.model'}
_TEXT_EXTENSIONS={'.md','.txt','.json','.jsonl','.parquet','.csv','.yaml','.yml','.py','.js','.ts','.toml','.sh'}


def explain(kind,repo,metadata,extra=()):
    """Return an owner-reviewable inclusion decision and the matching evidence."""
    text=json.dumps(metadata or {},ensure_ascii=True).lower().replace('_','-')
    identity=(repo or '').lower()
    reasons=[]
    explicit={str(value).lower() for value in extra}
    if identity in explicit:return {'include':True,'reason':'explicit owner-selected repository','matches':[identity],'explicit':True}
    if any(term in text for term in _IRRELEVANT):
        domain=[term for term in _IRRELEVANT if term in text]
    else:domain=[]
    matches=[term for term in _RELEVANT.get(kind,()) if re.search(r'(?<![a-z0-9])'+re.escape(term)+r'(?![a-z0-9])',text+' '+identity)]
    if domain and not any(term in matches for term in ('agent','coding','code','coder','llm','tool-use','function-calling')):
        return {'include':False,'reason':'outside the selected local-agent learning scope','matches':domain}
    if matches:
        return {'include':True,'reason':'matches the local LLM, coding-agent or tool-use scope','matches':matches[:12]}
    return {'include':False,'reason':'no local-agent learning signal in public catalogue metadata','matches':[]}


def file_selected(kind,repo,path,metadata,extra=()):
    """Select local references and text; weight/data files need explicit owner intent."""
    decision=explain(kind,repo,metadata,extra)
    if not decision['include']:return False,decision['reason']
    if decision.get('explicit'):return True,decision['reason']
    name=PurePosixPath(path).name.lower();suffix=PurePosixPath(path).suffix.lower()
    if kind=='model' and name not in _MODEL_TEXT_NAMES and suffix not in {'.jinja','.tiktoken'}:
        return False,'model weights and non-text assets require an explicit repository download request'
    if kind=='dataset' and suffix not in _TEXT_EXTENSIONS and name not in _MODEL_TEXT_NAMES:
        return False,'non-text dataset asset is outside the default searchable learning set'
    if kind=='space' and suffix not in _TEXT_EXTENSIONS:
        return False,'non-text Space asset is outside the reference-only learning set'
    return True,decision['reason']
