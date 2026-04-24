"""V8 Phase-5 MED Wave 2 code-change guards.

* S-5BFE8F8AC8 — Studio Proposals branches renamed to Proposed / In Progress /
   History with descriptive tooltips.
* S-926EBCBBEC — Feeds view gains an explicit "Login Curation" opt-in that
   persists to `fridays-feeds-login-curation` in localStorage.
* S-48738493AC — Terminal view adds a bottom menubar (status / exit code /
   duration / bubble toggle), a resizable shortcuts sidebar drag handle, and
   CSS for a `.terminal-bubble-mode` grid output.
* S-C505B1DB76 — Email view gains a folder sidebar (Inbox / Sent / Drafts /
   Trash) with localStorage persistence and `folder=` in the inbox fetch URL.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERMINAL_BASE = ROOT / 'frontend' / 'templates' / 'terminal_base.html'
FEEDS_HTML = ROOT / 'frontend' / 'templates' / 'views' / 'feeds.html'
COMPONENTS_CSS = ROOT / 'frontend' / 'static' / 'css' / 'components.css'
EMAIL_JS = ROOT / 'frontend' / 'static' / 'js' / 'views' / 'email.js'


def test_studio_proposal_tabs_use_branch_labels():
    src = TERMINAL_BASE.read_text()
    # The Pending tab must now read "Proposed" to match the V8 branch naming.
    assert '>Proposed<' in src
    assert 'Proposed — new proposals awaiting review' in src
    # In Progress + History labels and tooltips.
    assert 'In Progress — approved, under UAT' in src
    assert 'History — rejected, closed, and done proposals' in src


def test_feeds_view_has_login_curation_toggle():
    src = FEEDS_HTML.read_text()
    assert 'id="feeds-login-curation"' in src
    assert 'id="feeds-login-curation-toggle"' in src
    # Script-side persistence key.
    assert "'fridays-feeds-login-curation'" in src
    # Toggle must persist on change.
    assert 'localStorage.setItem(CURATION_KEY' in src


def test_terminal_has_bottom_menubar_and_resizer():
    src = TERMINAL_BASE.read_text()
    assert 'id="terminal-bottom-menubar"' in src
    assert 'id="terminal-status-text"' in src
    assert 'id="terminal-exit-code"' in src
    assert 'id="terminal-elapsed"' in src
    assert 'id="terminal-bubble-toggle"' in src
    assert 'id="terminal-sidebar-resizer"' in src
    assert 'cursor:col-resize' in src


def test_terminal_bubble_mode_css_defined():
    css = COMPONENTS_CSS.read_text()
    assert '#terminal-output.terminal-bubble-mode' in css
    assert 'grid-template-columns: repeat(auto-fill' in css


def test_email_has_folder_sidebar_and_persistence():
    src = EMAIL_JS.read_text()
    # Folder registry with all four standard buckets.
    assert '_EMAIL_FOLDERS' in src
    for key in ("'inbox'", "'sent'", "'drafts'", "'trash'"):
        assert key in src, f'missing folder entry {key}'
    # Folder nav container.
    assert 'id="email-folder-nav"' in src
    assert '_emailSetFolder' in src
    # Persisted choice + forwarded to API.
    assert "'fridays-email-folder'" in src
    assert "'&folder='+encodeURIComponent(_emailActiveFolder)" in src
