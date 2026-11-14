import json
import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend')]

from core import llm
from core.seven_llm import llama_server
from frontend.blueprints import ollama
from services import auth
from utils.db import registry


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, 'get_current_user', lambda: {'role': 'owner'})
    monkeypatch.setattr(registry, 'get_agent_models', lambda local_only: {'gemma': 'registered-model'})
    monkeypatch.setattr(llm, '_direct_model', lambda model: model)
    app = Flask(__name__)
    app.register_blueprint(ollama.ollama_bp)
    return app.test_client()


def test_agent_load_uses_registry_and_streams_real_stages(client, monkeypatch):
    def ensure(model, *, progress):
        assert model == 'registered-model'
        for stage in ('queued', 'checking_memory', 'loading'):
            progress({'stage': stage, 'model': model})
        progress({'stage': 'ready', 'model': model, 'placement': 'gpu+ram', 'gpu_layers': 12, 'total_layers': 33})
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(llama_server, 'ensure', ensure)
    response = client.post('/api/agents/gemma/load', json={'model': 'untrusted-override'})
    assert response.status_code == 200
    assert response.mimetype == 'application/x-ndjson'
    events = [json.loads(line) for line in response.data.splitlines()]
    assert [e['stage'] for e in events if e['stage'] != 'waiting'] == [
        'requested', 'queued', 'checking_memory', 'loading', 'ready',
    ]
    assert events[-1]['placement'] == 'gpu+ram'


