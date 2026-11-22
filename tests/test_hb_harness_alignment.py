"""Tests for Dynamic Benchmarked read_file + HB Harness Alignment (owner sync, Shakira handoff, truthful BA announce)."""
import json
import sqlite3
from pathlib import Path

from core import apex_tools, hb_announce


def test_dynamic_read_limit_scales_with_context_and_adapts_on_pressure():
    small = apex_tools.dynamic_read_limit(ctx_tokens=8192, backoff_level=0)
    nemo = apex_tools.dynamic_read_limit(ctx_tokens=24832, backoff_level=0)
    big = apex_tools.dynamic_read_limit(ctx_tokens=65536, backoff_level=0)
    assert 150 <= small < nemo < big <= 600
    assert nemo >= 400
    backed = apex_tools.dynamic_read_limit(ctx_tokens=24832, backoff_level=1)
    assert 120 <= backed < nemo
    # Live read_file on a real >200 line file now returns the whole file in 1 read instead of chopping at 100 lines!
    repo = apex_tools.ReadOnlyRepository()
    raw = repo.call('read_file', {'path': 'core/hb_nectar.py', 'start': 1, 'end': 300, 'raw': True})
    assert len(raw.splitlines()) > 150
    # APEX can still request smaller chunks naturally with start/end whenever it wants
    small_chunk = repo.call('read_file', {'path': 'core/hb_nectar.py', 'start': 1, 'end': 60, 'raw': True})
    assert len(small_chunk.splitlines()) == 60


def test_workflow_run_syncs_claude_code_owner_to_apex():
    src = Path('core/hb_plan_workflow.py').read_text(encoding='utf-8')
    assert "UPDATE project_steps SET owner='apex'" in src
    assert "cur_owner[0].lower() not in NOT_HBS_TO_ASSIGN" in src


def test_shakira_handoff_allows_new_test_files_and_announce_reads_spec_card():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE hb_activity_log(id INTEGER PRIMARY KEY, run_id TEXT, task_id TEXT, kind TEXT, text TEXT)')
    conn.execute('CREATE TABLE hb_task_events(event_id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, payload TEXT)')
    conn.execute("INSERT INTO hb_activity_log(run_id, task_id, kind, text) VALUES ('R-BA-1', 'T-111122223333', 'start', 'BA started')")
    conn.execute("INSERT INTO hb_task_events(task_id, kind, payload) VALUES ('T-111122223333', 'spec_card', ?)", (json.dumps({'ready': True}),))
    assert hb_announce._outcome(conn, 'R-BA-1') == ('done', '')
    hw_src = Path('core/hb_homework.py').read_text(encoding='utf-8')
    assert "all((ROOT / p).is_file() for p in named)" not in hw_src
