from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'studio.js'


def test_studio_defaults_to_projects_tab():
    src = STUDIO_JS.read_text()
    assert "window._studioTab = window._studioTab || 'projects';" in src
    assert "window._studioTab = window._studioTab || 'pending';" not in src