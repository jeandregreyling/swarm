from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


import pytest


@pytest.fixture(autouse=True)
def _multi_model_mode(monkeypatch):
    monkeypatch.setenv('SWARM_ONE_MODEL', '0')


def test_resident_policy_marks_direct_seven_model_as_not_ollama(tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-direct-policy.db'
    conn = _conn(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE agents (
                name TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                tier TEXT DEFAULT 'local',
                enabled INTEGER DEFAULT 1,
                eta_seconds INTEGER DEFAULT 60,
                keep_alive INTEGER DEFAULT 300
            );
            """
        )
        conn.executemany(
            "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
            [
                ('duck', 'qwen:latest', 300),
                ('librarian', 'qwen:latest', 300),
                ('seven', 'seven-direct:daily', 300),
            ],
        )
        conn.commit()

        targets = {row['agent']: row for row in watchdog_deos._resident_targets(conn)}
    finally:
        conn.close()

    assert targets['duck']['is_ollama'] is True
    assert targets['librarian']['is_ollama'] is True
    assert targets['seven']['is_ollama'] is False


def test_deos_cycle_records_control_plane_and_does_not_prewarm_by_default(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            conversation_id INTEGER DEFAULT 0,
            job_id TEXT UNIQUE NOT NULL,
            stalled_agent TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            recovery_agents_json TEXT DEFAULT '[]',
            relay_context_json TEXT DEFAULT '{}',
            summary TEXT DEFAULT '',
            lease_owner TEXT DEFAULT '',
            lease_until TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
        [
            ('duck', 'qwen2.5:latest', 300),
            ('librarian', 'qwen:latest', 300),
            ('seven', 'local-algorithm', 300),
        ],
    )
    conn.execute(
        """INSERT INTO chat_relay_recoveries
           (recovery_id, job_id, status, lease_owner, lease_until)
           VALUES ('recovery-old', 'job-old', 'open', 'tasker', datetime('now', '-1 minute'))"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(
        watchdog_deos,
        '_diamond_sch_health',
        lambda *_args, **_kwargs: {'recovered': False, 'reason': 'inactive', 'state': {'is_council_active': 0}},
    )
    monkeypatch.setattr(watchdog_deos, '_direct_runtime_snapshot', lambda: {
        'ok': True,
        'models': [{'name': 'seven-direct:daily'}],
        'servers': [],
        'resources': {'available_gb': 24.0},
        'inventory_roots': [],
        'warnings': [],
    })
    monkeypatch.setattr(watchdog_deos, '_seven_service_snapshot', lambda: {
        'ok': True,
        'service': 'seven-runtime',
        'model': 'seven-direct:daily',
        'flask_required': False,
        'ollama_required': False,
        'chat_timeout_s': 45,
        'direct_registered': True,
        'direct_model_count': 1,
        'resident_servers': 0,
        'warning': '',
    })
    warmed = []
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: warmed.append(a) or (True, 'warm ok'))
    run_calls = []
    task_runner = importlib.import_module('fridays.task_runner')
    monkeypatch.setattr(
        task_runner,
        'run_task',
        lambda name, args='': run_calls.append((name, args)) or (True, f'{name}:{args}'),
    )

    report = watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=1 agent_timeout_seconds=45')

    assert warmed == []
    assert report['operates']['expired_leases_cleared'] == 1
    assert report['operates']['diamond_sch']['reason'] == 'inactive'
    assert report['decides']['direct_runtime_policy']['ok'] is True
    assert report['operates']['direct_runtime']['models'][0]['name'] == 'seven-direct:daily'
    assert report['decides']['seven_service_policy']['service'] == 'seven-runtime'
    assert report['decides']['seven_service_policy']['ollama_required'] is False
    assert run_calls == []
    assert any('recovery skipped: no support agents ready' in item for item in report['executes'])

    conn = _conn(db_path)
    try:
        step = conn.execute(
            "SELECT status, owner_route FROM project_steps WHERE step_id='S-DEOS-CONTROL-PLANE'"
        ).fetchone()
        evidence = conn.execute(
            "SELECT COUNT(*) FROM project_step_evidence WHERE step_id='S-DEOS-CONTROL-PLANE'"
        ).fetchone()[0]
        lease = conn.execute(
            "SELECT lease_owner, lease_until FROM chat_relay_recoveries WHERE recovery_id='recovery-old'"
        ).fetchone()
    finally:
        conn.close()

    assert step['status'] == 'doing'
    assert step['owner_route'] == 'watchdog:deos'
    assert evidence >= 1
    assert lease['lease_owner'] == ''
    assert lease['lease_until'] == ''


