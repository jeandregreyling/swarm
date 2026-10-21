from email.mime.multipart import MIMEMultipart
from pathlib import Path
import sys

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'utils'))

from frontend.blueprints import email_bp as mail


def test_text_attachment_contains_exact_file_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv('SWARM_ROOT', str(tmp_path))
    path = tmp_path / 'sandpits' / 'apex' / 'proof.txt'
    path.parent.mkdir(parents=True)
    path.write_text('Local attachment proof.\n', encoding='utf-8')
    message = MIMEMultipart()
    assert mail._attach_sandpit_text_files(message, ['sandpits/apex/proof.txt']) == ['proof.txt']
    part = message.get_payload()[0]
    assert part.get_content_disposition() == 'attachment'
    assert part.get_payload(decode=True) == path.read_bytes()


@pytest.mark.parametrize('path', ['../secret.txt', '.env.agents', 'sandpits/apex/proof.py'])
def test_attachment_rejects_non_sandpit_or_non_text_paths(monkeypatch, tmp_path, path):
    monkeypatch.setenv('SWARM_ROOT', str(tmp_path))
    with pytest.raises(ValueError):
        mail._attach_sandpit_text_files(MIMEMultipart(), [path])


def test_email_route_only_reports_acceptance_after_smtp(monkeypatch):
    import config

    monkeypatch.setattr(config, 'GMAIL_ADDRESS', 'sender@example.test')
    monkeypatch.setattr(config, 'GMAIL_PASSWORD', 'test-only')
    monkeypatch.setattr(mail, 'log_activity', lambda *_args: None)
    monkeypatch.setattr('lib.email.email_handler._record_delivery', lambda *_args: None)
    delivered = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, *args):
            pass

        def send_message(self, message):
            delivered.append(message)
            return {}

    monkeypatch.setattr(mail.smtplib, 'SMTP_SSL', SMTP)
    app = Flask(__name__)
    app.register_blueprint(mail.email_bp)
    response = app.test_client().post('/api/email/send', json={
        'to': 'recipient@example.test', 'subject': 'test', 'body': 'body',
    })
    assert response.status_code == 200
    assert response.json['smtp_accepted'] is True
    assert response.json['message_id'] == delivered[0]['Message-ID']


def test_ticket_reply_uses_recorded_recipient_and_does_not_resend(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from fridays import skills
    import requests

    path = tmp_path / 'sandpits' / 'apex' / 'proof.txt'
    path.parent.mkdir(parents=True)
    path.write_text('local proof')
    monkeypatch.setattr(skills, '_FS_ROOT', tmp_path)
    monkeypatch.setattr(skills, '_fs_safe_path', lambda _rel: path)
    notes = []
    posts = []

    class Connection:
        def execute(self, sql, params):
            if 'FROM ticket_notes' in sql:
                row = {'content': notes[-1]} if notes else None
            elif 'FROM tickets' in sql:
                row = {'sender_email': 'operator@example.test', 'status': 'open'}
            else:
                row = {'agent': 'apex', 'status': 'approved'}
            return SimpleNamespace(fetchone=lambda: row)

        def close(self):
            pass

    def post(url, json, timeout):
        posts.append((url, json))
        return SimpleNamespace(ok=True, json=lambda: {'smtp_accepted': True, 'message_id': '<proof@test>', 'attachments': ['proof.txt']})

    monkeypatch.setattr('utils.db._connection.get_connection', Connection)
    monkeypatch.setattr('core.pipeline.ticket.add_agent_note', lambda *_args: notes.append(_args[-1]))
    monkeypatch.setattr(requests, 'post', post)
    args = 'TICKET-PROOF INTERNAL-APEX-PROOF sandpits/apex/proof.txt'
    assert skills._skill_email_ticket_reply(args, 'apex')[0] is True
    assert posts[0][1]['to'] == 'operator@example.test'
    assert posts[0][1]['attachments'] == ['sandpits/apex/proof.txt']
    assert skills._skill_email_ticket_reply(args, 'apex')[0] is True
    assert len(posts) == 1