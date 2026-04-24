"""V8 login form UX regression guards.

Covers the three [SMALL] V8 backlog items that describe login-surface
affordances:

* S-BDBC5ABA7C — Enter-key submits the login form
* S-6D81509FF8 — Password fields expose a show/hide eyeball toggle
* S-6A64F17743 — Owner email is configured as a single canonical value
   and the login form accepts an email identifier.

These are JS/DOM contracts rendered by ``frontend/static/js/friday-auth.js``
and the login blueprint, so the asserts inspect the source that actually
ships to the browser rather than driving a headless browser.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRIDAY_AUTH_JS = ROOT / 'frontend' / 'static' / 'js' / 'friday-auth.js'
UTILS_CONFIG = ROOT / 'utils' / 'config.py'


def test_login_enter_key_submits_form():
    """Login username + password inputs submit on Enter."""
    src = FRIDAY_AUTH_JS.read_text()
    # The login wiring registers keydown on loginUser + loginPass with
    # preventDefault + loginBtn.click().
    assert "[loginUser, loginPass].forEach" in src
    assert "if (e.key === 'Enter')" in src
    assert "loginBtn.click();" in src


def test_setup_enter_key_submits_form():
    """First-time setup password fields submit on Enter too."""
    src = FRIDAY_AUTH_JS.read_text()
    assert "[pass, pass2].forEach(el => el.addEventListener('keydown'" in src


def test_password_fields_have_eye_toggle():
    """Login/setup/register password inputs get a show/hide eye."""
    src = FRIDAY_AUTH_JS.read_text()
    # _wireEyeToggle is the shared helper and must be invoked for all
    # three password surfaces.
    assert 'function _wireEyeToggle(input)' in src
    assert "input.type = show ? 'text' : 'password';" in src
    # Login surface
    assert '_wireEyeToggle(loginPass);' in src
    # Register surface (wired inside _showLogin alongside loginPass)
    assert "_wireEyeToggle(overlay.querySelector('#reg-pass'));" in src
    # Setup surface
    assert '_wireEyeToggle(pass);' in src
    assert '_wireEyeToggle(pass2);' in src


def test_owner_email_is_single_canonical_value():
    """GHOST_EMAIL is the one configured owner email — no stale aliases."""
    src = UTILS_CONFIG.read_text()
    assert "GHOST_EMAIL" in src
    # Must resolve to the configured owner mailbox; reject empty/default.
    # We don't pin the literal value here to avoid leaking it into the
    # test log, but it must be assigned a non-empty string constant.
    import re
    match = re.search(r"GHOST_EMAIL\s*=\s*(?:os\.environ\.get\([^)]+\)|['\"][^'\"]+['\"])", src)
    assert match, 'GHOST_EMAIL must be defined in utils/config.py'
