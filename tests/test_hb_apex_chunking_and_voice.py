"""Tests for APEX-owned dynamic chunking (no forced 1-chunk stops) and lively DREAM-M thought voice."""
import sqlite3
from pathlib import Path

from core import apex_tools, hb_chunks

ROOT = Path(__file__).resolve().parents[1]


def test_apex_owns_chunking_pace_and_sees_remaining_steps():
    conn = sqlite3.connect(':memory:')
    hb_chunks.table(conn)
    conn.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    task = {
        'task_id': 'T-CHUNK1234567',
        'objective': 'Do: change_set show, then change_set apply, then run_tests, then report.',
        'step_id': None,
    }
    msg = hb_chunks.focus(conn, task)
    assert 'YOU decide the chunking and pace' in msg
    assert 'work ONLY on chunk' not in msg
    assert 'Remaining steps you can also tackle this turn' in msg


def test_thought_guidance_encourages_lively_first_person_dream_motivation():
    guidance = apex_tools.scoped_tool_guidance(['read_file', 'run_tests'])
    assert 'lively, self-motivating' in guidance
    assert 'skip dry robotic status echoes' in guidance