def test_deos_cycle_can_run_direct_runtime_smoke_when_requested(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-direct-smoke.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'open'
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
        [('duck', 'qwen2.5:latest', 300), ('librarian', 'qwen:latest', 300), ('seven', 'local-algorithm', 300)],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_direct_runtime_snapshot', lambda: {
        'ok': True,
        'models': [{'name': 'seven-direct:daily'}],
        'servers': [],
        'resources': {'available_gb': 24.0},
        'inventory_roots': [],
        'warnings': [],
    })
    smoke_calls = []
    monkeypatch.setattr(
        watchdog_deos,
        '_direct_runtime_smoke',
        lambda timeout_seconds: smoke_calls.append(timeout_seconds) or (True, 'direct smoke ok=True tokens=4 chunks=4'),
    )

    report = watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=0 execute_work=0 direct_smoke=1 warm_timeout_seconds=30')

    assert smoke_calls == [30]
    assert any('direct smoke ok=True' in item for item in report['executes'])
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT project_id, step_id, source_ref, status FROM project_step_evidence WHERE source_ref='watchdog-deos:direct-smoke'"
        ).fetchall()
    finally:
        conn.close()
    assert rows
    assert rows[0]['project_id'] == 'P-SEVEN-DIRECT-GGUF'
    assert rows[0]['step_id'] == 'S-DGGUF-08'
    assert rows[0]['status'] == 'ok'


def test_deos_cycle_records_seven_runtime_service(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-seven-service.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'open'
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
        [('duck', 'qwen:latest', 300), ('librarian', 'qwen:latest', 300), ('seven', 'seven-direct:daily', 300)],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_direct_runtime_snapshot', lambda: {
        'ok': True,
        'models': [{'name': 'seven-direct:daily'}],
        'servers': [],
        'resources': {'available_gb': 24.0},
        'inventory_roots': [],
        'warnings': [],
    })
    monkeypatch.setattr(watchdog_deos, '_seven_service_snapshot', lambda: {
        'ok': True,
        'service': 'seven-runtime',
        'model': 'seven-direct:daily',
        'flask_required': False,
        'ollama_required': False,
        'chat_timeout_s': 45,
        'direct_registered': True,
        'direct_model_count': 1,
        'resident_servers': 0,
        'warning': '',
    })

    report = watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=0 execute_work=0')

    assert report['decides']['seven_service_policy']['ok'] is True
    assert report['decides']['seven_service_policy']['flask_required'] is False
    assert report['decides']['seven_service_policy']['ollama_required'] is False
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT project_id, step_id, source_ref, status FROM project_step_evidence WHERE source_ref='watchdog-deos:seven-runtime-service'"
        ).fetchall()
    finally:
        conn.close()
    assert rows
    assert rows[0]['project_id'] == 'P-SEVEN-DIRECT-GGUF'
    assert rows[0]['step_id'] == 'S-DGGUF-11'
    assert rows[0]['status'] == 'ok'


