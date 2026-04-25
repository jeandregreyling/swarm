from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "frontend"))

from terminal import create_app


TEMPLATE = ROOT / "frontend" / "templates" / "terminal_base.html"
STUDIO_JS = ROOT / "frontend" / "static" / "js" / "views" / "studio.js"


def test_studio_template_contains_media_tab_and_panel():
    html = TEMPLATE.read_text()
    assert "studio-tab-media" in html
    assert "studio-media-panel" in html
    assert "Open Media Center" in html


def test_studio_js_knows_media_tab():
    src = STUDIO_JS.read_text()
    assert "const isMedia = (tab === 'media');" in src
    assert "loadStudioMediaPanel" in src


def test_media_center_state_exposes_studio_interests_feeds_and_spine():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/media-center/state")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "studio" in payload
    assert "interests" in payload
    assert "feeds" in payload
    assert "spine" in payload
    assert "linked_projects" in payload["studio"]
    assert "subscriptions" in payload["feeds"]
