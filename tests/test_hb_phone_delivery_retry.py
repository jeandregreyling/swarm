"""A failed send must not consume the source; successful chunks survive retries/restarts."""
import json
import sqlite3
import pytest
from core import hb_channels as c, hb_commands


@pytest.fixture
def db(tmp_path, monkeypatch):
    db = sqlite3.connect(tmp_path / 'channels.db')
    db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, conversation_id INTEGER, from_agent TEXT, content TEXT, message_type TEXT)')
    c.ensure(db)
    monkeypatch.setattr(c, '_chat', lambda _: 1)
    monkeypatch.setattr(hb_commands, 'waiting_items', lambda _: [])
    c.set_cursor(db, 'mirror_last_id', 0)
    db.commit()
    yield db
    db.close()


def post(db, mid, text='hello', kind='response'):
    db.execute('INSERT INTO messages VALUES (?,1,?,?,?)', (mid, 'apex', text, kind))
    db.commit()


@pytest.mark.parametrize('raises', [False, True])
def test_failed_send_is_retried_then_acknowledged_once(db, raises):
    post(db, 1)
    def fail(text):
        assert not db.in_transaction
        if raises:
            raise OSError('transport unavailable')
        return False
    assert c.mirror_once(db, fail) == 0
    assert c.cursor(db, 'mirror_last_id') == '0'
    calls = []
    assert c.mirror_once(db, lambda text: calls.append(text) or True) == 1
    assert calls == ['APEX: hello']
    assert c.cursor(db, 'mirror_last_id') == '1'
    assert c.mirror_once(db, lambda _: pytest.fail('already acknowledged')) == 0


def test_partial_chunks_resume_after_reopening_db(db):
    post(db, 1, 'x' * 8000)
    calls = []
    assert c.mirror_once(db, lambda text: calls.append(text) or len(calls) == 1) == 1
    assert len(calls) == 2
    path = db.execute('PRAGMA database_list').fetchone()[2]
    other = sqlite3.connect(path)
    resumed = []
    try:
        assert c.mirror_once(other, lambda text: resumed.append(text) or True) == 2
        assert resumed[0] == calls[1] and len(resumed[1]) < c.TELEGRAM_CHUNK
        assert c.cursor(other, 'mirror_last_id') == '1'
    finally:
        other.close()


def test_failed_needs_item_survives_retry_and_is_seen_only_after_send(db, monkeypatch):
    item = {'key': 'accept:S-ABC', 'kind': 'accept', 'step_id': 'S-ABC', 'label': 'Check complete'}
    monkeypatch.setattr(hb_commands, 'waiting_items', lambda _: [item])
    assert c.mirror_once(db, lambda _: False) == 0
    assert json.loads(c.cursor(db, 'needs_seen', '[]')) == []
    # The durable payload remains even if the live item disappears before the retry.
    monkeypatch.setattr(hb_commands, 'waiting_items', lambda _: [])
    sent = []
    assert c.mirror_once(db, lambda text: sent.append(text) or True) == 1
    assert '/accept S-ABC' in sent[0]
    assert json.loads(c.cursor(db, 'needs_seen')) == ['accept:S-ABC']


def test_network_callback_does_not_hold_db_writer_and_nested_tick_does_not_duplicate(db):
    post(db, 1)
    path = db.execute('PRAGMA database_list').fetchone()[2]
    calls = []
    def send(text):
        assert not db.in_transaction
        writer = sqlite3.connect(path, timeout=0)
        try:
            writer.execute("INSERT INTO hb_channel_cursor VALUES ('independent','ok')")
            writer.commit()
            assert c.mirror_once(writer, lambda _: pytest.fail('overlapping tick sent twice')) == 0
        finally:
            writer.close()
        calls.append(text)
        return True
    assert c.mirror_once(db, send) == 1
    assert calls == ['APEX: hello']


def test_first_start_skips_history_and_existing_needs(db, monkeypatch):
    db.execute("DELETE FROM hb_channel_cursor")
    post(db, 8, 'old history')
    monkeypatch.setattr(hb_commands, 'waiting_items', lambda _: [{'key': 'old', 'label': 'old need'}])
    assert c.mirror_once(db, lambda _: pytest.fail('replayed old history')) == 0
    assert c.cursor(db, 'mirror_last_id') == '8'
    assert json.loads(c.cursor(db, 'needs_seen')) == ['old']
    assert not db.in_transaction


def test_skipped_echo_and_tool_noise_advance_only_after_earlier_delivery(db):
    post(db, 1, 'deliver me')
    post(db, 2, 'phone echo')
    post(db, 3, '{"noise":1}', 'tool_result')
    c._log(db, 'telegram', 'in', 'owner', 2, 'phone echo')
    db.commit()
    assert c.mirror_once(db, lambda _: False) == 0
    assert c.cursor(db, 'mirror_last_id') == '0'
    assert c.mirror_once(db, lambda _: True) == 1
    assert c.cursor(db, 'mirror_last_id') == '3'