def test_deos_cycle_prewarm_is_bounded_and_support_only(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-prewarm.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'open'
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
        [
            ('duck', 'qwen2.5:latest', 600),
            ('librarian', 'qwen:latest', 600),
            ('seven', 'local-algorithm', 300),
            ('mistral', 'mistral:latest', 300),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: ['qwen:latest'])
    warmed = []

    def fake_warm(model, keep_alive, timeout_seconds):
        warmed.append((model, keep_alive, timeout_seconds))
        return True, f'{model} warm ok'

    monkeypatch.setattr(watchdog_deos, '_warm_model', fake_warm)

    report = watchdog_deos.run_deos_cycle('prewarm=1 execute_recovery=0 warm_timeout_seconds=20')

    assert warmed == [('qwen2.5:latest', 600, 20)]
    assert any('librarian:qwen:latest already resident' in item for item in report['executes'])
    assert any('seven is control/logical role' in item for item in report['executes'])


def test_deos_cycle_executes_with_ready_support_agent_only(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-ready.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'open'
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
        [
            ('duck', 'qwen2.5:latest', 600),
            ('librarian', 'qwen:latest', 600),
            ('seven', 'local-algorithm', 300),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: ['qwen:latest'])
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: (False, 'duck cold'))
    run_calls = []
    task_runner = importlib.import_module('fridays.task_runner')
    monkeypatch.setattr(
        task_runner,
        'run_task',
        lambda name, args='': run_calls.append((name, args)) or (True, 'ok'),
    )
    monkeypatch.setattr(
        watchdog_deos,
        '_claim_local_agent_step',
        lambda *_args, **_kwargs: pytest.fail('local work must wait until the next one-task cycle'),
    )

    report = watchdog_deos.run_deos_cycle(
        'prewarm=1 execute_recovery=1 execute_work=1 warm_timeout_seconds=20'
    )

    assert report['operates']['ready_recovery_agents'] == ['librarian']
    assert run_calls
    assert run_calls[0][0] == 'relay_recovery_sweep'
    assert 'agents=librarian' in run_calls[0][1]
    assert 'sweep_timeout_seconds=180' in run_calls[0][1]
    assert 'local agent work deferred: recovery attempt consumed this one-task cycle' in report['executes']


def test_deos_cycle_claims_one_local_agent_work_step(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-work.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (
            recovery_id TEXT PRIMARY KEY,
            job_id TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'open'
        );
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            methodology TEXT DEFAULT 'agile',
            status TEXT DEFAULT 'active',
            owner TEXT DEFAULT 'seven',
            created_at REAL,
            updated_at REAL,
            priority INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]'
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'todo',
            owner TEXT DEFAULT 'seven',
            order_idx INTEGER DEFAULT 0,
            created_at REAL,
            updated_at REAL,
            residual_risk TEXT DEFAULT '',
            owner_route TEXT DEFAULT ''
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model, keep_alive) VALUES (?, ?, ?)",
        [
            ('duck', 'qwen2.5:latest', 600),
            ('librarian', 'qwen:latest', 600),
            ('seven', 'local-algorithm', 300),
            ('mistral', 'mistral:latest', 300),
        ],
    )
    conn.execute(
        "INSERT INTO projects (project_id, name, created_at) VALUES ('P-WORK', 'Work', 1)"
    )
    conn.execute(
        """INSERT INTO project_steps
           (step_id, project_id, title, description, status, owner, created_at, updated_at, owner_route)
           VALUES ('S-WORK-1', 'P-WORK', 'Patch tiny issue', 'Do the tiny fix.', 'todo', 'mistral', 1, 1, 'test')"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: (False, 'cold'))
    calls = []

    def fake_run(agent, prompt, timeout_seconds):
        calls.append((agent, prompt, timeout_seconds))
        return True, 'Proof: pytest passed\nDEOS_STATUS: done', 12

    monkeypatch.setattr(watchdog_deos, '_run_local_agent_work', fake_run)

    report = watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=0 execute_work=1 work_timeout_seconds=120')

    assert calls and calls[0][0] == 'mistral'
    assert 'Step: S-WORK-1' in calls[0][1]
    assert calls[0][2] == 120
    assert any('local_agent_work agent=mistral step=S-WORK-1 status=done' in item for item in report['executes'])

    conn = _conn(db_path)
    try:
        step = conn.execute("SELECT status, residual_risk FROM project_steps WHERE step_id='S-WORK-1'").fetchone()
        evidence = conn.execute(
            "SELECT status, summary FROM project_step_evidence WHERE source_ref='agent-work:S-WORK-1'"
        ).fetchone()
        claimed_evidence = conn.execute(
            "SELECT source_ref, status FROM project_step_evidence WHERE step_id='S-WORK-1' ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    assert step['status'] == 'done'
    assert step['residual_risk'] == ''
    assert evidence['status'] == 'ok'
    assert 'DEOS_STATUS: done' in evidence['summary']
    assert 'coaching=passed' in evidence['summary']
    assert [r['source_ref'] for r in claimed_evidence] == ['claim:S-WORK-1', 'agent-work:S-WORK-1']


def test_deos_claim_refuses_second_local_agent_task_while_one_is_doing(tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-one-task-gate.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, status TEXT DEFAULT 'todo', owner TEXT DEFAULT 'seven',
            order_idx INTEGER DEFAULT 0, created_at REAL, updated_at REAL,
            residual_risk TEXT DEFAULT '', owner_route TEXT DEFAULT ''
        );
        """
    )
    conn.executemany(
        """INSERT INTO project_steps
           (step_id, project_id, title, status, owner, created_at, updated_at)
           VALUES (?, 'P-WORK', ?, ?, ?, ?, ?)""",
        [
            ('S-ACTIVE', 'Already active', 'doing', 'gemma', 1, 1),
            ('S-WAITING', 'Must wait', 'todo', 'mistral', 2, 2),
        ],
    )
    conn.commit()

    claimed = watchdog_deos._claim_local_agent_step(conn)
    waiting = conn.execute(
        "SELECT status FROM project_steps WHERE step_id='S-WAITING'"
    ).fetchone()
    conn.close()

    assert claimed is None
    assert waiting['status'] == 'todo'


