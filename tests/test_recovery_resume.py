import copy
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend'), str(ROOT / 'utils')]

from core.chat_continuity import ID_FLOOR, NOTICE, ContinuityChat
from core.recovery_resume import import_journal


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    connection.executescript('''
        CREATE TABLE conversations (id INTEGER PRIMARY KEY, title TEXT, source TEXT, sender TEXT);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER,
            from_agent TEXT, to_agent TEXT, content TEXT, message_type TEXT,
            tokens_used INTEGER, created_at TEXT);
    ''')
    yield connection
    connection.close()


@pytest.fixture
def journal():
    return {'id': ID_FLOOR + 15, 'owner': 'ghost', 'title': 'Recovery work',
            'messages': [
                {'sender': 'user', 'content': 'Fix Hummingbird', 'created_at': '2026-11-06T01:00:00Z'},
                {'sender': 'apex', 'content': NOTICE + '\n\nNo tools were attached.',
                 'created_at': '2026-11-06T01:00:01Z'},
            ]}


def test_import_is_exact_idempotent_and_does_not_mutate_original(conn, journal):
    original = copy.deepcopy(journal)
    result = import_journal(conn, journal, 'ghost')
    assert result['imported_messages'] == 2
    assert result['already_imported'] is False
    assert journal == original
    rows = conn.execute('SELECT from_agent,content,created_at FROM messages ORDER BY id').fetchall()
    assert rows[0] == ('user', 'Fix Hummingbird', '2026-11-06T01:00:00Z')
    assert NOTICE not in rows[1][1] and 'Historical recovery reply' in rows[1][1]
    again = import_journal(conn, journal, 'ghost')
    assert again['conversation_id'] == result['conversation_id']
    assert again['already_imported'] is True
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 2


def test_wrong_owner_and_new_journal_messages_cannot_silently_resume(conn, journal):
    with pytest.raises(PermissionError):
        import_journal(conn, journal, 'other')
    import_journal(conn, journal, 'ghost')
    journal['messages'].append({'sender': 'user', 'content': 'New work', 'created_at': '2026-11-06'})
    with pytest.raises(ValueError, match='changed after import'):
        import_journal(conn, journal, 'ghost')
    assert conn.execute('SELECT COUNT(*) FROM conversations').fetchone()[0] == 1


def test_partial_import_rolls_back_every_message(conn, journal):
    conn.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON messages WHEN NEW.from_agent='apex' "
                 "BEGIN SELECT RAISE(ABORT, 'fixture failure'); END")
    with pytest.raises(sqlite3.DatabaseError, match='fixture failure'):
        import_journal(conn, journal, 'ghost')
    assert conn.execute('SELECT COUNT(*) FROM conversations').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0


def test_failed_integrity_check_never_creates_import_tables_or_messages(conn, journal, monkeypatch):
    def fail(_conn):
        raise sqlite3.DatabaseError('database disk image is malformed')
    monkeypatch.setattr('core.recovery_resume.verify_storage', fail)
    with pytest.raises(sqlite3.DatabaseError, match='malformed'):
        import_journal(conn, journal, 'ghost')
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='recovery_thread_imports'").fetchone() is None
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 0


def test_missing_import_target_is_reported(conn, journal):
    result = import_journal(conn, journal, 'ghost')
    conn.execute('DELETE FROM conversations WHERE id=?', (result['conversation_id'],))
    conn.commit()
    with pytest.raises(ValueError, match='missing'):
        import_journal(conn, journal, 'ghost')


def test_owner_route_preserves_journal_and_rejects_other_origins(conn, journal, tmp_path, monkeypatch):
    from core.recovery_supervisor import _write_json
    module = importlib.import_module('frontend.blueprints.conversations')
    continuity = ContinuityChat(tmp_path)
    _write_json(continuity.path(journal['id']), journal)
    before = continuity.path(journal['id']).read_bytes()
    monkeypatch.setattr('core.chat_continuity.ContinuityChat', lambda: continuity)
    monkeypatch.setattr(module, 'get_current_user', lambda: {'username': 'ghost', 'role': 'owner'})
    # Use a file connection because the route owns and closes it.
    path = tmp_path / 'primary.db'
    backup = sqlite3.connect(path)
    conn.backup(backup)
    backup.close()
    monkeypatch.setattr(module, 'get_connection', lambda: sqlite3.connect(path))
    app = Flask(__name__)
    app.register_blueprint(module.conversations_bp)
    client = app.test_client()
    url = f"/api/conversations/{journal['id']}/resume"
    assert client.post(url, json={}, headers={'Origin': 'https://other.invalid'}).status_code == 403
    response = client.post(url, json={})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['conversation_id'] < ID_FLOOR
    assert continuity.path(journal['id']).read_bytes() == before
    monkeypatch.setattr(module, 'get_current_user', lambda: {'username': 'other', 'role': 'owner'})
    assert client.post(url, json={}).status_code == 403
    monkeypatch.setattr(module, 'get_current_user', lambda: None)
    assert client.post(url, json={}).status_code == 403
