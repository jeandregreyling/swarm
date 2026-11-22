"""Tests for Phone Flow 2: truthful observed queued/preparing/running/answer_posted progress (deduplicated, never guessed)."""
import sqlite3
from core import hb_channels as ch


def test_phone_progress_records_observed_stages_and_deduplicates():
    conn = sqlite3.connect(':memory:')
    assert ch.record_phone_stage(conn, 9001, 'queued', 'Queued for APEX', channel='telegram', sender_key='telegram:8735763890') is True
    # Exact duplicate stage+detail is deduplicated
    assert ch.record_phone_stage(conn, 9001, 'queued', 'Queued for APEX', channel='telegram', sender_key='telegram:8735763890') is False
    # New observed transition updates cleanly
    assert ch.record_phone_stage(conn, 9001, 'running', 'APEX is working on this phone request') is True
    assert ch.record_phone_stage(conn, 9001, 'answer_posted', 'Here is your verified answer.') is True
    rows = ch.recent_phone_progress(conn, limit=5)
    assert len(rows) == 1
    assert rows[0]['message_id'] == 9001 and rows[0]['stage'] == 'answer_posted'
