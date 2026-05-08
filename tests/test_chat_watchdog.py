"""Tests for chat job watchdog + health snapshot.

Exercises the timeout logic that prevents Thread #2104-style stalls (a chat
job hanging in 'running' for 12+ minutes) and the per-agent latency ring.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_FRONTEND = os.path.join(_ROOT, 'frontend')
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

import frontend.services.chat_jobs as cj


def _suppress_durable_spine_logs(monkeypatch):
    """Synthetic watchdog stalls should not pollute Terminal warning feeds."""
    from core import spine

    real_log = spine.log

    def _log_without_persist(kind, message, **kwargs):
        kwargs['persist'] = False
        return real_log(kind, message, **kwargs)

    monkeypatch.setattr(spine, 'log', _log_without_persist)


def _fresh_state():
    """Reset module-level state so tests don't leak into each other."""
    cj._CHAT_JOBS.clear()
    cj._CHAT_HEALTH_RING.clear()


def test_watchdog_marks_long_running_job_as_stalled(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
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


def test_watchdog_leaves_fresh_job_alone(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
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


def test_watchdog_respects_min_floor_for_fast_agents(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
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


def test_watchdog_caps_at_2000_second_handoff_deadline_with_high_eta(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    now = time.time()
    # Even with a 10-minute ETA, 4× = 40min would be too lenient. The
    # 2000-second handoff ceiling kicks in instead.
    cj._CHAT_JOBS['job-huge-eta'] = {
        'job_id': 'job-huge-eta',
        'agent': 'mistral',
        'status': 'running',
        'eta_seconds': 600,
        'started_ts': now - 2100,
        'updated_ts': now - 2100,
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert len(stalled) == 1


def test_watchdog_uses_idle_time_not_total_runtime(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    now = time.time()
    # Long total runtime is allowed when the model is still streaming progress.
    cj._CHAT_JOBS['job-active'] = {
        'job_id': 'job-active',
        'agent': 'llama',
        'status': 'running',
        'eta_seconds': 60,
        'started_ts': now - 2500,
        'updated_ts': now - 10,
        'stage_trace': [{'text': 'generating · partial answer', 'ts': now - 10}],
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert stalled == []
    assert cj._CHAT_JOBS['job-active']['status'] == 'running'


def test_watchdog_gives_local_jobs_full_handoff_window(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-local-waiting'] = {
        'job_id': 'job-local-waiting',
        'agent': 'gemma',
        'status': 'running',
        'runtime_class': 'local',
        'eta_seconds': 60,
        'started_ts': now - 1000,
        'updated_ts': now - 1000,
        'stage_trace': [{'text': 'sending model request', 'ts': now - 1000}],
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert stalled == []
    assert cj._CHAT_JOBS['job-local-waiting']['status'] == 'running'


def test_health_snapshot_p50_p95_and_stall_count(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
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


def test_health_snapshot_empty_for_unknown_agent(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    snap = cj.get_chat_agent_health_snapshot()
    assert 'nobody' not in snap


def test_status_watchdog_opens_relay_recovery_card(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    from flask import Flask
    from frontend.blueprints import chat as chat_mod

    recovery_calls = []
    with chat_mod._CHAT_JOB_LOCK:
        chat_mod._CHAT_JOBS.clear()

    def _fake_recovery(**kwargs):
        recovery_calls.append(kwargs)
        return {
            'created': True,
            'recovery': {
                'recovery_id': 'recovery-pytest',
                'job_id': kwargs.get('job_id'),
                'stalled_agent': kwargs.get('stalled_agent'),
                'summary': 'pytest recovery opened',
            },
            'message': 'relay recovery card',
        }

    monkeypatch.setattr(chat_mod, 'ensure_chat_relay_recovery', _fake_recovery)
    monkeypatch.setattr(chat_mod, 'get_open_chat_relay_recoveries', lambda *a, **k: [])
    monkeypatch.setattr(chat_mod, 'update_chat_job_db', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, '_chat_try_hard_kill_local_agent', lambda *a, **k: {'ok': True})
    monkeypatch.setattr(chat_mod, '_sse_chat', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, 'log_activity', lambda *a, **k: None)

    now = time.time()
    chat_mod._CHAT_JOBS['job-stuck-relay'] = {
        'job_id': 'job-stuck-relay',
        'conversation_id': 4321,
        'agent': 'qwen',
        'status': 'running',
        'eta_seconds': 60,
        'started_ts': now - 1000,
        'updated_ts': now - 1000,
        'stage_trace': [{'text': 'processing thread hand-off', 'ts': now - 990}],
    }

    app = Flask(__name__)
    app.register_blueprint(chat_mod.chat_bp)
    with app.test_client() as client:
        resp = client.get('/api/chat/jobs/status?conversation_id=4321')
        data = resp.get_json()

    assert resp.status_code == 200
    assert data['ok'] is True
    assert recovery_calls
    assert recovery_calls[0]['job_id'] == 'job-stuck-relay'
    assert recovery_calls[0]['stalled_agent'] == 'qwen'
    assert recovery_calls[0]['stage_trace'][0]['text'] == 'processing thread hand-off'
    assert data['recoveries'][0]['recovery_id'] == 'recovery-pytest'


def test_status_watchdog_opens_silent_thread_recovery_when_no_jobs(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    from flask import Flask
    from frontend.blueprints import chat as chat_mod

    silent_calls = []
    with chat_mod._CHAT_JOB_LOCK:
        chat_mod._CHAT_JOBS.clear()

    def _fake_silent_recovery(conversation_id, reason=''):
        silent_calls.append((conversation_id, reason))
        return {
            'created': True,
            'recovery': {
                'recovery_id': 'recovery-silent-pytest',
                'job_id': 'silent-thread-2576-7508',
                'stalled_agent': 'gemma',
                'summary': 'silent thread recovery opened',
            },
            'message': 'silent recovery card',
        }

    monkeypatch.setattr(chat_mod, 'ensure_silent_chat_thread_recovery', _fake_silent_recovery)
    monkeypatch.setattr(chat_mod, 'get_open_chat_relay_recoveries', lambda *a, **k: [])
    monkeypatch.setattr(chat_mod, 'log_activity', lambda *a, **k: None)

    app = Flask(__name__)
    app.register_blueprint(chat_mod.chat_bp)
    with app.test_client() as client:
        resp = client.get('/api/chat/jobs/status?conversation_id=2576')
        data = resp.get_json()

    assert resp.status_code == 200
    assert data['ok'] is True
    assert silent_calls
    assert silent_calls[0][0] == 2576
    assert data['recoveries'][0]['recovery_id'] == 'recovery-silent-pytest'


def test_relay_recovery_card_is_idempotent_and_contextual(monkeypatch, tmp_path):
    from utils.db import chat as db_chat

    db_path = tmp_path / 'chat-recovery.db'

    def _conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    monkeypatch.setattr(db_chat, 'get_connection', _conn)
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source TEXT DEFAULT 'test',
            sender TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER REFERENCES conversations(id),
            from_agent TEXT NOT NULL,
            to_agent TEXT,
            content TEXT NOT NULL,
            message_type TEXT DEFAULT 'response',
            tokens_used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conv_id = conn.execute(
        "INSERT INTO conversations (title) VALUES ('relay recovery pytest')"
    ).lastrowid
    conn.execute(
        "INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type) VALUES (?, 'user', 'qwen', 'Research this and hand it to Duck.', 'chat')",
        (conv_id,),
    )
    conn.commit()
    conn.close()

    first = db_chat.ensure_chat_relay_recovery(
        'job-idem',
        conv_id,
        'qwen',
        'timeout',
        stage_trace=[{'text': 'processing thread hand-off', 'ts': time.time()}],
    )
    second = db_chat.ensure_chat_relay_recovery(
        'job-idem',
        conv_id,
        'qwen',
        'timeout',
    )

    assert first['created'] is True
    assert second['created'] is False
    assert first['recovery']['stalled_agent'] == 'qwen'
    assert 'Relay Recovery Card' in first['message']
    assert 'Do not expose private chain-of-thought' in first['message']

    conn = _conn()
    try:
        recovery_count = conn.execute('SELECT COUNT(*) FROM chat_relay_recoveries').fetchone()[0]
        card_rows = conn.execute("SELECT content FROM messages WHERE message_type='relay_recovery'").fetchall()
    finally:
        conn.close()
    assert recovery_count == 1
    assert len(card_rows) == 1
    assert 'Research this and hand it to Duck.' in card_rows[0]['content']


def test_relay_recovery_leases_prevent_duplicate_active_reviews(monkeypatch, tmp_path):
    from utils.db import chat as db_chat

    db_path = tmp_path / 'chat-recovery-lease.db'

    def _conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    monkeypatch.setattr(db_chat, 'get_connection', _conn)
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source TEXT DEFAULT 'test',
            sender TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER REFERENCES conversations(id),
            from_agent TEXT NOT NULL,
            to_agent TEXT,
            content TEXT NOT NULL,
            message_type TEXT DEFAULT 'response',
            tokens_used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conv_id = conn.execute("INSERT INTO conversations (title) VALUES ('lease pytest')").lastrowid
    conn.commit()
    conn.close()

    created = db_chat.ensure_chat_relay_recovery('job-lease', conv_id, 'qwen', 'timeout')
    recovery_id = created['recovery']['recovery_id']

    first_claim = db_chat.lease_chat_relay_recoveries('tasker-a', limit=1, lease_seconds=300)
    second_claim = db_chat.lease_chat_relay_recoveries('tasker-b', limit=1, lease_seconds=300)

    assert [r['recovery_id'] for r in first_claim] == [recovery_id]
    assert first_claim[0]['lease_owner'] == 'tasker-a'
    assert second_claim == []

    assert db_chat.update_chat_relay_recovery_status(recovery_id, 'reviewed', 'pytest handled') is True
    assert db_chat.get_open_chat_relay_recoveries(limit=5) == []


def test_relay_recovery_status_endpoint_updates_card(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from flask import Flask
    from frontend.blueprints import chat as chat_mod

    calls = []
    monkeypatch.setattr(
        chat_mod,
        'update_chat_relay_recovery_status',
        lambda rid, status, summary=None: calls.append((rid, status, summary)) or True,
    )
    monkeypatch.setattr(chat_mod, 'log_activity', lambda *a, **k: None)

    app = Flask(__name__)
    app.register_blueprint(chat_mod.chat_bp)
    with app.test_client() as client:
        resp = client.post(
            '/api/chat/recoveries/recovery-123/status',
            json={'status': 'ignored', 'summary': 'dismissed in pytest', 'actor': 'pytest'},
        )

    data = resp.get_json()
    assert resp.status_code == 200
    assert data['ok'] is True
    assert calls == [('recovery-123', 'ignored', 'dismissed in pytest')]


def test_project_context_block_adds_studio_project_pack(monkeypatch):
    from core.knowledge import projects as kc_projects
    from frontend.blueprints import chat as chat_mod

    def fake_get_project(project_id):
        assert project_id == 'P-BD5B54E749'
        return {
            'project': {
                'project_id': project_id,
                'name': 'Integration Improvement Audit 2026-04-28',
                'description': 'Keep agents aligned on integration repair work.',
                'status': 'active',
                'methodology': 'mixed',
            },
            'steps': [
                {'title': '108. Done: persist relay recovery cards', 'status': 'done'},
                {'title': '115. Add project context packs for coding and research agents', 'status': 'doing'},
            ],
            'test_cases': [
                {'title': 'Relay recovery backend compile check', 'status': 'passed', 'script_id': 'python3 -m py_compile frontend/blueprints/chat.py'},
            ],
            'blackboard_notes': [
                {'author': 'duck', 'kind': 'risk', 'content': 'Watch for duplicate recovery reviews before active sweeps.'},
            ],
        }

    monkeypatch.setattr(kc_projects, 'get_project', fake_get_project)
    monkeypatch.setattr(chat_mod, '_project_context_doc_rows', lambda *a, **k: [
        {'doc_name': 'Agent Relay Recovery Upgrade', 'content': 'Recovery cards and Tasker sweeps keep dropped work visible.'}
    ])

    block = chat_mod._build_project_context_block('Continue P-BD5B54E749 please')

    assert 'Studio project context' in block
    assert 'Integration Improvement Audit 2026-04-28' in block
    assert 'Add project context packs for coding and research agents' in block
    assert 'Relay recovery backend compile check' in block
    assert 'Watch for duplicate recovery reviews' in block
    assert 'Agent Relay Recovery Upgrade' in block
