"""Practice 110 (owner 16 Nov 2026; closes Copilot's own proposal S-4FA87BBE34): Copilot is active again and answers to @git and @github
(hb_agents handles, peer_bridge.MENTIONS), but the chat window's "addressed directly" check knew only @copilot/@instructor, so
"@github please review" went to APEX whenever a local model was up."""
import re
from pathlib import Path

from core import peer_bridge

JS = (Path(__file__).resolve().parents[1] / 'frontend/static/js/views/chat.js').read_text()


def _direct_pattern():
    body = JS[JS.index('function getChatDispatchAgents(text) {'):]
    found = re.search(r"if \(/(\^.+?)/i\.test\(String\(text", body)
    return re.compile(found.group(1).replace('\\s', r'\s'), re.I)


def test_practice_110_git_and_github_are_addressed_directly():
    direct = _direct_pattern()
    for text in ('@github please review the last commit', '@git what changed today?', '@copilot hi', '@apex go'):
        assert direct.search(text), text
    assert not direct.search('please ask github about it')


def test_practice_110_server_side_already_knows_them():
    assert peer_bridge.MENTIONS['git'] == peer_bridge.MENTIONS['github'] == 'copilot-instructor'
