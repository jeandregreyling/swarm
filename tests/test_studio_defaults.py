from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'studio.js'


def test_studio_defaults_to_projects_tab():
    """Studio should default to the 'projects' tab on first load.

    Implementation moved to localStorage (studio.js:18-20) but the semantic
    contract is unchanged: when nothing is stored, default to 'projects',
    NOT 'pending'.
    """
    src = STUDIO_JS.read_text()
    # The bootstrap block must wire 'projects' as the default fallback.
    assert "localStorage.getItem('studio_last_tab') || 'projects'" in src, (
        "studio bootstrap no longer defaults to 'projects'"
    )
    assert "window._studioTab = 'projects'" in src, (
        "studio catch-branch fallback no longer 'projects'"
    )
    # Hard default of 'pending' would regress UX — must not exist.
    assert "window._studioTab = window._studioTab || 'pending';" not in src
    assert "window._studioTab = 'pending'" not in src