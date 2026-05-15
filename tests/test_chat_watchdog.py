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


def test_watchdog_enforces_gateway_absolute_cap_despite_progress(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-gateway-cap'] = {
        'job_id': 'job-gateway-cap',
        'agent': 'gemma',
        'status': 'running',
        'runtime_class': 'local',
        'eta_seconds': 85,
        'started_ts': now - 610,
        'updated_ts': now - 5,
        'stage_trace': [
            {'text': 'gateway: dispatch (absolute=600s idle=240s)', 'ts': now - 610},
            {'text': 'generating · still streaming', 'ts': now - 5},
        ],
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert len(stalled) == 1
    assert cj._CHAT_JOBS['job-gateway-cap']['status'] == 'failed'
    assert 'absolute cap' in cj._CHAT_JOBS['job-gateway-cap']['error']


def test_watchdog_enforces_gateway_idle_cap_for_silent_dispatch(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-gateway-idle'] = {
        'job_id': 'job-gateway-idle',
        'agent': 'mistral',
        'status': 'running',
        'runtime_class': 'local',
        'eta_seconds': 90,
        'started_ts': now - 260,
        'updated_ts': now - 250,
        'stage_trace': [
            {'text': 'gateway: dispatch (absolute=600s idle=240s)', 'ts': now - 250},
        ],
    }
    with cj._CHAT_JOB_LOCK:
        stalled = cj._watchdog_mark_stalled_jobs_locked()
    assert len(stalled) == 1
    assert cj._CHAT_JOBS['job-gateway-idle']['status'] == 'failed'
    assert 'idle cap' in cj._CHAT_JOBS['job-gateway-idle']['error']


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
    monkeypatch.setattr(chat_mod, '_trace', lambda *a, **k: None)
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


def test_status_reconciles_unowned_runners_while_job_is_running(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    from flask import Flask
    from frontend.blueprints import chat as chat_mod

    reconcile_calls = []
    with chat_mod._CHAT_JOB_LOCK:
        chat_mod._CHAT_JOBS.clear()
        now = time.time()
        chat_mod._CHAT_JOBS['job-qwen-live'] = {
            'job_id': 'job-qwen-live',
            'conversation_id': 4322,
            'agent': 'qwen',
            'status': 'running',
            'runtime_class': 'local',
            'eta_seconds': 120,
            'started_ts': now,
            'updated_ts': now,
            'stage': 'gateway: dispatch (absolute=2000s idle=900s)',
            'stage_trace': [],
        }

    monkeypatch.setattr(chat_mod, '_chat_reconcile_unowned_ollama_runners', lambda conv_id: reconcile_calls.append(conv_id) or [])
    monkeypatch.setattr(chat_mod, 'get_open_chat_relay_recoveries', lambda *a, **k: [])

    app = Flask(__name__)
    app.register_blueprint(chat_mod.chat_bp)
    with app.test_client() as client:
        resp = client.get('/api/chat/jobs/status?conversation_id=4322')
        data = resp.get_json()

    assert resp.status_code == 200
    assert data['ok'] is True
    assert data['jobs'][0]['status'] == 'running'
    assert reconcile_calls == [4322]


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


def test_status_watchdog_recovers_db_running_job_missing_from_runtime(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    from flask import Flask
    from frontend.blueprints import chat as chat_mod

    updated = []
    recovery_calls = []
    timeline_calls = []
    with chat_mod._CHAT_JOB_LOCK:
        chat_mod._CHAT_JOBS.clear()

    def _fake_recovery(**kwargs):
        recovery_calls.append(kwargs)
        return {
            'created': True,
            'recovery': {
                'recovery_id': 'recovery-orphan-pytest',
                'job_id': kwargs.get('job_id'),
                'stalled_agent': kwargs.get('stalled_agent'),
                'summary': 'orphan recovery opened',
            },
            'message': 'orphan recovery card',
        }

    monkeypatch.setattr(chat_mod, 'get_chat_jobs_by_ids', lambda ids: [{
        'job_id': 'job-db-orphan',
        'conversation_id': 2577,
        'agent': 'gemma',
        'status': 'running',
        'runtime_class': 'local',
        'stage': '',
        'eta_seconds': 85,
        'elapsed_ms': 0,
        'error': '',
        'stage_trace_json': '[]',
        'started_at': '2026-05-08T05:28:01Z',
        'updated_at': '2026-05-08T05:28:01Z',
    }])
    monkeypatch.setattr(chat_mod, 'update_chat_job_db', lambda *a, **k: updated.append((a, k)))
    monkeypatch.setattr(chat_mod, 'ensure_chat_relay_recovery', _fake_recovery)
    monkeypatch.setattr(chat_mod, 'ensure_silent_chat_thread_recovery', lambda *a, **k: {'created': False, 'recovery': None})
    monkeypatch.setattr(chat_mod, 'get_open_chat_relay_recoveries', lambda *a, **k: [])
    monkeypatch.setattr(chat_mod, '_chat_try_hard_kill_local_agent', lambda *a, **k: {'ok': True})
    monkeypatch.setattr(chat_mod, '_trace', lambda *a, **k: timeline_calls.append((a, k)))
    monkeypatch.setattr(chat_mod, 'log_activity', lambda *a, **k: None)

    app = Flask(__name__)
    app.register_blueprint(chat_mod.chat_bp)
    with app.test_client() as client:
        resp = client.get('/api/chat/jobs/status?conversation_id=2577&job_ids=job-db-orphan')
        data = resp.get_json()

    assert resp.status_code == 200
    assert data['ok'] is True
    assert data['jobs'][0]['status'] == 'failed'
    assert data['jobs'][0]['stage'] == 'stalled'
    assert 'missing from the live runtime' in data['jobs'][0]['error']
    assert updated
    assert recovery_calls
    assert recovery_calls[0]['job_id'] == 'job-db-orphan'
    assert recovery_calls[0]['stage_trace'][-2]['text'] == 'orphaned runtime job (watchdog)'
    assert recovery_calls[0]['stage_trace'][-1]['text'].startswith('ollama stop')
    assert timeline_calls
    assert timeline_calls[0][0][2] == 'ollama_control'
    assert data['recoveries'][0]['recovery_id'] == 'recovery-orphan-pytest'


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
        project = conn.execute("SELECT name FROM projects WHERE project_id='P-CHAT-RELAY-RECOVERY'").fetchone()
        step = conn.execute(
            "SELECT title, status, owner, owner_route FROM project_steps "
            "WHERE project_id='P-CHAT-RELAY-RECOVERY'"
        ).fetchone()
    finally:
        conn.close()
    assert recovery_count == 1
    assert len(card_rows) == 1
    assert 'Research this and hand it to Duck.' in card_rows[0]['content']
    assert project['name'] == 'Chat Relay Recovery Watchdog'
    assert 'Recover chat thread' in step['title']
    assert step['status'] == 'todo'
    assert step['owner'] == 'qwen'
    assert step['owner_route'].startswith('watchdog:recovery-')


def test_startup_orphan_sweep_creates_recovery_card(monkeypatch, tmp_path):
    from utils.db import chat as db_chat

    db_path = tmp_path / 'chat-startup-orphan.db'

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
        CREATE TABLE chat_jobs (
            job_id TEXT PRIMARY KEY,
            conversation_id INTEGER,
            agent TEXT,
            status TEXT,
            runtime_class TEXT,
            eta_seconds INTEGER,
            started_at TEXT,
            updated_at TEXT,
            stage TEXT,
            error TEXT,
            elapsed_ms INTEGER,
            tokens INTEGER DEFAULT 0,
            stage_trace_json TEXT DEFAULT '[]'
        );
        """
    )
    conv_id = conn.execute("INSERT INTO conversations (title) VALUES ('orphan startup')").lastrowid
    conn.execute(
        "INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type) VALUES (?, 'user', 'gemma', 'Status update', 'chat')",
        (conv_id,),
    )
    conn.execute(
        """INSERT INTO chat_jobs
           (job_id, conversation_id, agent, status, runtime_class, eta_seconds, started_at, updated_at, stage, error, elapsed_ms)
           VALUES ('job-startup-orphan', ?, 'gemma', 'running', 'local', 85,
                   '2026-05-08T05:28:01Z', '2026-05-08T05:28:01Z', '', '', 0)""",
        (conv_id,),
    )
    conn.commit()
    conn.close()

    db_chat.mark_orphaned_chat_jobs()

    conn = _conn()
    try:
        job = conn.execute("SELECT status, stage, error FROM chat_jobs WHERE job_id='job-startup-orphan'").fetchone()
        recovery = conn.execute("SELECT job_id, stalled_agent, status FROM chat_relay_recoveries").fetchone()
        card = conn.execute("SELECT content FROM messages WHERE message_type='relay_recovery'").fetchone()
    finally:
        conn.close()

    assert job['status'] == 'failed'
    assert job['stage'] == 'failed'
    assert 'server restarted' in job['error']
    assert recovery['job_id'] == 'job-startup-orphan'
    assert recovery['stalled_agent'] == 'gemma'
    assert recovery['status'] == 'open'
    assert 'server restarted - runtime job was orphaned' in card['content']


def test_sweep_stuck_jobs_recovers_no_progress_followup(monkeypatch, tmp_path):
    from utils.db import chat as db_chat

    db_path = tmp_path / 'chat-no-progress.db'

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
        CREATE TABLE chat_jobs (
            job_id TEXT PRIMARY KEY,
            conversation_id INTEGER,
            agent TEXT,
            status TEXT,
            runtime_class TEXT,
            eta_seconds INTEGER,
            started_at TEXT,
            updated_at TEXT,
            stage TEXT,
            error TEXT,
            elapsed_ms INTEGER,
            tokens INTEGER DEFAULT 0,
            stage_trace_json TEXT DEFAULT '[]'
        );
        """
    )
    conv_id = conn.execute("INSERT INTO conversations (title) VALUES ('thread 2583 shape')").lastrowid
    conn.execute(
        "INSERT INTO messages (conversation_id, from_agent, to_agent, content, message_type) VALUES (?, 'user', 'sniffles', 'pick three items you want to fix', 'chat')",
        (conv_id,),
    )
    conn.execute(
        """INSERT INTO chat_jobs
           (job_id, conversation_id, agent, status, runtime_class, eta_seconds,
            started_at, updated_at, stage, error, elapsed_ms, stage_trace_json)
           VALUES ('job-no-progress', ?, 'sniffles', 'running', 'local', 180,
                   datetime('now', '-6 minutes'), datetime('now', '-6 minutes'),
                   '', '', 0, '[]')""",
        (conv_id,),
    )
    conn.commit()
    conn.close()

    swept = db_chat.sweep_stuck_jobs(max_age_minutes=120, no_progress_age_minutes=5, conversation_id=conv_id)

    conn = _conn()
    try:
        job = conn.execute("SELECT status, stage, error, stage_trace_json FROM chat_jobs WHERE job_id='job-no-progress'").fetchone()
        recovery = conn.execute("SELECT job_id, stalled_agent, status FROM chat_relay_recoveries").fetchone()
        card = conn.execute("SELECT content FROM messages WHERE message_type='relay_recovery'").fetchone()
    finally:
        conn.close()

    assert swept == 1
    assert job['status'] == 'failed'
    assert job['stage'] == 'failed'
    assert 'no-progress job swept' in job['error']
    assert 'no progress recorded before watchdog sweep' in job['stage_trace_json']
    assert recovery['job_id'] == 'job-no-progress'
    assert recovery['stalled_agent'] == 'sniffles'
    assert recovery['status'] == 'open'
    assert 'pick three items you want to fix' in card['content']


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

    conn = _conn()
    try:
        step = conn.execute(
            "SELECT status FROM project_steps WHERE project_id='P-CHAT-RELAY-RECOVERY'"
        ).fetchone()
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM project_step_evidence WHERE project_id='P-CHAT-RELAY-RECOVERY'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert step['status'] == 'done'
    assert evidence_count >= 3


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


def test_watchdog_reconciles_unowned_ollama_runner(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    stop_calls = []
    trace_calls = []
    monkeypatch.setattr(chat_mod, '_chat_active_local_agents_from_db', lambda: set())
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: ['gemma3:latest'])
    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'gemma3:latest')
    monkeypatch.setattr(
        chat_mod,
        '_chat_try_hard_kill_local_agent',
        lambda agent: stop_calls.append(agent) or {
            'agent': agent,
            'ok': True,
            'detail': 'stopped gemma3:latest',
            'configured_model': 'gemma3:latest',
            'models': ['gemma3:latest'],
            'before_models': ['gemma3:latest'],
            'after_models': [],
        },
    )
    monkeypatch.setattr(chat_mod, '_chat_log_watchdog_ollama_event', lambda *a, **k: trace_calls.append((a, k)))

    result = chat_mod._chat_reconcile_unowned_ollama_runners(2577)

    assert stop_calls == ['gemma']
    assert result and result[0]['ok'] is True
    assert trace_calls
    assert trace_calls[0][0][3] == 'watchdog_unowned_runner_stop'


def test_watchdog_escalates_when_ollama_stop_leaves_single_runner(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    calls = {'ps': 0, 'cmds': [], 'pkilled': False}
    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'gemma3:latest')
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda name: {str(name or '').lower()})

    def _running_models():
        calls['ps'] += 1
        return [] if calls['pkilled'] else ['gemma3:latest']

    class _Proc:
        def __init__(self, returncode=0, stdout='', stderr=''):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _run(cmd, **kwargs):
        calls['cmds'].append(cmd)
        if cmd[:3] == ['pkill', '-f', 'ollama runner --model']:
            calls['pkilled'] = True
        return _Proc(0)

    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', _running_models)
    monkeypatch.setattr(chat_mod.subprocess, 'run', _run)
    monkeypatch.setattr(chat_mod.time, 'sleep', lambda *_: None)

    result = chat_mod._chat_try_hard_kill_local_agent('gemma')

    assert result['ok'] is True
    assert ['ollama', 'stop', 'gemma3:latest'] in calls['cmds']
    assert ['pkill', '-f', 'ollama runner --model'] in calls['cmds']
    assert result['after_models'] == []


