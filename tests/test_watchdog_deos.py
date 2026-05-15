from __future__ import annotations

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _conn(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


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
    warmed = []
    monkeypatch.setattr(watchdog_deos, '_warm_model', lambda *a, **k: warmed.append(a) or (True, 'warm ok'))
    run_calls = []
    monkeypatch.setattr(
        'fridays.task_runner.run_task',
        lambda name, args='': run_calls.append((name, args)) or (True, f'{name}:{args}'),
    )

    report = watchdog_deos.run_deos_cycle('prewarm=0 execute_recovery=1 agent_timeout_seconds=45')

    assert warmed == []
    assert report['operates']['expired_leases_cleared'] == 1
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
    monkeypatch.setattr(
        'fridays.task_runner.run_task',
        lambda name, args='': run_calls.append((name, args)) or (True, 'ok'),
    )

    report = watchdog_deos.run_deos_cycle('prewarm=1 execute_recovery=1 warm_timeout_seconds=20')

    assert report['operates']['ready_recovery_agents'] == ['librarian']
    assert run_calls
    assert run_calls[0][0] == 'relay_recovery_sweep'
    assert 'agents=librarian' in run_calls[0][1]


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
    assert [r['source_ref'] for r in claimed_evidence] == ['claim:S-WORK-1', 'agent-work:S-WORK-1']


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
    assert step['owner'] == 'qwen'
    assert 'rerouted to qwen' in step['residual_risk']
    assert evidence['status'] == 'warn'


def test_deos_cycle_uses_direct_local_model_for_relay_recovery(monkeypatch, tmp_path):
    from utils import watchdog_deos

    calls = []

    def fake_direct(agent, prompt, timeout_seconds):
        calls.append((agent, timeout_seconds, 'Live conversation context:' in prompt))
        return True, 'Health pulse: local recovery path is online.\nDEOS_STATUS: done', 9

    monkeypatch.setattr(watchdog_deos, '_run_local_agent_direct', fake_direct)

    ok, answer, tokens = watchdog_deos._run_local_agent_work(
        'qwen',
        'Recovery ID: recovery-x\nLive conversation context:\n- user: Health pulse in one line.',
        240,
    )

    assert ok is True
    assert tokens == 9
    assert 'DEOS_STATUS: done' in answer
    assert calls == [('qwen', 120, True)]
