"""Practice 222 (calm swarm 4/5): worker polls are read-only - no write lock per request."""
import sqlite3
import time

from core import peer_bridge as peers, service_accounts


def _conn(tmp_path):
    c = sqlite3.connect(tmp_path / 'h.db')
    peers.ensure_schema(c)
    c.commit()
    return c


def test_seeding_existing_accounts_takes_no_write_lock(tmp_path):
    c = _conn(tmp_path)
    service_accounts.initialise(c)
    peers.ensure_schema(c)
    assert not c.in_transaction            # nothing written, so no write lock held for the rest of the request


def test_a_missing_account_is_still_seeded(tmp_path):
    c = _conn(tmp_path)
    c.execute("DELETE FROM service_principals WHERE id='claude-code'")
    c.commit()
    service_accounts.initialise(c)
    assert c.execute("SELECT 1 FROM service_principals WHERE id='claude-code'").fetchone()


def test_a_poll_refreshes_last_contact_at_most_once_a_minute(tmp_path):
    c = _conn(tmp_path)
    c.execute("UPDATE service_principals SET enabled=1 WHERE id='apex'")
    raw = peers.issue_token(c, 'apex')
    c.commit()
    assert peers.authenticate(c, raw)['id'] == 'apex'
    c.commit()
    assert c.execute("SELECT last_used_at FROM service_tokens WHERE principal_id='apex' AND revoked_at IS NULL").fetchone()[0]
    assert peers.authenticate(c, raw)['id'] == 'apex'
    assert not c.in_transaction            # the next poll within a minute is read-only
    c.execute("UPDATE service_tokens SET last_used_at=? WHERE principal_id='apex'", (time.time() - 120,))
    c.commit()
    peers.authenticate(c, raw)
    assert c.in_transaction                # a minute later the last contact is refreshed