def test_watchdog_waits_for_ollama_stop_to_settle(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    calls = {'ps': 0, 'cmds': []}
    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'qwen2.5:latest')
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda name: {str(name or '').lower()})

    def _running_models():
        calls['ps'] += 1
        return ['qwen2.5:latest'] if calls['ps'] <= 2 else []

    class _Proc:
        returncode = 0
        stdout = ''
        stderr = ''

    def _run(cmd, **kwargs):
        calls['cmds'].append(cmd)
        return _Proc()

    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', _running_models)
    monkeypatch.setattr(chat_mod.subprocess, 'run', _run)
    monkeypatch.setattr(chat_mod.time, 'sleep', lambda *_: None)

    result = chat_mod._chat_try_hard_kill_local_agent('qwen')

    assert result['ok'] is True
    assert ['ollama', 'stop', 'qwen2.5:latest'] in calls['cmds']
    assert ['pkill', '-f', 'ollama runner --model'] not in calls['cmds']
    assert result['after_models'] == []


def test_watchdog_does_not_stop_owned_ollama_runner(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    stop_calls = []
    monkeypatch.setattr(chat_mod, '_chat_active_local_agents_from_db', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: ['gemma3:latest'])
    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'gemma'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'gemma3:latest')
    monkeypatch.setattr(chat_mod, '_chat_try_hard_kill_local_agent', lambda agent: stop_calls.append(agent))

    assert chat_mod._chat_reconcile_unowned_ollama_runners(2577) == []
    assert stop_calls == []


