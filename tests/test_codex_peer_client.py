import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hummingbird_peer_client import PeerClient
from hummingbird_codex_mcp import respond, invoke


def credentials(tmp_path, **changes):
    path = tmp_path / 'peer.json'
    data = {'base_url': 'http://127.0.0.1:5050', 'principal': 'codex-instructor', 'token': 'hbp_' + 'a' * 43}
    data.update(changes)
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('origin', ['https://example.com', 'http://localhost:5050',
    'http://127.0.0.1:5050/api', 'http://user:pass@127.0.0.1:5050', 'http://127.0.0.1:5050/?key=secret'])
def test_client_refuses_other_origins(tmp_path, origin):
    with pytest.raises(ValueError):
        PeerClient(credentials(tmp_path, base_url=origin))


def test_client_requires_private_dedicated_credentials(tmp_path):
    path = credentials(tmp_path)
    assert PeerClient(path).origin == 'http://127.0.0.1:5050'
    path.chmod(0o644)
    with pytest.raises(ValueError, match='0600'):
        PeerClient(path)
    path = credentials(tmp_path, principal='copilot-instructor')
    with pytest.raises(ValueError, match='dedicated'):
        PeerClient(path)


class FakeClient:
    def __init__(self):
        self.calls = []
    def whoami(self):
        return {'ok': True, 'principal': 'codex-instructor'}
    def request(self, path, body=None):
        self.calls.append((path, body))
        return {'ok': True, 'message_id': 15}


def test_mcp_lifecycle_is_local_and_reply_uses_scoped_peer_api():
    client = FakeClient()
    init = respond({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                    'params': {'protocolVersion': '2025-03-26'}}, lambda: client)
    assert init['result']['protocolVersion'] == '2025-03-26'
    tools = respond({'id': 2, 'method': 'tools/list'}, lambda: client)['result']['tools']
    assert {t['name'] for t in tools} == {'hummingbird_identity', 'hummingbird_inbox',
        'hummingbird_thread', 'hummingbird_reply', 'hummingbird_ack'}
    assert client.calls == []
    result = respond({'id': 3, 'method': 'tools/call', 'params': {'name': 'hummingbird_reply',
        'arguments': {'conversation_id': 2829, 'text': 'Verified recovery receipts.'}}}, lambda: client)
    assert not result['result'].get('isError')
    assert client.calls == [('/api/peer/v1/messages', {'conversation_id': 2829, 'text': 'Verified recovery receipts.'})]


@pytest.mark.parametrize('name,arguments', [
    ('hummingbird_reply', {'conversation_id': True, 'text': 'x'}),
    ('hummingbird_reply', {'conversation_id': 1, 'text': 'x', 'as': 'ghost'}),
    ('hummingbird_inbox', {'limit': 500}), ('hummingbird_ack', {'ids': [True]}),
    ('shell', {'command': 'anything'}),
])
def test_mcp_rejects_undeclared_arguments_without_dispatch(name, arguments):
    client = FakeClient()
    with pytest.raises(ValueError):
        invoke(client, name, arguments)
    assert client.calls == []
