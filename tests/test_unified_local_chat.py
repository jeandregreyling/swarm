import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend'), str(ROOT / 'utils')]


def test_automatic_local_selection_ignores_saved_manual_toggles():
    node = shutil.which('node') or shutil.which('nodejs')
    if node is None:
        pytest.skip('JavaScript runtime is not installed; selection is also checked in-browser')
    source = (ROOT / 'frontend/static/js/views/chat.js').read_text()
    start = source.index('function getAutomaticLocalChatAgents()')
    end = source.index('// Fetch agent registry', start)
    function = source[start:end]
    cases = [
        ([{'value': 'seven', 'tier': 'local'}, {'value': 'gemma', 'tier': 'local'}], ['gemma']),
        ([{'value': 'ten', 'tier': 'paid'}, {'value': 'qwen', 'tier': 'local'}], ['qwen']),
        ([{'value': 'gemma', 'tier': 'local', 'available': False}], []),
        ([{'value': 'seven', 'tier': 'local'}, {'value': 'ten', 'tier': 'paid'}], []),
        ([], []),
    ]
    script = function + '\n' + '\n'.join(
        f'CHAT_AGENT_OPTIONS = {json.dumps(rows)}; '
        f'if (JSON.stringify(getAutomaticLocalChatAgents()) !== {json.dumps(json.dumps(expected, separators=(",", ":")))}) '
        'throw new Error("Incorrect local selection");'
        for rows, expected in cases
    )
    subprocess.run([node, '-e', 'let CHAT_AGENT_OPTIONS;\n' + script], check=True, timeout=10)


def test_both_chat_surfaces_request_local_only_without_manual_selection():
    home = (ROOT / 'frontend/static/js/views/home-chat.js').read_text()
    send = home.split('function _hcSend() {', 1)[1].split("fetch('/api/chat'", 1)[0]
    assert 'getAutomaticLocalChatAgents()' in send
    assert 'HC_MANUAL_KEY' not in send
    assert 'local_only: true' in send
    chat = (ROOT / 'frontend/static/js/views/chat.js').read_text()
    send = chat.split('function sendMessage(', 1)[1]
    assert 'getAutomaticLocalChatAgents()' in send
    assert 'local_only: true' in send
    assert 'auto_relay: false' in send


@pytest.mark.parametrize('path,selectors', [
    ('frontend/static/css/home-chat.css', ['#home-chat-agents-panel', '#home-chat-agents-toggle']),
    ('frontend/static/css/views/chat.css', ['#chat-right-dock', '#chat-dock-resizer', '#chat-dock-restore-btn']),
])
def test_agent_sidebars_stay_hidden(path, selectors):
    source = (ROOT / path).read_text()
    rule = source[source.index(selectors[0]):].split('}', 1)[0]
    assert all(selector in rule for selector in selectors)
    assert 'display: none !important' in rule


def test_execution_summary_counts_receipts_without_claiming_teaching():
    from frontend.blueprints.chat import _chat_execution_breakdown

    result = _chat_execution_breakdown([
        {'skill': 'file_read', 'status': 'succeeded'},
        {'skill': 'file_read', 'status': 'failed'},
        {'skill': 'shell', 'status': 'denied'},
        {'skill': 'alm_create_proposal', 'status': 'skipped'},
    ], 2)
    assert '1 succeeded, 1 failed, 1 denied, 1 skipped' in result
    assert 'Runtime guidance prompts: 2' in result
    assert 'no teaching recorded for this turn' in result
    assert 'not measured' in result


def test_executor_reports_backend_results_not_model_claims(monkeypatch):
    from agents import skills_loop
    import fridays.skills
    import database

    monkeypatch.setattr(database, 'can_user_invoke_skill', lambda *a, **kw: True)
    monkeypatch.setattr(fridays.skills, 'call', lambda *a, **kw: (False, 'not run'))
    stages = []
    skills_loop._execute_skill_cmds([('file_read', 'missing.txt')], 'gemma', stages.append)
    receipts = [json.loads(stage.partition(':')[2]) for stage in stages if stage.startswith('execution_receipt:')]
    assert receipts == [{'skill': 'file_read', 'status': 'failed'}]


def test_local_only_chat_rejects_cloud_before_identity_or_execution(monkeypatch):
    from flask import Flask
    from frontend.blueprints import chat

    monkeypatch.setattr(chat, '_reg_routable', lambda: [
        {'name': 'gemma', 'tier': 'local'},
        {'name': 'ten', 'tier': 'paid'},
    ])
    monkeypatch.setattr(chat, '_resolve_identity_or_response',
                        lambda *a, **kw: pytest.fail('must reject before identity or dispatch'))
    app = Flask(__name__)
    app.register_blueprint(chat.chat_bp)
    with app.test_client() as client:
        response = client.post('/api/chat', json={
            'message': 'Open a program', 'agents': ['ten'], 'local_only': True,
        })
    assert response.status_code == 400
    assert response.get_json()['response'] == 'Local chat cannot dispatch to a non-local agent.'