def test_watchdog_reconciles_shared_utility_ollama_runner(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    stop_calls = []
    monkeypatch.setattr(chat_mod, '_chat_active_local_agents_from_db', lambda: set())
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: ['qwen:latest'])
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'librarian'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'qwen:latest')
    monkeypatch.setattr(
        chat_mod,
        '_chat_try_hard_kill_local_agent',
        lambda agent: stop_calls.append(agent) or {
            'agent': agent,
            'ok': True,
            'detail': 'stopped qwen:latest',
            'configured_model': 'qwen:latest',
            'models': ['qwen:latest'],
            'before_models': ['qwen:latest'],
            'after_models': [],
        },
    )
    monkeypatch.setattr(chat_mod, '_chat_log_watchdog_ollama_event', lambda *a, **k: None)

    result = chat_mod._chat_reconcile_unowned_ollama_runners(2822)

    assert stop_calls == ['librarian']
    assert result and result[0]['ok'] is True


def test_watchdog_treats_placeholder_answer_as_unusable():
    from frontend.blueprints import chat as chat_mod

    assert chat_mod._chat_response_is_unusable('gemma', '[gemma unavailable]') is True
    assert chat_mod._chat_response_is_unusable('gemma', '[gemma] no response') is True
    assert chat_mod._chat_response_is_unusable('mistral', '[mistral] No response - check server logs.') is True
    assert chat_mod._chat_response_is_unusable('gemma', 'Here is the actual status update.') is False


