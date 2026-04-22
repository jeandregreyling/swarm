"""Phase 5 UI surface: home-chat renders a provenance badge for agent interests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_HC_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'home-chat.js'
_HC_CSS = ROOT / 'frontend' / 'static' / 'css' / 'home-chat.css'


def test_home_chat_renders_agent_badge():
    src = _HC_JS.read_text()
    # Reads the new provenance fields from the API response
    assert "item.source === 'agent'" in src
    assert 'item.source_agent' in src
    # Renders a dedicated badge element
    assert 'home-interest-agent' in src
    # Maps the three whitelisted agents to emoji (any subset shown here)
    assert 'librarian' in src.lower()
    assert 'scholar' in src.lower()
    assert 'seeker' in src.lower()


def test_home_chat_css_styles_agent_badge():
    css = _HC_CSS.read_text()
    assert '.home-interest-agent' in css


def test_home_chat_badge_served_by_flask():
    from frontend.terminal import create_app
    app = create_app()
    with app.test_client() as c:
        js_resp = c.get('/static/js/views/home-chat.js')
        css_resp = c.get('/static/css/home-chat.css')
    assert js_resp.status_code == 200
    assert css_resp.status_code == 200
    assert 'home-interest-agent' in js_resp.get_data(as_text=True)
    assert '.home-interest-agent' in css_resp.get_data(as_text=True)