def test_deos_cycle_blocks_unverified_local_agent_result(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-work-blocked.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (recovery_id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'open');
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            methodology TEXT DEFAULT 'agile', status TEXT DEFAULT 'active',
            owner TEXT DEFAULT 'seven', created_at REAL, updated_at REAL,
            priority INTEGER DEFAULT 0, tags TEXT DEFAULT '[]'
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, status TEXT DEFAULT 'todo', owner TEXT DEFAULT 'seven',
            order_idx INTEGER DEFAULT 0, created_at REAL, updated_at REAL,
            residual_risk TEXT DEFAULT '', owner_route TEXT DEFAULT ''
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model) VALUES (?, ?)",
        [('duck', 'qwen2.5:latest'), ('librarian', 'qwen:latest'), ('seven', 'local-algorithm'), ('qwen', 'qwen2.5:latest')],
    )
    conn.execute("INSERT INTO projects (project_id, name, created_at) VALUES ('P-WORK', 'Work', 1)")
    conn.execute(
        """INSERT INTO project_steps
           (step_id, project_id, title, description, status, owner, created_at, updated_at)
           VALUES ('S-WORK-2', 'P-WORK', 'Ambiguous task', 'Figure it out.', 'todo', 'qwen', 1, 1)"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: (False, 'cold'))
    monkeypatch.setattr(
        watchdog_deos,
        '_run_local_agent_work',
        lambda *a, **k: (True, 'I looked at it but did not prove it.', 3),
    )

    watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=0 execute_work=1')

    conn = _conn(db_path)
    try:
        step = conn.execute("SELECT status, residual_risk FROM project_steps WHERE step_id='S-WORK-2'").fetchone()
        evidence = conn.execute(
            "SELECT status, summary FROM project_step_evidence WHERE step_id='S-WORK-2' AND source_ref='agent-work:S-WORK-2'"
        ).fetchone()
    finally:
        conn.close()
    assert step['status'] == 'blocked'
    assert 'DEOS_STATUS: done' in step['residual_risk']
    assert evidence['status'] == 'warn'
    assert 'did not prove it' in evidence['summary']


def test_deos_cycle_blocks_refusal_even_with_done_status(monkeypatch, tmp_path):
    from utils import watchdog_deos

    assert watchdog_deos._looks_like_refusal(
        "I'm sorry, but I am unable to assist you with this request.\nDEOS_STATUS: done"
    )


def test_deos_cycle_returns_stale_local_work_claim_to_board(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-stale-work.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (recovery_id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'open');
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            methodology TEXT DEFAULT 'agile', status TEXT DEFAULT 'active',
            owner TEXT DEFAULT 'seven', created_at REAL, updated_at REAL,
            priority INTEGER DEFAULT 0, tags TEXT DEFAULT '[]'
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, status TEXT DEFAULT 'todo', owner TEXT DEFAULT 'seven',
            order_idx INTEGER DEFAULT 0, created_at REAL, updated_at REAL,
            residual_risk TEXT DEFAULT '', owner_route TEXT DEFAULT ''
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model) VALUES (?, ?)",
        [('duck', 'qwen2.5:latest'), ('librarian', 'qwen:latest'), ('seven', 'local-algorithm'), ('gemma', 'gemma3:latest')],
    )
    conn.execute("INSERT INTO projects (project_id, name, created_at) VALUES ('P-WORK', 'Work', 1)")
    conn.execute(
        """INSERT INTO project_steps
           (step_id, project_id, title, description, status, owner, created_at, updated_at)
           VALUES ('S-WORK-STALE', 'P-WORK', 'Stale claim', 'Recover me.', 'doing', 'gemma', 1, 1)"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: (False, 'cold'))

    report = watchdog_deos.run_deos_cycle(
        'prewarm=0 execute_recovery=0 execute_work=0 local_work_stale_seconds=300'
    )

    conn = _conn(db_path)
    try:
        step = conn.execute("SELECT status, residual_risk FROM project_steps WHERE step_id='S-WORK-STALE'").fetchone()
        evidence = conn.execute(
            "SELECT status, summary FROM project_step_evidence WHERE step_id='S-WORK-STALE' AND source_ref='stale-claim:S-WORK-STALE'"
        ).fetchone()
    finally:
        conn.close()
    assert report['operates']['stale_local_work_claims'] == 1
    assert step['status'] == 'blocked'
    assert 'expired' in step['residual_risk']
    assert evidence['status'] == 'warn'


def test_deos_cycle_reroutes_blocked_failed_local_work(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-reroute-work.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (recovery_id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'open');
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            methodology TEXT DEFAULT 'agile', status TEXT DEFAULT 'active',
            owner TEXT DEFAULT 'seven', created_at REAL, updated_at REAL,
            priority INTEGER DEFAULT 0, tags TEXT DEFAULT '[]'
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, status TEXT DEFAULT 'todo', owner TEXT DEFAULT 'seven',
            order_idx INTEGER DEFAULT 0, created_at REAL, updated_at REAL,
            residual_risk TEXT DEFAULT '', owner_route TEXT DEFAULT ''
        );
        CREATE TABLE project_step_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            source_type TEXT DEFAULT 'task',
            source_ref TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            status TEXT DEFAULT 'ok',
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model) VALUES (?, ?)",
        [('duck', 'qwen2.5:latest'), ('librarian', 'qwen:latest'), ('seven', 'local-algorithm'), ('qwen', 'qwen2.5:latest'), ('gemma', 'gemma3:latest')],
    )
    conn.execute("INSERT INTO projects (project_id, name, created_at) VALUES ('P-WORK', 'Work', 1)")
    conn.execute(
        """INSERT INTO project_steps
           (step_id, project_id, title, description, status, owner, created_at, updated_at)
           VALUES ('S-WORK-REROUTE', 'P-WORK', 'Failed Mistral packet', 'Recover me.', 'blocked', 'mistral', 1, 1)"""
    )
    conn.execute(
        """INSERT INTO project_step_evidence
           (project_id, step_id, source_type, source_ref, summary, status)
           VALUES ('P-WORK', 'S-WORK-REROUTE', 'watchdog_deos', 'agent-work:S-WORK-REROUTE', 'mistral result tokens=0: ', 'warn')"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: (False, 'cold'))

    report = watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=0 execute_work=0')

    conn = _conn(db_path)
    try:
        step = conn.execute("SELECT owner, residual_risk FROM project_steps WHERE step_id='S-WORK-REROUTE'").fetchone()
        evidence = conn.execute(
            "SELECT status, summary FROM project_step_evidence WHERE step_id='S-WORK-REROUTE' AND source_ref='reroute:S-WORK-REROUTE'"
        ).fetchone()
    finally:
        conn.close()
    assert report['operates']['rerouted_local_work'] == 1
    assert step['owner'] == 'fred'
    assert 'rerouted to fred' in step['residual_risk']
    assert evidence['status'] == 'warn'


def test_deos_cycle_uses_direct_local_model_for_relay_recovery(monkeypatch, tmp_path):
    from utils import watchdog_deos

    calls = []

    def fake_direct(agent, mode, prompt, timeout_seconds):
        calls.append((agent, mode, timeout_seconds, 'Live conversation context:' in prompt))
        return True, 'Health pulse: local recovery path is online.\nDEOS_STATUS: done', 9

    monkeypatch.setattr(watchdog_deos, '_run_local_agent_direct_guarded', fake_direct)

    ok, answer, tokens = watchdog_deos._run_local_agent_work(
        'qwen',
        'Recovery ID: recovery-x\nLive conversation context:\n- user: Health pulse in one line.',
        240,
    )

    assert ok is True
    assert tokens == 9
    assert 'DEOS_STATUS: done' in answer
    assert calls == [('qwen', 'recovery', 120, True)]


def test_deos_cycle_uses_direct_local_model_for_micro_task(monkeypatch):
    from utils import watchdog_deos

    calls = []

    def fake_micro(agent, mode, prompt, timeout_seconds):
        calls.append((agent, mode, timeout_seconds, 'DEOS_MICRO_TASK' in prompt))
        return True, 'Mistral micro result\nDEOS_STATUS: done', 4

    monkeypatch.setattr(watchdog_deos, '_run_local_agent_direct_guarded', fake_micro)

    ok, answer, tokens = watchdog_deos._run_local_agent_work(
        'mistral',
        'Project: P\nDEOS_MICRO_TASK\nTask: Return READY.',
        180,
    )

    assert ok is True
    assert tokens == 4
    assert 'DEOS_STATUS: done' in answer
    assert calls == [('mistral', 'micro', 90, True)]


def test_deos_cycle_filters_local_work_by_project_and_owner(monkeypatch, tmp_path):
    from utils import watchdog_deos

    db_path = tmp_path / 'deos-filter-work.db'
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE agents (
            name TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            tier TEXT DEFAULT 'local',
            enabled INTEGER DEFAULT 1,
            eta_seconds INTEGER DEFAULT 60,
            keep_alive INTEGER DEFAULT 300
        );
        CREATE TABLE chat_relay_recoveries (recovery_id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'open');
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            methodology TEXT DEFAULT 'agile', status TEXT DEFAULT 'active',
            owner TEXT DEFAULT 'seven', created_at REAL, updated_at REAL,
            priority INTEGER DEFAULT 0, tags TEXT DEFAULT '[]'
        );
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
            description TEXT, status TEXT DEFAULT 'todo', owner TEXT DEFAULT 'seven',
            order_idx INTEGER DEFAULT 0, created_at REAL, updated_at REAL,
            residual_risk TEXT DEFAULT '', owner_route TEXT DEFAULT ''
        );
        """
    )
    conn.executemany(
        "INSERT INTO agents (name, model) VALUES (?, ?)",
        [('duck', 'qwen2.5:latest'), ('librarian', 'qwen:latest'), ('seven', 'local-algorithm'), ('mistral', 'mistral:latest'), ('qwen', 'qwen:latest')],
    )
    conn.execute("INSERT INTO projects (project_id, name, created_at) VALUES ('P-DRILL', 'Drill', 1)")
    conn.execute("INSERT INTO projects (project_id, name, created_at) VALUES ('P-OTHER', 'Other', 1)")
    conn.execute(
        "INSERT INTO project_steps (step_id, project_id, title, description, status, owner, created_at, updated_at) VALUES ('S-OTHER-1','P-OTHER','Old other','DEOS_MICRO_TASK\\nTask: other','todo','qwen',1,1)"
    )
    conn.execute(
        "INSERT INTO project_steps (step_id, project_id, title, description, status, owner, created_at, updated_at) VALUES ('S-DRILL-1','P-DRILL','Drill one','DEOS_MICRO_TASK\\nTask: drill','todo','mistral',1,2)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(watchdog_deos, 'get_connection', lambda: _conn(db_path))
    monkeypatch.setattr(watchdog_deos, '_ollama_loaded', lambda: [])
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: (False, 'cold'))
    monkeypatch.setattr(
        watchdog_deos,
        '_run_local_agent_work',
        lambda agent, prompt, timeout_seconds: (True, 'drill done\nDEOS_STATUS: done', 2),
    )

    watchdog_deos.run_deos_cycle(
        'prewarm=0 execute_recovery=0 execute_work=1 work_project_id=P-DRILL work_owner=mistral work_step_prefix=S-DRILL-'
    )

    conn = _conn(db_path)
    try:
        drill = conn.execute("SELECT status FROM project_steps WHERE step_id='S-DRILL-1'").fetchone()
        other = conn.execute("SELECT status FROM project_steps WHERE step_id='S-OTHER-1'").fetchone()
    finally:
        conn.close()
    assert drill['status'] == 'done'
    assert other['status'] == 'todo'


