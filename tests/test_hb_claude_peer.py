"""@claude in main chat (owner 12 Nov): the Claude Code CLI answers explicitly addressed requests, read-only,
one CLI session per chat, and the answer goes back into the same chat."""
import json
import types

import pytest

from scripts import hummingbird_claude_peer as cp
from core import hb_online, peer_bridge


def test_claude_is_a_mentionable_peer_and_an_owner_gated_provider():
    assert peer_bridge.MENTIONS['claude'] == 'claude-code'
    assert peer_bridge.SCOPES['claude-code'] == ('peer.read', 'peer.post', 'peer.memory')
    assert hb_online.PROVIDERS['claude'] == 'claude-code'
    assert hb_online.may_dispatch.__doc__                     # owner senders always pass; automatic ones need /online claude on


def test_command_is_read_only_and_resumes_the_chat_session():
    cmd = cp.build_command('/x/claude', 'hi', 'sess-1')
    assert cmd[:3] == ['/x/claude', '-p', 'hi'] and cmd[cmd.index('--tools') + 1] == 'Read,Grep,Glob'
    assert cmd[cmd.index('--resume') + 1] == 'sess-1' and '--output-format' in cmd
    assert '--resume' not in cp.build_command('/x/claude', 'hi', None)


def test_output_parsing_keeps_answer_session_and_cost():
    out = json.dumps({'type': 'result', 'result': 'HB link ok', 'session_id': 's-9', 'total_cost_usd': 0.0123,
                      'usage': {'input_tokens': 2, 'cache_read_input_tokens': 10, 'cache_creation_input_tokens': 5, 'output_tokens': 7}})
    answer, session, usage = cp.parse_output(out)
    assert (answer, session) == ('HB link ok', 's-9')
    assert usage == {'input_tokens': 17, 'output_tokens': 7, 'total_tokens': 24, 'cost_usd': 0.0123}


def test_a_lost_session_falls_back_to_a_fresh_one(monkeypatch):
    monkeypatch.setattr(cp, 'claude_binary', lambda: '/x/claude')
    calls = []

    def runner(cmd):
        calls.append(cmd)
        if '--resume' in cmd:
            return types.SimpleNamespace(returncode=1, stdout='', stderr='No conversation found with session ID')
        return types.SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({'result': 'fresh', 'session_id': 'new'}))
    assert cp.ask('q', 'old', runner=runner)[:2] == ('fresh', 'new')
    assert len(calls) == 2


class FakeAPI:
    def __init__(self, inbox):
        self.inbox, self.posts, self.acks = inbox, [], []

    def call(self, path, body=None):
        if path.startswith('/api/agent/v1/whoami'):
            return {'principal': 'claude-code'}
        if path.startswith('/api/peer/v1/inbox?'):
            page, self.inbox = self.inbox, []
            return {'messages': page}
        if path == '/api/peer/v1/inbox/ack':
            self.acks += body['ids']
        return {'ok': True}

    def post(self, conversation, text, **routing):
        self.posts.append((conversation, text, routing))
        return {'message_id': 1}


def test_worker_answers_in_the_same_chat_and_remembers_the_session(tmp_path, monkeypatch):
    monkeypatch.setattr(cp.agent_identity, 'STATE', tmp_path)
    api = FakeAPI([{'id': 41, 'conversation_id': 2834, 'recipient': 'claude-code', 'sender': 'user', 'body': '@claude are you there?',
                    'routing': {}}])
    seen = []

    def asker(prompt, session):
        seen.append(session)
        return 'Yes, Claude here.', 'sess-a', {'total_tokens': 30, 'cost_usd': 0.01}
    cp.serve(once=True, api_factory=lambda agent: api, asker=asker)
    assert api.posts[0][0] == 2834 and api.posts[0][1] == 'Yes, Claude here.'
    assert api.posts[0][2]['reply_to_request_id'] == 41 and api.posts[0][2]['model'] == 'claude-code'
    assert api.acks == [41] and seen == [None]
    api.inbox = [{'id': 42, 'conversation_id': 2834, 'recipient': 'claude-code', 'sender': 'user', 'body': 'and again', 'routing': {}}]
    cp.serve(once=True, api_factory=lambda agent: api, asker=asker)
    assert seen == [None, 'sess-a']                            # same chat -> same Claude session


def test_paused_task_is_not_sent_to_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(cp.agent_identity, 'STATE', tmp_path)
    api = FakeAPI([{'id': 43, 'conversation_id': 2834, 'recipient': 'claude-code', 'sender': 'user', 'body': 'x',
                    'routing': {'task_context': {'state': 'paused'}}}])
    cp.serve(once=True, api_factory=lambda agent: api, asker=lambda *a: pytest.fail('paused tasks never reach Claude'))
    assert api.posts == []
