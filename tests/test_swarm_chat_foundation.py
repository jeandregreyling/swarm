"""Validates Phase-4 foundation: shared SwarmChat.esc helper.

- File exists at the expected path.
- Template loads it in <script> list before the views.
- Contract is present: window.SwarmChat.esc + escAttr, OWASP escape set.
- chat.js defers to SwarmChat.esc when available.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from frontend.terminal import create_app

_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'swarm-chat.js'
_TPL = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
_CHAT_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'chat.js'


def test_swarm_chat_module_exists():
    assert _JS.exists(), f'missing {_JS}'
    src = _JS.read_text()
    # Namespace + idempotency
    assert 'window.SwarmChat' in src
    assert 'ns.esc = esc' in src
    assert 'ns.escAttr' in src
    # Full OWASP escape set
    for token in ('&amp;', '&lt;', '&gt;', '&quot;', '&#39;'):
        assert token in src, f'missing escape token {token}'


def test_template_loads_swarm_chat_before_views():
    tpl = _TPL.read_text()
    # swarm-chat.js must appear in the template
    assert '/static/js/core/swarm-chat.js' in tpl
    # and it must appear before the Views section marker
    idx_swarm = tpl.find('/static/js/core/swarm-chat.js')
    idx_views = tpl.find('<!-- Views -->')
    assert idx_swarm > 0 and idx_views > 0
    assert idx_swarm < idx_views, 'swarm-chat.js must load before view scripts'


def test_chat_js_prefers_shared_escape():
    src = _CHAT_JS.read_text()
    assert 'window.SwarmChat' in src
    assert 'window.SwarmChat.esc' in src


def test_swarm_chat_js_served_by_flask():
    app = create_app()
    with app.test_client() as c:
        resp = c.get('/static/js/core/swarm-chat.js')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'SwarmChat' in body
    assert 'function esc' in body