def test_direct_local_agent_guard_times_out_hung_micro_call(monkeypatch):
    from utils import watchdog_deos

    resets = []

    def hung_micro(*_args, **_kwargs):
        time.sleep(10)
        return True, 'late\nDEOS_STATUS: done', 1

    monkeypatch.setattr(watchdog_deos, '_run_local_agent_micro_direct', hung_micro)
    monkeypatch.setattr(
        watchdog_deos,
        '_hard_reset_ollama_after_timeout',
        lambda agent, mode: resets.append((agent, mode)) or 'ollama hard reset after timeout',
    )

    ok, answer, tokens = watchdog_deos._run_local_agent_direct_guarded(
        'mistral',
        'micro',
        'DEOS_MICRO_TASK\nTask: Return READY.',
        1,
    )

    assert ok is False
    assert tokens == 0
    assert 'guarded timeout 1s' in answer
    assert resets == [('mistral', 'micro')]


def test_one_model_mode_blocks_prewarm_work_and_recovery(monkeypatch):
    from utils import watchdog_deos as wd
    monkeypatch.setenv('SWARM_ONE_MODEL', '1')
    assert wd._one_model_mode() is True
    monkeypatch.setenv('SWARM_ONE_MODEL', '0')
    assert wd._one_model_mode() is False