def test_timeout_self_handoff_is_not_successful_completion():
    from frontend.blueprints import chat as chat_mod

    text = (
        '[twenty] reached the handoff deadline after 251s while still showing active progress.\n\n'
        'SELF-HANDOFF:\n'
        '- Current status: deadline 240s reached with heartbeat idle 239s.\n'
    )

    assert chat_mod._chat_response_is_timeout_handoff(text, 0) is True
    assert chat_mod._chat_response_is_timeout_handoff(text, 42) is False
    assert chat_mod._chat_response_is_timeout_handoff('Finished the proposal.', 0) is False


def test_twenty_persistent_mode_uses_local_handoff_window():
    from frontend.blueprints import chat as chat_mod

    assert chat_mod._chat_agent_timeout_seconds('twenty', persistent_mode=True) == 2000
    assert chat_mod._chat_agent_timeout_seconds('twenty', persistent_mode=False) == 12


def test_chat_routes_explicit_agent_mentions_before_defaulting_to_nine(monkeypatch):
    from frontend.blueprints import chat as chat_mod

    monkeypatch.setattr(chat_mod, '_get_agent_labels', lambda: {'gemma': 'Gemma', 'nine': 'Nine'})

    assert chat_mod._chat_extract_explicit_agent_mentions(
        'Gemma give me a status update',
        {'gemma', 'nine'},
    ) == ['gemma']


