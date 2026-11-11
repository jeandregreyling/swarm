from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from dataclasses import replace

import pytest

from core.apex_routing import LocalRoute, active_model, current_route, select_local_model, use_model
from core.seven_llm.registry import ModelEntry


def catalogue():
    return [ModelEntry('gemma-direct:3','llamacpp',path='/gemma',ctx=16384,ram_gb=3),
            ModelEntry('apex-direct:7b','llamacpp',role='coder',path='/coder',ctx=16384,ram_gb=6),
            ModelEntry('qwen2.5:14b-instruct','llamacpp',path='/qwen',ctx=16384,ram_gb=10,
                       endpoint='http://127.0.0.1:8080')]


def choose(message, entries=None, **kwargs):
    return select_local_model(message, entries or catalogue(),
        {'http://127.0.0.1:8080':{'qwen2.5:14b-instruct'}}, exists=lambda _: True, **kwargs)


@pytest.mark.parametrize('message,model', [
    ('hello', 'gemma-direct:3'),
    ('debug this traceback', 'apex-direct:7b'),
    ('verify the memory files', 'qwen2.5:14b-instruct'),
    ('analyse the architecture', 'qwen2.5:14b-instruct'),
    ('Read frontend/chat.py', 'apex-direct:7b'),
    ('test tools and memory', 'qwen2.5:14b-instruct'),
    ('why is APEX doing nothing?', 'qwen2.5:14b-instruct'),
])
def test_task_selects_local_backend_while_apex_identity_is_stable(message, model):
    route = choose(message)
    assert route.model == model
    with use_model(route):
        from core.apex_context import context_tokens
        assert active_model() == model
        assert context_tokens() == route.context_tokens
    assert current_route() is None


def test_cloud_embeddings_missing_models_and_wrong_endpoint_alias_are_excluded():
    entries = [ModelEntry('cloud','openai',path='/cloud',ctx=32000),
        ModelEntry('embed','llamacpp',role='embed',path='/embed',ctx=32000),
        ModelEntry('missing','llamacpp',path='/missing',ctx=32000),
        ModelEntry('rollback','llamacpp',path='/rollback',ctx=32000,endpoint='http://127.0.0.1:8080',
                   options={'api_model':'gpt-oss:20B'}),
        ModelEntry('remote','llamacpp',path='/remote',ctx=32000,endpoint='https://models.example.com')]
    with pytest.raises(RuntimeError, match='no online agent was invoked'):
        select_local_model('debug code', entries, {'http://127.0.0.1:8080':{'qwen'}},
                           exists=lambda path:path!='/missing')


def test_ram_pressure_chooses_smaller_local_model_without_cloud_fallback():
    assert choose('analyse this design',available_gb=8).model == 'apex-direct:7b'
    with pytest.raises(RuntimeError):
        choose('hello',available_gb=2)


def test_unavailable_endpoint_can_use_a_managed_local_model():
    route=select_local_model('verify memory',catalogue(),{},exists=lambda _:True)
    assert route.model in {'gemma-direct:3','apex-direct:7b'}


def test_parallel_turns_do_not_share_models_or_context_windows():
    barrier=Barrier(2)
    routes=[LocalRoute('a','coder',8192,'test'),LocalRoute('b','voice',16384,'test')]
    def run(route):
        with use_model(route):
            barrier.wait()
            from core.apex_context import context_tokens
            return active_model(),context_tokens()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run,routes)) == [('a',8192),('b',16384)]
    assert current_route() is None


def test_tool_loop_uses_selected_model_and_restores_default_on_error():
    from core.apex_tools import run_apex_tools
    calls=[]
    def model(name,messages):
        calls.append(name)
        return '{"tool_calls":[],"answer":"hello"}',1
    with use_model(LocalRoute('chosen','voice',8192,'test')):
        assert run_apex_tools(model,[{'role':'user','content':'hello'}],lambda:True,lambda _:None)[0]=='hello'
    assert calls==['chosen'] and current_route() is None


def test_assigned_repair_backend_cannot_select_an_online_or_arbitrary_model():
    from core.apex_routing import assigned_local_model
    for name in ['gemini','gpt-4o','http://example.com','qwen2.5:14b-instruct']:
        with pytest.raises(PermissionError):assigned_local_model(name)


def test_focused_local_repair_can_use_8k_cpu24b_with_real_headroom(tmp_path,monkeypatch):
    from core import apex_routing as routing
    from core.seven_llm import llama_server
    weights=tmp_path/'model.gguf';weights.write_bytes(b'fixture')
    entry=ModelEntry('fred-cpu:24b','llamacpp',path=str(weights),ctx=8192,ram_gb=16,options={'ngl':0})
    monkeypatch.setattr(routing.registry,'get',lambda _:entry)
    monkeypatch.setattr(llama_server,'resource_snapshot',lambda:{'residents':[]})
    route=routing.assigned_local_model('fred-cpu:24b',available_gb=54)
    assert route.model=='fred-cpu:24b' and route.context_tokens==8192
    with pytest.raises(RuntimeError,match='headroom'):routing.assigned_local_model('fred-cpu:24b',available_gb=20)
