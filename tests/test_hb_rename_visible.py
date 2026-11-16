"""Practice 45 (owner 15 Nov): rename slice 1 - the product name people see in the web UI and on the login page is Hummingbird.
Stored data, session names, storage keys, module names and service names are NOT renamed here (docs/HUMMINGBIRD_NAMESPACE_MIGRATION.md)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEN = ['frontend/templates/terminal_base.html', 'frontend/templates/views/onboarding.html', 'utils/session_auth.py']


def test_practice_45_visible_product_name_is_hummingbird():
    for rel in SEEN:
        text = (ROOT / rel).read_text()
        assert "Seven's Swarm" not in text, rel
    base = (ROOT / SEEN[0]).read_text()
    assert '<span id="sundial-title">Hummingbird</span>' in base and 'Hummingbird Settings</h2>' in base and 'Fridays Settings' not in base
    assert 'Welcome to Hummingbird' in base and 'Welcome to Hummingbird' in (ROOT / SEEN[1]).read_text()
    login = (ROOT / SEEN[2]).read_text()
    assert '<title>Login — Hummingbird</title>' in login and '<h1>Hummingbird</h1>' in login


def test_practice_45_contracts_are_untouched():
    base = (ROOT / SEEN[0]).read_text()
    assert "localStorage.setItem('fridays-welcome-at-startup'" in base      # browser storage key: a data contract, not a label
    assert "'fridays-feeds-subscriptions'" in (ROOT / 'frontend/templates/views/feeds.html').read_text()
