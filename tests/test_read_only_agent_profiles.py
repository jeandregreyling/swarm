import json
import sqlite3
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
    agent_skill_allowed,
    normalize_read_only_response,
    persist_read_only_chat_memory,
)


def test_read_only_profiles_deny_execution_capabilities():
    from utils.db.agents import AGENT_CAPABILITY_REGISTRY

    assert READ_ONLY_AGENT_PROFILES == {'seven'}
    for agent in READ_ONLY_AGENT_PROFILES:
        for capability in (
            'skill_shell', 'sandpit_write', 'git_propose', 'git_execute',
            'ticket_create', 'memory_read_all', 'coordinate',
        ):
            assert not agent_capability_allowed(agent, capability)
    assert agent_capability_allowed('mistral', 'git_execute')
    assert MEMORY_WRITE_AGENT_PROFILES == {'fred', 'gemma', 'qwen', 'llama'}
    for agent in MEMORY_WRITE_AGENT_PROFILES:
        assert all(
            agent_capability_allowed(agent, capability)
            for capability in AGENT_CAPABILITY_REGISTRY
        )
        assert agent_skill_allowed(agent, 'fs_write')
        assert agent_capability_allowed(agent, 'memory_write')
        assert agent_capability_allowed(agent, 'shared_memory_read')
        assert agent_capability_allowed(agent, 'shared_memory_write')
        assert agent_capability_allowed(agent, 'git_execute')
        assert agent_skill_allowed(agent, 'shared_memory_write')
    assert not agent_capability_allowed('seven', 'memory_write')
    assert not agent_capability_allowed('seven', 'shared_memory_write')


def test_local_trio_prompts_match_tool_enabled_backend_profile():
    from utils import config
    from utils.local_runtime_policy import FULL_AGENT_TOOL_PROMPT, READ_ONLY_PROFILE_PROMPT
    from ops.seed_agent_permissions import (
        AGENT_ROLE_MAP,
        FULL_AGENT_PACK,
    )
    from utils.db.agents import AGENT_CAPABILITY_REGISTRY

    for prompt_name in ('GEMMA_SYSTEM_PROMPT', 'QWEN_SYSTEM_PROMPT', 'LLAMA_SYSTEM_PROMPT'):
        assert FULL_AGENT_TOOL_PROMPT in getattr(config, prompt_name)
    assert READ_ONLY_PROFILE_PROMPT in config.SEVEN_SYSTEM_PROMPT
    assert FULL_AGENT_TOOL_PROMPT not in config.SEVEN_SYSTEM_PROMPT
    assert set(FULL_AGENT_PACK) == set(AGENT_CAPABILITY_REGISTRY)
    for agent in ('gemma', 'qwen', 'llama'):
        assert set(AGENT_ROLE_MAP[agent][1]) == set(AGENT_CAPABILITY_REGISTRY)
    assert 'Never bypass' in FULL_AGENT_TOOL_PROMPT
    assert 'alm_self_approve' in FULL_AGENT_TOOL_PROMPT
    assert 'trust-level 2 mutation skills may be denied' in FULL_AGENT_TOOL_PROMPT


def test_seeded_agent_identity_cards_match_trio_and_guardian_scopes(monkeypatch, tmp_path):
    from ops import seed_agent_permissions

    monkeypatch.setattr(seed_agent_permissions, 'SANDPIT_ROOT', tmp_path)
    for agent in ('gemma', 'qwen', 'llama', 'seven'):
        seed_agent_permissions._write_identity(
            agent, seed_agent_permissions.IDENTITY_TEMPLATES[agent]
        )

    for agent in ('gemma', 'qwen', 'llama'):
        identity = (tmp_path / agent / 'WHO_AM_I.md').read_text(encoding='utf-8')
        assert 'Use only explicitly authorized skills' in identity
        assert 'Never self-approve' in identity
        assert 'read-only repository' not in identity

    seven_identity = (tmp_path / 'seven' / 'WHO_AM_I.md').read_text(encoding='utf-8')
    assert 'read-only guardian' in seven_identity
    assert 'Never grant capabilities' in seven_identity


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


