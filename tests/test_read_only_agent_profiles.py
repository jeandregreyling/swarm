import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontend'))

from agents.skills_loop import run_skill_loop
from core import read_only_context
from frontend.blueprints import agent_api, agents as agents_api
from utils.local_runtime_policy import (
    MEMORY_WRITE_AGENT_PROFILES,
    READ_ONLY_AGENT_PROFILES,
    agent_capability_allowed,
    normalize_read_only_response,
    persist_read_only_chat_memory,
)


def test_read_only_profiles_deny_execution_capabilities():
    assert READ_ONLY_AGENT_PROFILES == {'gemma', 'qwen', 'llama', 'seven'}
    for agent in READ_ONLY_AGENT_PROFILES:
        for capability in (
            'skill_shell', 'sandpit_write', 'git_propose', 'git_execute',
            'ticket_create', 'memory_read_all', 'coordinate',
        ):
            assert not agent_capability_allowed(agent, capability)
    assert agent_capability_allowed('mistral', 'git_execute')
    assert MEMORY_WRITE_AGENT_PROFILES == {'gemma', 'qwen', 'llama'}
    for agent in MEMORY_WRITE_AGENT_PROFILES:
        assert agent_capability_allowed(agent, 'memory_write')
        assert not agent_capability_allowed(agent, 'git_execute')
    assert not agent_capability_allowed('seven', 'memory_write')


def test_read_only_chat_memory_is_private_and_capability_gated(monkeypatch):
    from utils.db import agents as db_agents

    writes = []
    monkeypatch.setattr(db_agents, 'agent_has_capability', lambda agent, cap: (
        agent == 'qwen' and cap == 'memory_write'
    ))
    monkeypatch.setattr(
        'database.save_agent_memory',
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )
    response = json.dumps({
        'kind': 'analysis',
        'summary': 'Local storage is available.',
        'evidence': [],
        'proposed_changes': [],
        'human_review_required': True,
    })

    assert persist_read_only_chat_memory('qwen', 'Check local storage', response)
    assert writes == [(
        (
            'qwen',
            'Check local storage',
            json.dumps(json.loads(response), ensure_ascii=True, separators=(',', ':')),
        ),
        {
            'tags': 'chat,review_gated',
            'importance': 5,
            'source': 'read_only_chat',
        },
    )]
    assert not persist_read_only_chat_memory('gemma', 'Do not cross-write', response)
    assert len(writes) == 1


def test_read_only_chat_memory_skips_errors_and_denied_grants(monkeypatch):
    from utils.db import agents as db_agents

    writes = []
    monkeypatch.setattr(db_agents, 'agent_has_capability', lambda *_args: False)
    monkeypatch.setattr(
        'database.save_agent_memory',
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    error_response = normalize_read_only_response('llama', '[llama] error: offline')
    assert not persist_read_only_chat_memory('llama', 'check status', error_response)
    assert not persist_read_only_chat_memory(
        'llama',
        'check status',
        json.dumps({
            'kind': 'analysis',
            'summary': 'Not review-gated.',
            'evidence': [],
            'proposed_changes': [],
            'human_review_required': False,
        }),
    )
    assert not writes


@pytest.mark.parametrize(
    ('module_name', 'agent_name'),
    [
        ('agents.gemma.gemma_agent', 'gemma'),
        ('agents.qwen.qwen_agent', 'qwen'),
        ('agents.llama.llama_agent', 'llama'),
    ],
)
def test_trio_chat_routes_successful_responses_to_private_memory(
    monkeypatch, module_name, agent_name
):
    import importlib
    from agents import skill_intent, skills_loop
    from utils import local_runtime_policy

    writes = []
    response = json.dumps({
        'kind': 'analysis',
        'summary': f'{agent_name} status is ready.',
        'evidence': [],
        'proposed_changes': [],
        'human_review_required': True,
    })
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, '_build_context', lambda _message: '')
    monkeypatch.setattr(
        skills_loop,
        'run_skill_loop',
        lambda **_kwargs: (response, 8),
    )
    monkeypatch.setattr(skill_intent, 'message_likely_needs_skills', lambda _message: False)
    monkeypatch.setattr(
        local_runtime_policy,
        'persist_read_only_chat_memory',
        lambda name, prompt, answer: writes.append((name, prompt, answer)) or True,
    )

    answer, tokens = module.chat('Check local readiness.')

    assert answer == response
    assert tokens == 8
    assert writes == [(agent_name, 'Check local readiness.', response)]