def test_watchdog_marks_status_prompts_read_only():
    from frontend.blueprints import chat as chat_mod

    assert chat_mod._chat_user_prompt_is_informational('Gemma give me a status update') is True
    assert chat_mod._chat_user_prompt_is_informational('update the watchdog code to stop Ollama') is False
    assert chat_mod._chat_prompt_needs_clarification('status update') is True


def test_duck_rejects_status_only_work_proposals():
    from utils import proposal_review

    verdict, note = proposal_review._duck_verdict(
        'Status Update',
        'Provide current status for the user with queue and proposal counts.',
        'nine',
    )

    assert verdict == 'rejected'
    assert 'informational/status request' in note


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


def test_watchdog_circuit_breaker_state_initializes_and_resets(monkeypatch):
    from frontend.blueprints import chat as chat_mod

    with chat_mod._WATCHDOG_KILL_LOCK:
        chat_mod._WATCHDOG_KILL_STATE.clear()

    state = chat_mod._watchdog_get_kill_state('qwen2.5:latest')
    assert state['consecutive_failures'] == 0
    assert state['escalation_level'] == 0
    assert state['ticket_emitted'] is False

    state['consecutive_failures'] = 5
    chat_mod._watchdog_reset_kill_state('qwen2.5:latest')

    with chat_mod._WATCHDOG_KILL_LOCK:
        assert 'qwen2.5:latest' not in chat_mod._WATCHDOG_KILL_STATE


def test_watchdog_backoff_respects_exponential_delays(monkeypatch):
    from frontend.blueprints import chat as chat_mod

    base = 5
    state = {'consecutive_failures': 0, 'last_attempt_ts': 0.0}
    assert chat_mod._watchdog_backoff_ok(state) is True

    now = time.time()
    state = {'consecutive_failures': 1, 'last_attempt_ts': now}
    assert chat_mod._watchdog_backoff_ok(state) is False
    state['last_attempt_ts'] = now - base
    assert chat_mod._watchdog_backoff_ok(state) is True

    state = {'consecutive_failures': 3, 'last_attempt_ts': now}
    assert chat_mod._watchdog_backoff_ok(state) is False
    state['last_attempt_ts'] = now - (base * 4)
    assert chat_mod._watchdog_backoff_ok(state) is True

    state = {'consecutive_failures': 5, 'last_attempt_ts': now}
    assert chat_mod._watchdog_backoff_ok(state) is False
    state['last_attempt_ts'] = now - (base * 16)
    assert chat_mod._watchdog_backoff_ok(state) is True


def test_watchdog_escalates_to_kill9_after_three_failures(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    with chat_mod._WATCHDOG_KILL_LOCK:
        chat_mod._WATCHDOG_KILL_STATE.clear()

    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'qwen2.5:latest')
    restarted = {'done': False}
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: [] if restarted['done'] else ['qwen2.5:latest'])
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})

    stop_calls = []

    def _failing_stop(model_name):
        stop_calls.append(model_name)
        return {'ok': False, 'detail': 'mock stop failed'}

    monkeypatch.setattr(chat_mod, '_watchdog_kill_ollama_runner_pid', _failing_stop)

    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['consecutive_failures'] = 3
    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['last_attempt_ts'] = 0.0

    result = chat_mod._chat_try_hard_kill_local_agent('qwen')
    assert result['ok'] is False
    assert any(a['action'] == 'kill-9' for a in result['attempts'])
    assert stop_calls[0] == 'qwen2.5:latest'


