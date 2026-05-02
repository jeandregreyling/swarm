"""Phase 5 wiring: housekeeping decay hook + /api/interests provenance fields."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_housekeeping_calls_interest_decay():
    """run_housekeeping should import decay_agent_interests and call it."""
    src = (ROOT / 'lib' / 'system' / 'housekeeping.py').read_text()
    assert 'from utils.db.interests import decay_agent_interests' in src
    assert 'decay_agent_interests(' in src
    # Must be inside run_housekeeping() so the nightly sweep actually triggers it
    rh_idx = src.find('def run_housekeeping')
    decay_idx = src.find('decay_agent_interests(')
    assert rh_idx > 0 and decay_idx > rh_idx, \
        'decay_agent_interests must be called within run_housekeeping()'


def test_housekeeping_swarm_root_derived():
    """housekeeping.py no longer hardcodes /home/seven/swarm."""
    src = (ROOT / 'lib' / 'system' / 'housekeeping.py').read_text()
    assert "sys.path.insert(0, '/home/seven/swarm')" not in src
    assert 'SWARM_ROOT' in src


def test_interests_api_returns_source_and_source_agent():
    """The /api/interests saved_interests rows now include provenance fields."""
    from frontend.terminal import create_app
    # Bind the connection through the same module the blueprint uses, so the
    # INSERT we do here lands in the same DB that /api/interests will read,
    # even when other tests have monkey-patched the lower-level
    # ``utils.db._connection.get_connection`` binding.
    from database import get_connection

    # Insert one agent-sourced row so we can verify shape
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_interests "
            "(username, topic, category, source, source_agent, score, active) "
            "VALUES ('ghost', '__test_phase5_topic__', 'test', 'agent', 'scholar', 5.0, 1)"
        )
        conn.commit()
    finally:
        conn.close()

    app = create_app()
    try:
        with app.test_client() as c:
            resp = c.get('/api/interests?username=ghost')
        assert resp.status_code == 200
        data = resp.get_json()
        saved = data.get('saved_interests') or []
        # Find our injected row
        matches = [r for r in saved if r.get('topic') == '__test_phase5_topic__']
        assert matches, f'injected row not returned; got {len(saved)} saved interests'
        row = matches[0]
        assert row.get('source') == 'agent'
        assert row.get('source_agent') == 'scholar'
    finally:
        # Cleanup
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM user_interests WHERE topic = '__test_phase5_topic__'"
            )
            conn.commit()
        finally:
            conn.close()