def test_read_only_response_suppresses_skill_requests_as_json():
    result = json.loads(normalize_read_only_response(
        'gemma',
        'SKILL fs_write core/spine.py malicious content',
    ))

    assert result['kind'] == 'error'
    assert result['blocked_tool'] == 'fs_write'
    assert result['human_review_required'] is True
    assert 'malicious content' not in json.dumps(result)


def test_read_only_response_enforces_json_schema():
    result = json.loads(normalize_read_only_response(
        'seven',
        json.dumps({
            'kind': 'untrusted_kind',
            'summary': {'answer': 'review this'},
            'evidence': ['malformed'],
            'proposed_changes': [{'path': 'core/x.py', 'change': 'draft'}],
            'extra': 'discarded',
        }),
    ))

    assert result == {
        'kind': 'analysis',
        'summary': '{"answer": "review this"}',
        'evidence': [],
        'proposed_changes': [{'path': 'core/x.py', 'change': 'draft'}],
        'human_review_required': True,
    }


def test_read_only_runtime_error_is_reported_as_error():
    result = json.loads(normalize_read_only_response('qwen', '[qwen] error: model unavailable'))

    assert result['kind'] == 'error'
    assert 'model unavailable' in result['summary']


def test_read_only_empty_response_is_an_explicit_error():
    result = json.loads(normalize_read_only_response('gemma', ''))

    assert result['kind'] == 'error'
    assert result['summary'] == 'The agent returned an empty response.'


def test_read_only_skill_loop_never_executes_model_tool_output():
    called = []

    def model_call(_messages):
        return 'SKILL shell rm -rf /', 17

    answer, tokens = run_skill_loop(
        agent_name='llama',
        call_fn=model_call,
        messages=[{'role': 'user', 'content': 'Inspect the code.'}],
        emit_fn=lambda _message: called.append(_message),
    )
    payload = json.loads(answer)

    assert tokens == 17
    assert payload['kind'] == 'error'
    assert payload['blocked_tool'] == 'shell'
    assert 'executing skill' not in called


def test_seven_read_only_chat_does_not_write_memory_or_learning(monkeypatch):
    from agents.seven import learnings, seven_agent
    from core import witness

    writes = []
    monkeypatch.setattr(seven_agent, '_read_state', lambda: {})
    monkeypatch.setattr(seven_agent, '_load_memory', lambda _message: [])
    monkeypatch.setattr(seven_agent, '_compose', lambda *_args: ('draft answer', 0))
    monkeypatch.setattr(learnings, 'observe', lambda *_args: writes.append('learning'))
    monkeypatch.setattr(witness, 'is_enabled', lambda: False)
    monkeypatch.setattr(
        'database.save_agent_memory',
        lambda *_args, **_kwargs: writes.append('memory'),
    )

    answer, _tokens = seven_agent.chat(
        'Review this',
        conversation_history=[{'role': 'assistant', 'content': 'prior answer'}],
    )

    assert json.loads(answer)['summary'] == 'draft answer'
    assert writes == []


def test_seven_read_only_slash_command_rejects_mutation(monkeypatch):
    from agents.seven import seven_agent

    monkeypatch.setattr(
        seven_agent,
        '_slash_command',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('must not run')),
    )

    answer, _tokens = seven_agent.chat('/curiosity ask update my beliefs')

    payload = json.loads(answer)
    assert payload['kind'] == 'error'
    assert 'read-only' in payload['summary']


