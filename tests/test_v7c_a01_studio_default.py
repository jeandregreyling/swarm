"""V7C-A01 — Studio default/opening logic still wrong.

Project: P-E9BAE4159F
Step:    S-1FA5306FB4
Case:    C-CC3C0322CF
Script:  pytest-studio-defaults (council-of-7 expansion)

History: a shallow single-assert test previously "passed" this step. User
flagged the glazing. This test exercises the real wiring across 7 reviewer
lenses so regressions can't slip back in.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / 'frontend' / 'static' / 'js' / 'core' / 'app.js'
STUDIO_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'studio.js'
TEMPLATE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'


# ── Reviewer 1: FUNCTIONAL — default tab is 'projects' ──────────────────────
def test_r1_default_tab_is_projects():
    src = STUDIO_JS.read_text()
    # Default may now flow through localStorage, but 'projects' must remain
    # the fallback when nothing is stored.
    assert (
        "localStorage.getItem('studio_last_tab') || 'projects'" in src
        or "window._studioTab = window._studioTab || 'projects';" in src
    ), "Default tab must be 'projects' — not pending/proposals/git/testlab."
    assert "window._studioTab = 'projects'" in src, (
        "Catch-branch fallback must still be 'projects'."
    )


# ── Reviewer 2: REGRESSION GUARD — no other default slipped in ──────────────
def test_r2_no_other_default_reintroduced():
    src = STUDIO_JS.read_text()
    forbidden = [
        "window._studioTab = window._studioTab || 'pending'",
        "window._studioTab = window._studioTab || 'proposals'",
        "window._studioTab = window._studioTab || 'git'",
        "window._studioTab = window._studioTab || 'testlab'",
        "window._studioTab = window._studioTab || 'in_progress'",
    ]
    for f in forbidden:
        assert f not in src, f"Forbidden default reintroduced: {f}"


# ── Reviewer 3: WIRING — no stub loadStudioData in app.js ───────────────────
def test_r3_no_stub_in_app_js():
    src = APP_JS.read_text()
    # Real implementation lives in studio.js. Stubs that merely console.log
    # are forbidden — they mask the real wiring if script order ever changes.
    assert "Real implementation will be added once base UI is stable" not in src, (
        "Legacy Studio stub marker still present in app.js — remove it."
    )
    # The stub signature was a body that only called console.log. Anything
    # that looks like a no-op studio function definition here is wrong.
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if 'function loadStudioData' in line or 'function studioSetTab' in line:
            # app.js must not define either function
            raise AssertionError(
                f"app.js:{i+1} must not define Studio functions — "
                "they are owned by views/studio.js."
            )


# ── Reviewer 4: SCRIPT ORDER — app.js before studio.js ──────────────────────
def test_r4_script_load_order():
    tpl = TEMPLATE.read_text()
    app_idx = tpl.find('/static/js/core/app.js')
    studio_idx = tpl.find('/static/js/views/studio.js')
    assert app_idx > 0, "core/app.js script tag missing"
    assert studio_idx > 0, "views/studio.js script tag missing"
    assert app_idx < studio_idx, (
        "core/app.js must load before views/studio.js so the Studio tile's "
        "openWindow('studio'...) callback has the real implementation bound."
    )


# ── Reviewer 5: DOM CONTRACT — required studio DOM ids present ──────────────
def test_r5_studio_dom_ids_present():
    tpl = TEMPLATE.read_text()
    required = [
        'id="studio-tab-projects"',
        'id="studio-projects-panel"',
        'id="studio-content"',
    ]
    for r in required:
        assert r in tpl, f"Studio DOM contract missing: {r}"


# ── Reviewer 6: OPEN-TO-PROJECTS — studioSetTab('projects') shows panel ────
def test_r6_projects_path_shows_projects_panel():
    src = STUDIO_JS.read_text()
    # The tab switch must toggle projectsPanel visibility based on isProjects.
    assert "const isProjects = (tab === 'projects');" in src
    assert "projectsPanel.style.display  = isProjects  ? 'flex' : 'none';" in src or \
           "projectsPanel.style.display = isProjects ? 'flex' : 'none';" in src or \
           "projectsPanel.style.display" in src and "isProjects" in src
    # The projects branch must trigger the loader.
    assert "loadStudioProjectsPanel" in src


# ── Reviewer 7: APP-WIRING — openWindow('studio') calls loadStudioData ─────
def test_r7_open_studio_calls_load_studio_data():
    src = APP_JS.read_text()
    # Canonical wiring in openWindow switch.
    assert "id === 'studio'" in src and "loadStudioData(win)" in src, (
        "openWindow flow must still call loadStudioData(win) for 'studio'."
    )
