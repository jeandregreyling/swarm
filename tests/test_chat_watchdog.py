"""Tests for chat job watchdog + health snapshot.

Exercises the timeout logic that prevents Thread #2104-style stalls (a chat
job hanging in 'running' for 12+ minutes) and the per-agent latency ring.
"""
from __future__ import annotations

import time

import frontend.services.chat_jobs as cj


def _fresh_state():
    """Reset module-level state so tests don't leak into each other."""
    cj._CHAT_JOBS.clear()
    cj._CHAT_HEALTH_RING.clear()


def test_watchdog_marks_long_running_job_as_stalled():
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-stuck'] = {
        'job_id': 'job-stuck',
        'agent': 'gemma',
        'status': 'running',
        'eta_seconds': 60,
        'started_ts': now - 1000,   # well past 4×ETA + 5min floor
        'updated_ts': now - 1000,
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert len(stalled) == 1
    assert stalled[0]['agent'] == 'gemma'
    assert cj._CHAT_JOBS['job-stuck']['status'] == 'failed'
    assert cj._CHAT_JOBS['job-stuck']['stage'] == 'stalled'
    assert cj._CHAT_JOBS['job-stuck']['stalled'] is True
    assert 'Watchdog' in cj._CHAT_JOBS['job-stuck']['error']


def test_watchdog_leaves_fresh_job_alone():
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-fresh'] = {
        'job_id': 'job-fresh',
        'agent': 'gemma',
        'status': 'running',
        'eta_seconds': 60,
        'started_ts': now - 5,   # 5 seconds in
        'updated_ts': now - 5,
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert stalled == []
    assert cj._CHAT_JOBS['job-fresh']['status'] == 'running'


def test_watchdog_respects_min_floor_for_fast_agents():
    _fresh_state()
    now = time.time()
    # Tiny ETA but only 2min elapsed → still under the 5min floor.
    cj._CHAT_JOBS['job-fast'] = {
        'job_id': 'job-fast',
        'agent': 'duck',
        'status': 'running',
        'eta_seconds': 5,
        'started_ts': now - 120,
        'updated_ts': now - 120,
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert stalled == []


def test_watchdog_caps_at_15_minutes_even_with_high_eta():
    _fresh_state()
    now = time.time()
    # Even with a 10-minute ETA, 4× = 40min would be too lenient. The
    # 15-minute hard ceiling kicks in instead.
    cj._CHAT_JOBS['job-huge-eta'] = {
        'job_id': 'job-huge-eta',
        'agent': 'mistral',
        'status': 'running',
        'eta_seconds': 600,
        'started_ts': now - 1000,   # 16+ minutes
        'updated_ts': now - 1000,
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert len(stalled) == 1


def test_health_snapshot_p50_p95_and_stall_count():
    _fresh_state()
    base = time.time()
    # Three completed jobs: 1s, 2s, 10s.
    for elapsed_s, jid in [(1, 'a'), (2, 'b'), (10, 'c')]:
        job = {
            'job_id': jid,
            'agent': 'gemma',
            'status': 'completed',
            'started_ts': base - elapsed_s,
            'updated_ts': base,
        }
        cj._CHAT_JOBS[jid] = job
        with cj._CHAT_JOB_LOCK:
            cj._record_job_health_locked(job)
    # Plus one stall.
    stall_job = {
        'job_id': 'd', 'agent': 'gemma',
        'status': 'failed', 'stalled': True,
        'started_ts': base - 1000, 'updated_ts': base,
    }
    cj._CHAT_JOBS['d'] = stall_job
    with cj._CHAT_JOB_LOCK:
        cj._record_job_health_locked(stall_job)

    snap = cj.get_chat_agent_health_snapshot()
    g = snap['gemma']
    assert g['count'] == 4
    assert g['completed'] == 3
    assert g['failed'] == 1
    assert g['stalled'] == 1
    # p50 over [1000, 2000, 10000] → middle = 2000ms
    assert g['p50_ms'] == 2000
    # p95 over the same → 10000ms (top of range)
    assert g['p95_ms'] == 10000


def test_health_snapshot_empty_for_unknown_agent():
    _fresh_state()
    snap = cj.get_chat_agent_health_snapshot()
    assert 'nobody' not in snap