def _steps_db(tmp_path):
    conn = _conn(tmp_path / 'deos-steps.db')
    conn.executescript(
        """
        CREATE TABLE project_steps (
            step_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, description TEXT,
            status TEXT, owner TEXT, owner_route TEXT, residual_risk TEXT,
            updated_at REAL, created_at REAL);
        CREATE TABLE project_step_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, step_id TEXT,
            source_type TEXT, source_ref TEXT, summary TEXT, status TEXT);
        CREATE TABLE ghost_circle (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, entry_type TEXT,
            content TEXT, created_at TEXT);
        CREATE TABLE chat_jobs (job_id TEXT, status TEXT, stage TEXT, updated_at TEXT);
        """
    )
    return conn


def _add(conn, sid, status, owner='fred'):
    conn.execute(
        "INSERT INTO project_steps (step_id, project_id, title, description, status, owner, updated_at, created_at)"
        " VALUES (?, 'P', 't', 'd', ?, ?, 1, 1)", (sid, status, owner))
    conn.commit()


def test_one_model_claim_skips_blocked_and_continue_carries_notes(tmp_path, monkeypatch):
    from utils import watchdog_deos

    monkeypatch.setenv('SWARM_ONE_MODEL', '1')
    conn = _steps_db(tmp_path)
    _add(conn, 'S-BLOCKED', 'blocked')
    assert watchdog_deos._claim_local_agent_step(conn, owner='fred') is None
    _add(conn, 'S-TODO', 'todo')
    step = watchdog_deos._claim_local_agent_step(conn, owner='fred')
    assert step['step_id'] == 'S-TODO'

    out = watchdog_deos._finish_local_agent_step(
        conn, step, True, 'part one finished\nPROGRESS: next append part two\nDEOS_STATUS: continue', 10)
    assert out == 'continue'
    assert conn.execute("SELECT status FROM project_steps WHERE step_id='S-TODO'").fetchone()[0] == 'todo'
    notes = watchdog_deos._progress_notes(conn, step)
    assert len(notes) == 1 and 'append part two' in notes[0]
    assert 'append part two' in watchdog_deos._agent_work_prompt(step, notes)