@pytest.mark.parametrize('path', [
    '/api/agent/tickets',
    '/api/agent/git/proposals',
    '/api/agent/git/proposals/test-proposal/execute',
    '/api/agent/think',
])
def test_read_only_agent_mutation_routes_reject_before_work(monkeypatch, path):
    app = Flask(__name__)
    app.register_blueprint(agent_api.agent_api_bp)
    monkeypatch.setattr(agent_api, '_validate_agent_request', lambda: ('gemma', None))
    monkeypatch.setattr(
        agent_api,
        'intake_internal',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('must not queue work')),
    )

    response = app.test_client().post(path, json={'title': 'Forbidden task'})

    assert response.status_code == 403
    assert response.get_json()['ok'] is False


def test_capability_api_cannot_regrant_restricted_capability(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(agents_api.agents_bp)
    monkeypatch.setattr(
        agents_api,
        '_resolve_identity_or_response',
        lambda _data: ({'effective_user': 'ghost'}, None),
    )
    monkeypatch.setattr(agents_api, '_reg_roster_bp', lambda: [{'name': 'gemma'}])
    monkeypatch.setattr(
        agents_api,
        'grant_agent_capability',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('must not grant')),
    )

    response = app.test_client().post(
        '/api/agents/capabilities',
        json={'agent': 'gemma', 'capability': 'git_execute', 'enabled': True},
    )

    assert response.status_code == 403
    assert 'read-only profile' in response.get_json()['error']


def test_repository_context_uses_checkout_scoped_source_only(monkeypatch, tmp_path):
    (tmp_path / 'agents').mkdir()
    (tmp_path / 'agents' / 'policy.py').write_text(
        'READ_ONLY_POLICY_MARKER = "history context"\n',
        encoding='utf-8',
    )
    (tmp_path / '.env').write_text(
        'READ_ONLY_POLICY_MARKER=DO_NOT_INDEX\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(read_only_context, 'REPO_ROOT', tmp_path)

    matches, _history_path = read_only_context._repository_matches('READ_ONLY_POLICY_MARKER')

    assert any(match['path'] == 'agents/policy.py' for match in matches)
    assert all('.env' not in match['path'] for match in matches)
    assert all('DO_NOT_INDEX' not in match['excerpt'] for match in matches)


def test_repository_context_redacts_credentials():
    excerpt = read_only_context._sanitize_excerpt(
        '"api_key": "sensitive-value" Authorization: Bearer abc.def.ghi'
    )

    assert 'sensitive-value' not in excerpt
    assert 'abc.def.ghi' not in excerpt
    assert '[REDACTED]' in excerpt


def test_vortex_context_search_reads_only_recent_index_metadata(monkeypatch, tmp_path):
    index_dir = tmp_path / 'indexes'
    index_dir.mkdir()
    day = datetime.now(timezone.utc).date().isoformat()
    (index_dir / f'{day}.jsonl').write_text(
        json.dumps({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source_agent': 'gemma',
            'target_agent': 'llama',
            'action_type': 'agent_handoff',
            'execution_status': 'completed',
            'payload_context_hash': 'f' * 64,
            'terms': ['agent_handoff', 'vortex_test_marker'],
        }) + '\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(read_only_context, 'VORTEX_ROOT', tmp_path)

    events = read_only_context._vortex_events('vortex_test_marker')

    assert len(events) == 1
    assert events[0]['action_type'] == 'agent_handoff'
    assert events[0]['context_hash'] == 'f' * 64


def test_agent_capability_api_hard_denies_profile_mutations(monkeypatch):
    from utils.db import agents

    monkeypatch.setattr(
        agents,
        'get_connection',
        lambda: (_ for _ in ()).throw(AssertionError('database must not be consulted')),
    )

    assert not agents.agent_has_capability('gemma', 'git_execute')
    try:
        agents.grant_agent_capability('qwen', 'sandpit_write')
    except PermissionError:
        pass
    else:
        raise AssertionError('restricted capability grant should be rejected')