def test_explicit_no_tools_request_skips_automatic_private_memory_write(monkeypatch):
    from utils.db import agents as db_agents

    writes = []
    monkeypatch.setattr(
        db_agents,
        'agent_has_capability',
        lambda agent, capability: agent == 'qwen' and capability == 'memory_write',
    )
    monkeypatch.setattr(
        'database.save_agent_memory',
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )
    response = json.dumps({
        'kind': 'analysis',
        'summary': 'Acknowledged without tools.',
        'evidence': [],
        'proposed_changes': [],
        'human_review_required': True,
    })

    assert not persist_read_only_chat_memory(
        'qwen',
        'Do not use tools or write memory. Acknowledge only.',
        response,
    )
    assert writes == []


def test_no_tools_turn_skips_local_context_retrieval_and_vortex_recording(monkeypatch):
    retrievals = []
    for name in (
        '_repository_matches',
        '_git_history',
        '_vortex_events',
        '_vortex_checkpoints',
    ):
        monkeypatch.setattr(
            read_only_context,
            name,
            lambda *args, _name=name, **kwargs: retrievals.append(_name),
        )

    context = read_only_context.build_local_agent_context(
        'gemma',
        'Do not use tools. Reply with exactly READY.',
    )

    assert 'retrieval skipped' in context
    assert retrievals == []


def test_no_tools_turn_does_not_acknowledge_injected_knowledge(monkeypatch):
    from frontend.blueprints import chat as chat_blueprint
    from utils.db import knowledge

    events = [{'id': 19, 'payload': json.dumps({
        'category': 'lesson',
        'key': 'agent-policy',
        'source_agent': 'qwen',
    })}]
    acknowledgements = []
    monkeypatch.setattr(knowledge, 'get_unacked_events', lambda *_args, **_kwargs: events)
    monkeypatch.setattr(
        knowledge,
        'ack_all_events',
        lambda agent, ids: acknowledgements.append((agent, ids)),
    )

    injected = chat_blueprint._build_knowledge_broadcast_block(
        'gemma', 'Do not use tools or perform actions.'
    )

    assert 'agent-policy' in injected
    assert acknowledgements == []