def test_watchdog_kill9_resolves_runner_by_model_digest(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    cmds = []
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_model_info', lambda: [{
        'model': 'Qwen2.5:latest',
        'digest': 'abc123',
    }])
    monkeypatch.setattr(chat_mod, '_chat_ollama_model_blob_patterns', lambda model: ['sha256-layer456'])

    class _Proc:
        def __init__(self, returncode=0, stdout='', stderr=''):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[:2] == ['pgrep', '-f'] and 'sha256-layer456' in cmd[2]:
            return _Proc(0, '4242\n')
        if cmd[:2] == ['pgrep', '-f']:
            return _Proc(1, '')
        return _Proc(0, '')

    monkeypatch.setattr(chat_mod.subprocess, 'run', _run)
    monkeypatch.setattr(
        'builtins.open',
        lambda path, mode='r', *a, **k: type(
            '_F',
            (),
            {'read': lambda self: b'/usr/local/bin/ollama runner --model sha256-layer456'},
        )(),
    )

    result = chat_mod._watchdog_kill_ollama_runner_pid('Qwen2.5:latest')

    assert result['ok'] is True
    assert result['pid'] == '4242'
    assert ['kill', '-9', '4242'] in cmds


def test_watchdog_kill9_uses_sudo_when_runner_user_differs(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    cmds = []
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_model_info', lambda: [{'model': 'Qwen2.5:latest'}])
    monkeypatch.setattr(chat_mod, '_chat_ollama_model_blob_patterns', lambda model: ['sha256-layer456'])
    monkeypatch.setattr(chat_mod.os.path, 'exists', lambda path: False)
    monkeypatch.setattr(
        'builtins.open',
        lambda path, mode='r', *a, **k: type(
            '_F',
            (),
            {'read': lambda self: b'/usr/local/bin/ollama runner --model sha256-layer456'},
        )(),
    )

    class _Proc:
        def __init__(self, returncode=0, stdout='', stderr=''):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _run(cmd, **kwargs):
        cmds.append(cmd)
        if cmd[:2] == ['pgrep', '-f']:
            return _Proc(0, '4242\n')
        if cmd[:3] == ['kill', '-9', '4242']:
            return _Proc(1, stderr='Operation not permitted')
        return _Proc(0)

    monkeypatch.setattr(chat_mod.subprocess, 'run', _run)

    result = chat_mod._watchdog_kill_ollama_runner_pid('Qwen2.5:latest')

    assert result['ok'] is True
    assert ['sudo', '-n', 'kill', '-9', '4242'] in cmds


def test_watchdog_emits_ticket_once_after_five_failures(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod
    from core import spine

    with chat_mod._WATCHDOG_KILL_LOCK:
        chat_mod._WATCHDOG_KILL_STATE.clear()

    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'qwen2.5:latest')
    restarted = {'done': False}
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: [] if restarted['done'] else ['qwen2.5:latest'])
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})

    tickets = []
    real_log = spine.log

    def _capture_ticket(kind, message, **kwargs):
        if kind == spine.EventKind.TICKET:
            tickets.append({'message': message, 'payload': kwargs.get('payload')})
        kwargs['persist'] = False
        return real_log(kind, message, **kwargs)

    monkeypatch.setattr(spine, 'log', _capture_ticket)

    def _failing_kill9(model_name):
        return {'ok': False, 'detail': 'mock kill-9 failed'}

    monkeypatch.setattr(chat_mod, '_watchdog_kill_ollama_runner_pid', _failing_kill9)

    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['consecutive_failures'] = 5
    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['last_attempt_ts'] = 0.0

    result = chat_mod._chat_try_hard_kill_local_agent('qwen')
    assert result['ok'] is False
    assert len(tickets) == 1
    assert 'kill-9 both failed' in tickets[0]['message']
    assert tickets[0]['payload']['escalation_level'] == 3

    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['last_attempt_ts'] = 0.0
    tickets.clear()
    result2 = chat_mod._chat_try_hard_kill_local_agent('qwen')
    assert len(tickets) == 0
    assert result2['attempts'][0]['action'] == 'kill-9'