def test_continue_limit_blocks_and_failed_skill_refuses_done(tmp_path):
    from utils import watchdog_deos

    conn = _steps_db(tmp_path)
    _add(conn, 'S-LOOP', 'doing')
    step = {'step_id': 'S-LOOP', 'project_id': 'P', 'owner': 'fred', 'title': 't'}
    for i in range(watchdog_deos.MAX_CONTINUES):
        watchdog_deos._finish_local_agent_step(conn, step, True, 'more\nDEOS_STATUS: continue', 1)
    assert watchdog_deos._finish_local_agent_step(conn, step, True, 'more\nDEOS_STATUS: continue', 1) == 'blocked'

    _add(conn, 'S-FAIL', 'doing')
    conn.execute("INSERT INTO ghost_circle (source, entry_type, content, created_at) VALUES "
                 "('fred', 'skill_call', '[FAILED] fs_write(x) -> boom', datetime('now'))")
    conn.commit()
    step = {'step_id': 'S-FAIL', 'project_id': 'P', 'owner': 'fred', 'title': 't'}
    status = watchdog_deos._finish_local_agent_step(
        conn, step, True, 'I wrote and verified it, created the file.\nDEOS_STATUS: done', 5,
        claimed_at=time.time() - 60)
    assert status == 'blocked'


def test_chat_job_active_guard(tmp_path):
    from utils import watchdog_deos

    conn = _steps_db(tmp_path)
    assert watchdog_deos._chat_job_active(conn) is False
    conn.execute("INSERT INTO chat_jobs VALUES ('j1', 'running', 'dispatching', datetime('now'))")
    conn.execute("INSERT INTO chat_jobs VALUES ('j2', 'completed', 'completed', datetime('now'))")
    conn.commit()
    assert watchdog_deos._chat_job_active(conn) is True
    conn.execute("UPDATE chat_jobs SET updated_at='2000-01-01 00:00:00'")
    conn.commit()
    assert watchdog_deos._chat_job_active(conn) is False


def test_empty_fenced_write_is_an_error():
    from fridays import skills

    ok, msg = skills._skill_fs_write('sandpits/fred/x.md\n```\n```', 'fred')
    assert not ok and 'empty block' in msg
    ok, msg = skills._skill_fs_append('sandpits/fred/x.md\n```\n```', 'fred')
    assert not ok and 'empty block' in msg


def test_continue_status_tolerates_trailing_punctuation():
    from utils import watchdog_deos

    assert watchdog_deos._CONTINUE_RE.search('PROGRESS: x\n\nDEOS_STATUS: continue.')
