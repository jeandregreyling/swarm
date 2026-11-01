from pathlib import Path
import sqlite3
import sys

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'utils'))

from frontend.blueprints import email_bp as mail


def _client(monkeypatch, tmp_path):
    db = tmp_path / 'mail.db'
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE email_delivery_log (id INTEGER PRIMARY KEY, sender TEXT, to_address TEXT, cc TEXT, "
        "subject TEXT, in_reply_to TEXT, sent_at TEXT, status TEXT, attempts INTEGER, error TEXT)"
    )
    conn.executemany(
        "INSERT INTO email_delivery_log (sender, to_address, cc, subject, in_reply_to, sent_at, status, attempts, error) "
        "VALUES (?, ?, '', ?, '', ?, ?, 1, ?)",
        [
            ('sevenpotato9@gmail.com', 'a@example.test', 'Digest', '2026-10-20 01:00:00', 'ok', ''),
            ('ninepotato7@gmail.com', 'b@example.test', 'Nine note', '2026-10-21 01:00:00', 'failed', 'boom'),
        ],
    )
    conn.commit()
    conn.close()

    def connect():
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(mail, 'get_connection', connect)
    app = Flask(__name__)
    app.register_blueprint(mail.email_bp)
    return app.test_client()


def test_sent_folder_lists_delivery_log_newest_first(monkeypatch, tmp_path):
    data = _client(monkeypatch, tmp_path).get('/api/email/inbox?folder=sent').get_json()
    assert data['folder'] == 'sent'
    assert [e['subject'] for e in data['emails']] == ['Nine note', 'Digest']
    assert data['emails'][0]['status'] == 'failed'
    assert data['emails'][0]['error'] == 'boom'


def test_sent_folder_filters_by_account(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    data = client.get('/api/email/inbox?folder=sent&account=SevenPotato9@gmail.com').get_json()
    assert [e['to_address'] for e in data['emails']] == ['a@example.test']


def test_drafts_and_trash_are_empty_with_note(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for folder in ('drafts', 'trash'):
        data = client.get(f'/api/email/inbox?folder={folder}').get_json()
        assert data['emails'] == [] and 'not synced' in data['note']


def test_norm_subject_strips_reply_prefixes():
    assert mail._norm_subject('Re: FWD:  Daily   Digest') == 'daily digest'
    assert mail._norm_subject('Re:Re: x') == 'x'