def test_failed_load_is_not_reported_ready(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('RAM reserve would be exceeded')
    monkeypatch.setattr(llama_server, 'ensure', fail)
    events = [json.loads(line) for line in client.post('/api/agents/gemma/load').data.splitlines()]
    assert events[-1]['stage'] == 'error'
    assert 'RAM reserve' in events[-1]['error']
    assert not any(e['stage'] == 'ready' for e in events)


def test_agent_load_requires_owner_and_local_registry(client, monkeypatch):
    assert client.post('/api/agents/disabled/load').status_code == 404
    assert client.post('/api/agents/gemma/load', headers={'Origin': 'https://elsewhere.invalid'}).status_code == 403
    monkeypatch.setattr(llm, '_direct_model', lambda model: '')
    assert client.post('/api/agents/gemma/load').status_code == 409
    monkeypatch.setattr(auth, 'get_current_user', lambda: {'role': 'viewer'})
    assert client.post('/api/agents/gemma/load').status_code == 403


@pytest.mark.parametrize('gpu,total,placement', [(0,33,'ram'), (12,33,'gpu+ram'), (33,33,'gpu')])
def test_placement_comes_from_confirmed_offload_log(tmp_path, gpu, total, placement):
    log = tmp_path / 'server.log'
    log.write_text(f'load_tensors: offloaded {gpu}/{total} layers to GPU\n')
    assert llama_server._placement_from_log(str(log)) == {
        'placement': placement, 'gpu_layers': gpu, 'total_layers': total,
    }
    assert llama_server._placement_from_log(str(tmp_path / 'missing')) == {'placement': 'unknown'}


def test_low_vram_accounts_for_system_ram(monkeypatch):
    entry = SimpleNamespace(ram_gb=10, options={})
    monkeypatch.setattr(llama_server, '_vram_free_gb', lambda: 2.0)
    assert llama_server._host_need_gb(entry) == 9.0
    monkeypatch.setattr(llama_server, '_vram_free_gb', lambda: 0.0)
    assert llama_server._host_need_gb(entry) == 10.0


def test_kernel_placement_deduplicates_drm_clients(monkeypatch, tmp_path):
    paths = []
    for name in ('fd1', 'fd2'):
        path = tmp_path / name
        path.write_text('drm-client-id:\t42\ndrm-resident-vram:\t1048576 KiB\ndrm-resident-gtt:\t2097152 KiB\n')
        paths.append(str(path))
    monkeypatch.setattr(llama_server.glob, 'glob', lambda pattern: paths)
    assert llama_server._placement_from_process(123) == {
        'placement': 'gpu+ram', 'placement_source': 'kernel',
        'vram_gb': 1.0, 'gpu_host_ram_gb': 2.0,
    }


def test_cold_start_reports_low_vram_then_health_confirmed_ready(monkeypatch, tmp_path):
    model_path = tmp_path / 'model.gguf'
    model_path.write_bytes(b'GGUF')
    entry = SimpleNamespace(name='pytest-loading', driver='llamacpp', path=str(model_path),
                            options={'server': str(model_path)}, ctx=4096, ram_gb=10, endpoint=None)
    monkeypatch.setattr(llama_server.registry, 'get', lambda model: entry)
    monkeypatch.setattr(llama_server, '_PROCS', {})
    monkeypatch.setattr(llama_server, '_cross_process_lock', contextlib.nullcontext)
    monkeypatch.setattr(llama_server, '_load_state', lambda: {})
    monkeypatch.setattr(llama_server, '_save_state', lambda state: None)
    monkeypatch.setattr(llama_server, '_foreign_servers', lambda: [])
    monkeypatch.setattr(llama_server, '_port_for', lambda model: 18099)
    monkeypatch.setattr(llama_server, '_reap_idle', lambda *a, **k: None)
    monkeypatch.setattr(llama_server, '_admit', lambda *a: 9.0)
    monkeypatch.setattr(llama_server, '_vram_free_gb', lambda: 2.0)
    monkeypatch.setattr(llama_server, '_launcher_prefix', lambda *a: [])
    monkeypatch.setattr(llama_server, '_set_oom_score', lambda pid: None)
    monkeypatch.setattr(llama_server, '_placement_from_log', lambda path: {'placement': 'unknown'})
    monkeypatch.setattr(llama_server, '_placement_from_process', lambda pid: {
        'placement': 'gpu+ram', 'placement_source': 'kernel', 'vram_gb': 1, 'gpu_host_ram_gb': 8,
    })
    proc = SimpleNamespace(pid=42, poll=lambda: None)
    monkeypatch.setattr(llama_server.subprocess, 'Popen', lambda *a, **k: proc)
    events = []

    def healthy(endpoint):
        assert not any(event['stage'] == 'ready' for event in events)
        return True

    monkeypatch.setattr(llama_server, '_server_alive', healthy)
    try:
        handle = llama_server.ensure('pytest-loading', progress=events.append)
        assert handle.pid == 42
        assert [e['stage'] for e in events] == ['queued', 'checking_memory', 'loading', 'ready']
        assert events[2]['placement_estimate'] == 'gpu+ram'
        assert events[2]['host_ram_gb'] == 9.0
        assert events[-1]['placement_source'] == 'kernel'
    finally:
        Path('/tmp/seven-llama-server-pytest-loading.log').unlink(missing_ok=True)


def test_both_selectors_warm_models_and_home_selection_is_explicit():
    home = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    full = (ROOT / 'frontend/static/js/views/chat.js').read_text()
    assert "localStorage.setItem(HC_MANUAL_KEY, '1')" in home
    assert "window.warmChatAgent(btn.dataset.agent)" in home
    assert "if (input.checked) window.warmChatAgent(input.value)" in full
    assert 'data-agent-load-status' in home and 'data-agent-load-status' in full


def test_chat_stream_decodes_sse_as_utf8(monkeypatch):
    import io
    import requests
    from core.seven_llm import llama_server

    body = 'data: {"choices":[{"delta":{"content":"model\u2019s \u2013 \u201cready\u201d"}}]}\n\ndata: [DONE]\n\n'
    resp = requests.Response()
    resp.status_code = 200
    resp.headers["Content-Type"] = "text/event-stream"
    resp.raw = io.BytesIO(body.encode("utf-8"))
    resp.encoding = "ISO-8859-1"
    monkeypatch.setattr(llama_server.requests, "post", lambda *a, **k: resp)
    handle = llama_server.ServerHandle.__new__(llama_server.ServerHandle)
    object.__setattr__(handle, "endpoint", "http://127.0.0.1:1") if hasattr(handle, "__dataclass_fields__") else setattr(handle, "endpoint", "http://127.0.0.1:1")

    text, _ = llama_server._chat_stream(handle, {}, timeout=5)

    assert text == "model\u2019s \u2013 \u201cready\u201d"
