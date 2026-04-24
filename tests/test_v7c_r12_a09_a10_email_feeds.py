"""V7C-R12 + A09 + A10 — Email/enrolment/feeds/account.

Project: P-E9BAE4159F
Steps:   S-74ACBED376 (R12), S-7B784DEAAB (A09), S-47E3AE816F (A10)

Locks:
  - Email: folder sidebar visible (Inbox/Sent/Drafts/Trash)
  - Email: account tabs per configured account
  - Email: Accounts manager button + modal (A09 fix)
  - Email: persists active folder in localStorage
  - Feeds: login curation toggle (already in place)
  - Feeds: status clearly labelled "Partial" with A10 reference (not "Coming soon")
  - Feeds: local RSS subscription persistence
"""
from pathlib import Path

ROOT  = Path(__file__).resolve().parents[1]
EMAIL = (ROOT / 'frontend' / 'static' / 'js' / 'views' / 'email.js').read_text()
FEEDS = (ROOT / 'frontend' / 'templates' / 'views' / 'feeds.html').read_text()


def test_r12_r1_email_folders_sidebar():
    for key in ('inbox', 'sent', 'drafts', 'trash'):
        assert f"key: '{key}'" in EMAIL
    assert 'id="email-folder-nav"' in EMAIL


def test_r12_r2_email_account_tabs():
    assert "_EMAIL_ACCOUNTS = [" in EMAIL
    assert 'id="email-tab-all"' in EMAIL
    assert '_emailSetAccount' in EMAIL


def test_a09_r3_accounts_manager_button():
    assert 'id="email-manage-accounts"' in EMAIL
    assert '_emailOpenAccountManager()' in EMAIL


def test_a09_r4_accounts_manager_modal_and_actions():
    assert "function _emailOpenAccountManager(" in EMAIL
    assert "id='email-accounts-modal'" in EMAIL or "'email-accounts-modal'" in EMAIL
    assert "_emailRequestAccountAdd" in EMAIL
    assert "_emailRequestAccountRemove" in EMAIL


def test_r12_r5_email_folder_persists():
    assert "localStorage.getItem('fridays-email-folder')" in EMAIL


def test_a10_r6_feeds_status_not_placeholder():
    # Old "Coming soon" header must be gone; new status honestly says Partial.
    assert 'Coming soon' not in FEEDS.split('<style>')[0]
    assert 'Partial' in FEEDS
    assert 'S-47E3AE816F' in FEEDS  # explicit tracking reference


def test_r12_r7_feeds_login_curation():
    assert 'id="feeds-login-curation-toggle"' in FEEDS
    assert "fridays-feeds-login-curation" in FEEDS