def test_read_only_chat_memory_skips_errors_and_denied_grants(monkeypatch):
    from utils.db import agents as db_agents

    writes = []
    monkeypatch.setattr(db_agents, 'agent_has_capability', lambda *_args: False)
    monkeypatch.setattr(
        'database.save_agent_memory',
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    error_response = normalize_read_only_response('seven', '[seven] error: offline')
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


def test_shared_memory_isolated_table_and_scoped_capabilities(monkeypatch, tmp_path):
    from utils.db import agents as db_agents
    from utils.db import memory as db_memory

    db_path = tmp_path / 'shared-memory.sqlite'
    connection = sqlite3.connect(db_path)
    connection.execute(
        """CREATE TABLE trio_shared_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            note_content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    connection.executescript(
        """CREATE TRIGGER trg_trio_shared_notes_no_update
           BEFORE UPDATE ON trio_shared_notes
           BEGIN SELECT RAISE(ABORT, 'trio_shared_notes is append-only'); END;
           CREATE TRIGGER trg_trio_shared_notes_no_delete
           BEFORE DELETE ON trio_shared_notes
           BEGIN SELECT RAISE(ABORT, 'trio_shared_notes is append-only'); END;"""
    )
    connection.commit()
    connection.close()

    def _get_connection():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(db_memory, 'get_connection', _get_connection)
    monkeypatch.setattr(
        db_agents,
        'agent_has_capability',
        lambda agent, capability: (
            agent in {'gemma', 'qwen', 'llama'}
            and capability in {'shared_memory_read', 'shared_memory_write'}
        ),
    )

    entry_id = db_memory.save_shared_agent_memory(
        'gemma',
        'Local deployment',
        'Use the local Ollama gateway for the trio.',
        tags='routing',
    )
    entry = db_memory.get_shared_agent_memory('qwen', query='Ollama')[0]

    assert entry['id'] == entry_id
    assert entry['source_agent'] == 'gemma'
    assert entry['subject'] == 'Local deployment'
    assert 'Ollama gateway' in entry['content']
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        connection = _get_connection()
        try:
            connection.execute(
                'UPDATE trio_shared_notes SET note_content=? WHERE id=?',
                ('changed', entry_id),
            )
        finally:
            connection.close()
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        connection = _get_connection()
        try:
            connection.execute('DELETE FROM trio_shared_notes WHERE id=?', (entry_id,))
        finally:
            connection.close()
    with pytest.raises(PermissionError, match='cannot write shared memory'):
        db_memory.save_shared_agent_memory('seven', 'Denied', 'No access.')
    with pytest.raises(PermissionError, match='cannot read shared memory'):
        db_memory.get_shared_agent_memory('seven')


def test_explicit_shared_memory_hook_is_scoped_to_shared_table(monkeypatch):
    from utils import local_runtime_policy

    writes = []
    monkeypatch.setattr(
        'utils.db.memory.save_shared_agent_memory',
        lambda *args, **kwargs: writes.append((args, kwargs)) or 1,
    )
    note = json.dumps({
        'subject': 'Gateway routing',
        'content': 'Keep all three local agents on the Ollama gateway.',
        'tags': 'routing',
    })

    assert local_runtime_policy.persist_explicit_shared_memory_note('qwen', note)
    assert writes == [(
        ('qwen',),
        {
            'subject': 'Gateway routing',
            'content': 'Keep all three local agents on the Ollama gateway.',
            'tags': 'routing',
        },
    )]
    with pytest.raises(PermissionError, match='cannot write shared memory'):
        local_runtime_policy.persist_explicit_shared_memory_note('seven', note)
    assert len(writes) == 1


def test_tool_enabled_trio_shared_memory_command_uses_direct_database_hook(monkeypatch):
    from agents import skills_loop
    from utils import local_runtime_policy

    writes = []
    responses = iter([
        'SKILL shared_memory_write {"subject":"Routing","content":"Use Ollama."}',
        json.dumps({
            'kind': 'analysis',
            'summary': 'The note was shared with the trio.',
            'evidence': [],
            'proposed_changes': [],
            'human_review_required': True,
        }),
    ])
    monkeypatch.setattr(
        local_runtime_policy,
        'persist_explicit_shared_memory_note',
        lambda agent, note: writes.append((agent, note)) or True,
    )
    monkeypatch.setattr(
        'fridays.skills.call',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('general skill dispatcher must not run')
        ),
    )
    monkeypatch.setattr(skills_loop, '_tl', lambda *_args: None)

    answer, tokens = skills_loop.run_skill_loop(
        agent_name='qwen',
        call_fn=lambda _messages: (next(responses), 4),
        messages=[{'role': 'user', 'content': 'Share this routing note with the trio.'}],
        emit_fn=lambda _message: None,
    )

    assert json.loads(answer)['summary'] == 'The note was shared with the trio.'
    assert tokens == 8
    assert writes == [
        ('qwen', '{"subject":"Routing","content":"Use Ollama."}'),
    ]


def test_tool_enabled_trio_can_execute_regular_registered_skills(monkeypatch):
    from agents import skills_loop

    calls = []
    responses = iter([
        'SKILL system_index search agents',
        json.dumps({
            'kind': 'analysis',
            'summary': 'The skill output was reviewed.',
            'evidence': [],
            'proposed_changes': [],
            'human_review_required': True,
        }),
    ])
    monkeypatch.setattr(
        'database.can_user_invoke_skill',
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        'fridays.skills.call',
        lambda name, args='', agent='', **_kwargs: (
            calls.append((name, args, agent)) or (True, 'matched skill output')
        ),
    )
    monkeypatch.setattr(skills_loop, '_tl', lambda *_args: None)

    answer, tokens = skills_loop.run_skill_loop(
        agent_name='qwen',
        call_fn=lambda _messages: (next(responses), 3),
        messages=[{'role': 'user', 'content': 'Find the agent registry.'}],
        emit_fn=lambda _message: None,
    )

    assert json.loads(answer)['summary'] == 'The skill output was reviewed.'
    assert tokens == 6
    assert calls == [('system_index', 'search agents', 'qwen')]


def test_read_only_task_blocks_model_generated_mutation_after_inspection(monkeypatch):
    from agents import skills_loop

    executed = []
    responses = iter([
        'SKILL fs_readonly read .github/skills/swarm-teamwork/SKILL.md',
        'SKILL fs_patch utils/config.py\n```\nx\n```\n```\ny\n```',
        json.dumps({
            'kind': 'analysis',
            'summary': 'The requested inspection completed without changes.',
            'evidence': [],
            'proposed_changes': [],
            'human_review_required': True,
        }),
    ])
    monkeypatch.setattr(
        'database.can_user_invoke_skill',
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        'fridays.skills.call',
        lambda name, args='', agent='', **_kwargs: (
            executed.append((name, args, agent)) or (True, 'read-only content')
        ),
    )
    monkeypatch.setattr(skills_loop, '_tl', lambda *_args: None)

    answer, _tokens = skills_loop.run_skill_loop(
        agent_name='gemma',
        call_fn=lambda _messages: (next(responses), 2),
        messages=[{
            'role': 'user',
            'content': (
                'Read the skill file. Do not edit files, create proposals, or make changes.'
            ),
        }],
        emit_fn=lambda _message: None,
    )

    assert json.loads(answer)['summary'] == 'The requested inspection completed without changes.'
    assert executed == [
        ('fs_readonly', 'read .github/skills/swarm-teamwork/SKILL.md', 'gemma'),
    ]


def test_explicit_no_tools_request_blocks_readonly_skill_even_when_allowlisted(monkeypatch):
    from agents import skills_loop

    executed = []
    responses = iter([
        'SKILL fs_readonly read frontend/blueprints/chat.py',
        json.dumps({
            'kind': 'analysis',
            'summary': 'No tool was executed.',
            'evidence': [],
            'proposed_changes': [],
            'human_review_required': True,
        }),
    ])
    monkeypatch.setattr(
        'database.can_user_invoke_skill',
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        'fridays.skills.call',
        lambda name, args='', agent='', **_kwargs: (
            executed.append((name, args, agent)) or (True, 'unexpected tool output')
        ),
    )
    monkeypatch.setattr(skills_loop, '_tl', lambda *_args: None)

    answer, tokens = skills_loop.run_skill_loop(
        agent_name='llama',
        call_fn=lambda _messages: (next(responses), 2),
        messages=[{
            'role': 'user',
            'content': (
                'Do not use tools, inspect files, write memory, or make changes. '
                'Acknowledge this instruction only.'
            ),
        }],
        emit_fn=lambda _message: None,
        allowed_skill_names={'fs_readonly'},
        nudge_if_no_skills=True,
    )

    assert json.loads(answer)['summary'] == 'No tool was executed.'
    assert tokens == 4
    assert executed == []


def test_read_only_chat_does_not_copy_ordinary_responses_to_shared_pool(monkeypatch):
    from agents import skills_loop
    from utils import local_runtime_policy

    writes = []
    response = json.dumps({
        'kind': 'analysis',
        'summary': 'The local gateway is ready.',
        'evidence': [],
        'proposed_changes': [],
        'human_review_required': True,
    })
    monkeypatch.setattr(
        local_runtime_policy,
        'persist_explicit_shared_memory_note',
        lambda *args: writes.append(args),
    )
    monkeypatch.setattr(skills_loop, '_tl', lambda *_args: None)

    answer, _tokens = skills_loop.run_skill_loop(
        agent_name='gemma',
        call_fn=lambda _messages: (response, 3),
        messages=[{'role': 'user', 'content': 'Check the gateway.'}],
        emit_fn=lambda _message: None,
    )

    assert json.loads(answer)['summary'] == 'The local gateway is ready.'
    assert writes == []


def test_shared_memory_write_failure_cannot_be_reported_as_success(monkeypatch):
    from agents import skills_loop
    from utils import local_runtime_policy

    responses = iter([
        'SKILL shared_memory_write {"subject":"Routing","content":"Use Ollama."}',
        json.dumps({
            'kind': 'analysis',
            'summary': 'The note was shared successfully.',
            'evidence': [],
            'proposed_changes': [],
            'human_review_required': True,
        }),
    ])
    monkeypatch.setattr(
        local_runtime_policy,
        'persist_explicit_shared_memory_note',
        lambda *_args: (_ for _ in ()).throw(PermissionError('permission denied')),
    )
    monkeypatch.setattr(skills_loop, '_tl', lambda *_args: None)

    answer, _tokens = skills_loop.run_skill_loop(
        agent_name='qwen',
        call_fn=lambda _messages: (next(responses), 4),
        messages=[{'role': 'user', 'content': 'Share the routing note.'}],
        emit_fn=lambda _message: None,
    )

    payload = json.loads(answer)
    assert payload['kind'] == 'error'
    assert payload['summary'] == 'Shared-memory write failed: permission denied'


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
        'seven',
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
    result = json.loads(normalize_read_only_response('seven', '[seven] error: model unavailable'))

    assert result['kind'] == 'error'
    assert 'model unavailable' in result['summary']


def test_read_only_empty_response_is_an_explicit_error():
    result = json.loads(normalize_read_only_response('seven', ''))

    assert result['kind'] == 'error'
    assert result['summary'] == 'The agent returned an empty response.'


def test_read_only_seven_skill_loop_never_executes_model_tool_output():
    called = []

    def model_call(_messages):
        return 'SKILL shell rm -rf /', 17

    answer, tokens = run_skill_loop(
        agent_name='seven',
        call_fn=model_call,
        messages=[{'role': 'user', 'content': 'Inspect the code.'}],
        emit_fn=lambda _message: called.append(_message),
    )
    payload = json.loads(answer)

    assert tokens == 17
    assert payload['kind'] == 'error'
    assert payload['blocked_tool'] == 'shell'
    assert 'executing skill' not in called






@pytest.mark.parametrize('path', [
    '/api/agent/tickets',
    '/api/agent/git/proposals',
    '/api/agent/git/proposals/test-proposal/execute',
    '/api/agent/think',
])
def test_read_only_agent_mutation_routes_reject_before_work(monkeypatch, path):
    app = Flask(__name__)
    app.register_blueprint(agent_api.agent_api_bp)
    monkeypatch.setattr(agent_api, '_validate_agent_request', lambda: ('seven', None))
    monkeypatch.setattr(
        agent_api,
        'intake_internal',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('must not queue work')),
    )

    response = app.test_client().post(path, json={'title': 'Forbidden task'})

    assert response.status_code == 403
    assert response.get_json()['ok'] is False


def test_capability_api_can_grant_tool_capability_to_enabled_trio(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(agents_api.agents_bp)
    monkeypatch.setattr(
        agents_api,
        '_resolve_identity_or_response',
        lambda _data: ({'effective_user': 'ghost'}, None),
    )
    monkeypatch.setattr(agents_api, '_reg_roster_bp', lambda: [{'name': 'gemma'}])
    granted = []
    monkeypatch.setattr(
        agents_api,
        'grant_agent_capability',
        lambda *args, **kwargs: granted.append((args, kwargs)),
    )
    monkeypatch.setattr(agents_api, 'get_agent_capabilities', lambda _agent: [])
    monkeypatch.setattr(agents_api, 'log_activity', lambda *_args, **_kwargs: None)

    response = app.test_client().post(
        '/api/agents/capabilities',
        json={'agent': 'gemma', 'capability': 'git_execute', 'enabled': True},
    )

    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    assert granted


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


def test_agent_capability_api_preserves_seven_profile_hard_denies(monkeypatch):
    from utils.db import agents

    monkeypatch.setattr(
        agents,
        'get_connection',
        lambda: (_ for _ in ()).throw(AssertionError('database must not be consulted')),
    )

    assert not agents.agent_has_capability('seven', 'git_execute')
    try:
        agents.grant_agent_capability('seven', 'sandpit_write')
    except PermissionError:
        pass
    else:
        raise AssertionError('read-only capability grant should be rejected')
