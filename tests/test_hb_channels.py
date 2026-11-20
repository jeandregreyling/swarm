"""Base channel contracts without live Telegram or model traffic."""
import sqlite3
from core import hb_channels as c


def test_unknown_sender_cannot_enqueue_or_execute(monkeypatch):
    db = sqlite3.connect(':memory:')
    c.ensure(db)
    posted = []
    monkeypatch.setattr(c, '_post', lambda *a, **k: posted.append(a[2]) or 1)
    assert 'does not know' in c.inbound(db, 'telegram', 'telegram:7', 'stranger', '/continue T-123456789ABC')
    assert len(posted) == 1
    assert db.execute('SELECT direction FROM hb_channel_log').fetchone()[0] == 'unknown'


def test_plain_and_chunks_keep_phone_output_bounded():
    assert c.plain('**Done** [evidence](/receipt)') == 'Done evidence'
    parts = c.chunks('x' * 20, size=4, most=3)
    assert len(parts) == 3 and 'rest is in main chat' in parts[-1]


def test_question_classification_does_not_restore_raw_task_spam():
    assert c.kind_of('Hey', True) == 'question'
    assert c.kind_of('Fix it', True) == 'question'
    assert c.kind_of('/status', True) == 'command'
