import json
import sqlite3
from pathlib import Path
import sys

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'utils'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontend'))


@pytest.fixture
def ticket_db(monkeypatch, tmp_path):
    from core.pipeline import ticket, orchestrator
    from frontend.blueprints import tickets

    db_path = tmp_path / 'tickets.db'

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    conn = connect()
    conn.executescript('''
        CREATE TABLE queue (id INTEGER PRIMARY KEY, from_addr TEXT, subject TEXT,
            question TEXT, status TEXT, source_type TEXT, agent TEXT,
            processed_at TEXT, completed_at TEXT);
        CREATE TABLE tickets (id INTEGER PRIMARY KEY, ticket_number TEXT UNIQUE,
            queue_id INTEGER, sender_email TEXT, question TEXT, tags TEXT, status TEXT,
            email_message_id TEXT, conv_id INTEGER, channel TEXT, agents_assigned TEXT,
            gemma_routing TEXT, updated_at TEXT, final_answer TEXT);
        CREATE TABLE ticket_notes (id INTEGER PRIMARY KEY, ticket_id INTEGER,
            agent TEXT, note_type TEXT, content TEXT, confidence REAL);
        CREATE TABLE agents (name TEXT, model TEXT, role TEXT, enabled INTEGER, tier TEXT);
        CREATE TABLE project_steps (status TEXT);
        CREATE TABLE scheduled_tasks (enabled INTEGER, next_run TEXT);
        INSERT INTO agents VALUES ('gemma','gemma3:latest','director',1,'local'),
            ('llama','llama3.2:latest','researcher',1,'local'),
            ('duck','mistral:latest','reviewer',1,'local'),
            ('nine','external','retired',0,'paid');
        INSERT INTO queue (id,status) VALUES (1,'queued');
        INSERT INTO tickets (ticket_number,queue_id,status,question)
            VALUES ('LOCAL-TEST',1,'open','Report local queue findings');
    ''')
    conn.commit()
    conn.close()
    monkeypatch.setattr('database.get_connection', connect)
    monkeypatch.setattr(tickets, 'get_connection', connect)
    monkeypatch.setattr(ticket, 'log_action', lambda *_args: None)
    monkeypatch.setattr(ticket, 'log_ticket_lifecycle', lambda *_args: None)
    calls = []

    def ask(agent, prompt, **kwargs):
        assert kwargs['allow_skills'] is False
        assert 'report-only ticket stage' in kwargs['system_prompt_override']
        calls.append(agent)
        return {'gemma': 'AGENT: llama\nREASON: Local inspection report.',
                'llama': 'Findings: enabled local agents exist.\nLimitations: no filesystem inspection.',
                'duck': 'YES\nFindings match supplied evidence.'}[agent]

    monkeypatch.setattr(orchestrator, 'ask_agent', ask)
    return connect, calls, ticket, tickets, orchestrator


def test_local_ticket_triage_findings_review_and_no_automatic_close(ticket_db):
    connect, calls, ticket, _, _ = ticket_db
    result = ticket.process_local_ticket('LOCAL-TEST')
    assert result['ok'] and calls == ['gemma', 'llama', 'duck']
    conn = connect()
    row = conn.execute('SELECT * FROM tickets').fetchone()
    assert row['status'] == 'open'
    assert json.loads(row['gemma_routing'])['agents'] == 'llama'
    assert 'No file edits' in row['final_answer']
    assert conn.execute('SELECT status FROM queue').fetchone()[0] == 'completed'
    assert [row[0] for row in conn.execute('SELECT note_type FROM ticket_notes')] == [
        'processing', 'triage', 'evidence', 'findings', 'review']
    conn.close()
    with pytest.raises(ValueError, match='already processing'):
        ticket.process_local_ticket('LOCAL-TEST')
    assert calls == ['gemma', 'llama', 'duck']


@pytest.mark.parametrize('response', ['AGENT: nine', 'AGENT: nonexistent', 'unparseable'])
def test_triage_rejects_disabled_external_or_unknown_agents(ticket_db, monkeypatch, response):
    connect, _, ticket, _, orchestrator = ticket_db
    monkeypatch.setattr(orchestrator, 'ask_agent', lambda *_args, **_kwargs: response)
    with pytest.raises(RuntimeError, match='enabled local analyst'):
        ticket.process_local_ticket('LOCAL-TEST')
    conn = connect()
    assert conn.execute('SELECT status FROM queue').fetchone()[0] == 'queued'
    assert conn.execute("SELECT count(*) FROM ticket_notes WHERE note_type='processing_error'").fetchone()[0] == 1
    conn.close()


def test_duck_rejection_does_not_complete_work(ticket_db, monkeypatch):
    connect, _, ticket, _, orchestrator = ticket_db
    original = orchestrator.ask_agent
    monkeypatch.setattr(orchestrator, 'ask_agent', lambda agent, *args, **kwargs:
                        'NO\nUnsupported claims.' if agent == 'duck' else original(agent, *args, **kwargs))
    assert ticket.process_local_ticket('LOCAL-TEST')['status'] == 'review_required'
    conn = connect()
    assert conn.execute('SELECT status FROM tickets').fetchone()[0] == 'open'
    assert conn.execute('SELECT status FROM queue').fetchone()[0] == 'queued'
    conn.close()


def test_ticket_recheck_requires_new_diagnostics_and_injects_them(ticket_db, monkeypatch):
    connect, _, ticket, _, orchestrator = ticket_db
    ticket.process_local_ticket('LOCAL-TEST')
    with pytest.raises(ValueError, match='fresh diagnostic'):
        ticket.process_local_ticket('LOCAL-TEST', recheck=True)
    ticket.add_agent_note('LOCAL-TEST', 'seven_runtime', 'diagnostic_result',
                          '{"grade":"passed","content":"FRESH_DIAGNOSTIC_42","unload":{"ok":true}}')
    original = orchestrator.ask_agent
    prompts = []

    def ask(agent, prompt, **kwargs):
        if agent == 'llama':
            prompts.append(prompt)
        return original(agent, prompt, **kwargs)

    monkeypatch.setattr(orchestrator, 'ask_agent', ask)
    assert ticket.process_local_ticket('LOCAL-TEST', recheck=True)['ok']
    assert 'FRESH_DIAGNOSTIC_42' in prompts[0]
    with pytest.raises(ValueError, match='fresh diagnostic'):
        ticket.process_local_ticket('LOCAL-TEST', recheck=True)
    conn = connect()
    assert conn.execute('SELECT status FROM tickets').fetchone()[0] == 'open'
    assert conn.execute('SELECT status FROM queue').fetchone()[0] == 'completed'
    conn.close()


def test_ticket_api_creates_a_real_ticket_and_processes_it(ticket_db):
    connect, _, _, tickets, _ = ticket_db
    app = Flask(__name__)
    app.register_blueprint(tickets.tickets_bp)
    client = app.test_client()
    assert client.post('/api/tickets', json={'question': 42}).status_code == 400
    created = client.post('/api/tickets', json={'question': 'Report the local roster'})
    assert created.status_code == 201
    number = created.json['ticket_number']
    response = client.post(f'/api/tickets/{number}/process')
    assert response.status_code == 200 and response.json['ok']
    assert client.post(f'/api/tickets/{number}/process').status_code == 409
    conn = connect()
    assert conn.execute('SELECT count(*) FROM tickets').fetchone()[0] == 2
    conn.close()