def test_watchdog_restarts_ollama_when_kill9_fails_and_no_active_jobs(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    with chat_mod._WATCHDOG_KILL_LOCK:
        chat_mod._WATCHDOG_KILL_STATE.clear()

    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'qwen2.5:latest')
    restarted = {'done': False}
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: [] if restarted['done'] else ['qwen2.5:latest'])
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})
    monkeypatch.setattr(chat_mod, '_chat_active_local_agents_from_db', lambda: set())
    monkeypatch.setattr(chat_mod, '_watchdog_kill_ollama_runner_pid', lambda model: {'ok': False, 'detail': 'permission denied'})
    def _restart(model):
        restarted['done'] = True
        return {
            'ok': True,
            'detail': 'ollama service restarted',
            'action': 'systemctl-restart-ollama',
        }

    monkeypatch.setattr(chat_mod, '_watchdog_restart_ollama_service', _restart)

    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['consecutive_failures'] = 3
    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['last_attempt_ts'] = 0.0

    result = chat_mod._chat_try_hard_kill_local_agent('qwen')

    assert result['ok'] is True
    assert any(a['action'] == 'kill-9' for a in result['attempts'])
    assert any(a['action'] == 'systemctl-restart-ollama' for a in result['attempts'])


def test_runtime_stop_ignores_current_job_for_restart_escalation(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    calls = {'ignore_job_id': None}
    monkeypatch.setattr(chat_mod, 'update_chat_job_db', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, '_chat_log_watchdog_ollama_event', lambda *a, **k: None)

    def _fake_kill(agent, *, ignore_job_id=None):
        calls['ignore_job_id'] = ignore_job_id
        return {
            'agent': agent,
            'ok': True,
            'detail': 'ollama service restarted',
            'before_models': ['Qwen3.6:latest'],
            'after_models': [],
            'models': ['Qwen3.6:latest'],
        }

    monkeypatch.setattr(chat_mod, '_chat_try_hard_kill_local_agent', _fake_kill)

    result, trace, error = chat_mod._chat_apply_runtime_stop_to_job(
        'job-current',
        'twenty',
        'stalled',
        stage_trace=[{'text': 'stalled (watchdog)', 'ts': 1.0}],
        conversation_id=2831,
    )

    assert calls['ignore_job_id'] == 'job-current'
    assert result['ok'] is True
    assert trace[-1]['text'].startswith('ollama stop ok')
    assert 'ollama service restarted' in error


def test_cancel_passes_job_id_to_local_cleanup(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    _fresh_state()
    from flask import Flask
    from frontend.blueprints import chat as chat_mod

    now = time.time()
    with chat_mod._CHAT_JOB_LOCK:
        chat_mod._CHAT_JOBS.clear()
        chat_mod._CHAT_JOBS['job-cancel-mistral'] = {
            'job_id': 'job-cancel-mistral',
            'conversation_id': 2832,
            'agent': 'mistral',
            'status': 'running',
            'runtime_class': 'local',
            'eta_seconds': 90,
            'started_ts': now - 120,
            'updated_ts': now,
            'stage': 'gateway: dispatch (absolute=2000s idle=900s)',
            'stage_trace': [],
        }

    calls = []
    delayed = []
    monkeypatch.setattr(chat_mod, 'update_chat_job_db', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, '_chat_log_watchdog_ollama_event', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, 'log_activity', lambda *a, **k: None)
    monkeypatch.setattr(
        chat_mod,
        '_chat_schedule_delayed_runtime_cleanup',
        lambda agent, job_id=None, delay_seconds=30: delayed.append((agent, job_id, delay_seconds)) or True,
    )

    def _fake_kill(agent, *, ignore_job_id=None):
        calls.append((agent, ignore_job_id))
        return {
            'agent': agent,
            'ok': True,
            'detail': 'stopped Mistral:latest',
            'before_models': ['Mistral:latest'],
            'after_models': [],
            'models': ['Mistral:latest'],
        }

    monkeypatch.setattr(chat_mod, '_chat_try_hard_kill_local_agent', _fake_kill)

    app = Flask(__name__)
    app.register_blueprint(chat_mod.chat_bp)
    with app.test_client() as client:
        resp = client.post('/api/chat/jobs/cancel', json={
            'conversation_id': 2832,
            'job_ids': ['job-cancel-mistral'],
            'hard_kill': True,
        })
        data = resp.get_json()

    assert resp.status_code == 200
    assert data['ok'] is True
    assert calls == [('mistral', 'job-cancel-mistral')]
    assert delayed == [('mistral', 'job-cancel-mistral', 30)]
    assert data['cancelled'][0]['job_id'] == 'job-cancel-mistral'


def test_watchdog_immediate_escalates_after_successful_stop_still_running(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    with chat_mod._WATCHDOG_KILL_LOCK:
        chat_mod._WATCHDOG_KILL_STATE.clear()

    restarted = {'done': False}
    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'eight'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'eight'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'gemma4:26b')
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: [] if restarted['done'] else ['gemma4:26b'])
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})
    monkeypatch.setattr(chat_mod, '_chat_active_local_agents_from_db', lambda: set())
    monkeypatch.setattr(chat_mod.time, 'sleep', lambda *_: None)

    class _Proc:
        returncode = 0
        stdout = ''
        stderr = ''

    monkeypatch.setattr(chat_mod.subprocess, 'run', lambda *a, **k: _Proc())
    monkeypatch.setattr(chat_mod, '_watchdog_kill_ollama_runner_pid', lambda model: {'ok': False, 'detail': 'no permission'})

    def _restart(model):
        restarted['done'] = True
        return {'ok': True, 'detail': 'ollama service restarted', 'action': 'systemctl-restart-ollama'}

    monkeypatch.setattr(chat_mod, '_watchdog_restart_ollama_service', _restart)

    result = chat_mod._chat_try_hard_kill_local_agent('eight')

    assert result['ok'] is True
    assert any(a['action'] == 'ollama-stop' and a['ok'] for a in result['attempts'])
    assert any(a['action'] == 'kill-9-immediate' for a in result['attempts'])
    assert any(a['action'] == 'systemctl-restart-ollama' for a in result['attempts'])


def test_watchdog_resets_state_when_model_confirmed_gone(monkeypatch):
    _suppress_durable_spine_logs(monkeypatch)
    from frontend.blueprints import chat as chat_mod

    with chat_mod._WATCHDOG_KILL_LOCK:
        chat_mod._WATCHDOG_KILL_STATE.clear()

    monkeypatch.setattr(chat_mod, '_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_all_local_ollama_chat_agents', lambda: {'qwen'})
    monkeypatch.setattr(chat_mod, '_chat_agent_configured_model', lambda agent: 'qwen2.5:latest')
    monkeypatch.setattr(chat_mod, '_chat_running_ollama_models', lambda: [])
    monkeypatch.setattr(chat_mod, '_chat_model_aliases', lambda model: {str(model).lower()})

    chat_mod._watchdog_get_kill_state('qwen2.5:latest')['consecutive_failures'] = 3

    result = chat_mod._chat_try_hard_kill_local_agent('qwen')
    assert result['ok'] is True
    with chat_mod._WATCHDOG_KILL_LOCK:
        assert 'qwen2.5:latest' not in chat_mod._WATCHDOG_KILL_STATE


def test_skills_loop_does_not_nudge_empty_gateway_failure():
    from agents.skills_loop import run_skill_loop

    calls = []
    stages = []

    def _call_fn(_messages):
        calls.append(_messages)
        return '', 0

    answer, tokens = run_skill_loop(
        agent_name='mistral',
        call_fn=_call_fn,
        messages=[{'role': 'user', 'content': 'fix watchdog'}],
        emit_fn=stages.append,
        max_passes=2,
        nudge_if_no_skills=True,
    )

    assert answer == ''
    assert tokens == 0
    assert len(calls) == 1
    assert 'nudging for skill commands' not in stages


def test_terminal_job_ignores_late_stage_after_cancel():
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-cancelled'] = {
        'job_id': 'job-cancelled',
        'agent': 'mistral',
        'status': 'cancelled',
        'stage': 'cancelled by user',
        'eta_seconds': 0,
        'started_ts': now - 10,
        'updated_ts': now,
        'stage_trace': [{'text': 'cancelled by user', 'ts': now}],
    }

    cj._chat_update_job('job-cancelled', stage='finalizing answer')

    assert cj._CHAT_JOBS['job-cancelled']['stage'] == 'cancelled by user'


def test_terminal_job_ignores_late_stage_after_failed():
    _fresh_state()
    now = time.time()
    cj._CHAT_JOBS['job-failed'] = {
        'job_id': 'job-failed',
        'agent': 'mistral',
        'status': 'failed',
        'stage': 'stalled',
        'eta_seconds': 0,
        'started_ts': now - 10,
        'updated_ts': now,
        'stage_trace': [{'text': 'stalled (watchdog)', 'ts': now}],
    }

    cj._chat_update_job('job-failed', stage='finalizing answer')

    assert cj._CHAT_JOBS['job-failed']['stage'] == 'stalled'
