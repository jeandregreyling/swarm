"""APEX-only retrieval against disposable SQLite and sandpit storage."""
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'frontend'), str(ROOT / 'utils')]


@pytest.fixture
def memory_panel(tmp_path, monkeypatch):
    db = tmp_path / 'memory-panel.db'
    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    monkeypatch.setenv('SWARM_DB', str(db))
    monkeypatch.setenv('SWARM_ROOT', str(tmp_path))
    from utils.db import _connection
    monkeypatch.setattr(_connection, 'DB_PATH', str(db))
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE memory_apex (
                id INTEGER PRIMARY KEY, agent TEXT, subject TEXT, content TEXT,
                tags TEXT, importance INTEGER, archived INTEGER, created_at TEXT);
            INSERT INTO memory_apex VALUES
                (1, 'apex', 'needle subject', 'first', '', 3, 0, '2026-01-01'),
                (2, 'fred', 'second', 'needle content', '', 8, 0, '2026-01-02'),
                (3, 'apex', 'third', 'third', 'needle tags', 5, 0, '2026-01-02'),
                (4, 'apex', 'needle archived', 'hidden', '', 9, 1, '2026-01-03');
        """)
    memory = importlib.import_module('frontend.blueprints.memory')

    def connect():
        conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(memory, 'get_connection', connect)
    monkeypatch.setattr(memory, '_reg_mem_tables',
                        lambda: pytest.fail('Retrieval must not consult registry metadata'))
    app = Flask(__name__)
    app.register_blueprint(memory.memory_bp)
    return app.test_client(), memory, tmp_path


def flatten(response):
    return [row for rows in response.get_json()['results'].values() for row in rows]


@pytest.mark.parametrize('agent', ['', 'apex', ' APEX '])
def test_panel_reads_apex_without_registry_or_other_memory_tables(memory_panel, agent):
    client, memory, _ = memory_panel
    response = client.get('/api/memory', query_string={
        'agent': agent, 'q': 'needle', 'include_local': '0', 'limit': 2,
    })
    assert response.status_code == 200
    assert response.get_json()['limit'] == 2
    assert {row['id'] for row in flatten(response)} == {2, 3}
    assert all(row['source_table'] == 'memory_apex' for row in flatten(response))
    # Preserve stored authors, without silently dropping Fred-authored APEX rows.
    assert set(response.get_json()['results']) == {'fred', 'apex'}
    rows = memory._memory_search('needle', 3, limit=10)
    assert [row['id'] for row in rows] == [2, 3, 1]
    assert [row['id'] for row in memory._memory_search('needle', 6)] == [2]


@pytest.mark.parametrize('agent', ['fred', 'mistral', 'ed:mistral-', "apex' OR 1=1 --"])
def test_legacy_agent_is_rejected_before_opening_storage(memory_panel, monkeypatch, agent):
    client, memory, _ = memory_panel
    monkeypatch.setattr(memory, 'get_connection',
                        lambda: pytest.fail('Invalid selection must not open storage'))
    response = client.get('/api/memory', query_string={'agent': agent})
    assert response.status_code == 400
    assert response.get_json() == {'error': 'Memory retrieval permits only the APEX agent.'}


@pytest.mark.parametrize('limit,expected', [('0', 1), ('2', 2), ('9999', 500)])
def test_existing_limit_bounds_are_preserved(memory_panel, limit, expected):
    client, _, _ = memory_panel
    response = client.get('/api/memory', query_string={'limit': limit, 'include_local': '0'})
    assert response.status_code == 200
    assert response.get_json()['limit'] == expected
    assert len(flatten(response)) <= expected


def test_local_files_are_apex_only_and_respect_the_combined_limit(memory_panel):
    client, _, root = memory_panel
    for agent in ('apex', 'fred', 'shared'):
        folder = root / 'sandpits' / agent
        folder.mkdir(parents=True)
        (folder / 'MEMORY.md').write_text('needle local note')
    response = client.get('/api/memory', query_string={'q': 'needle', 'limit': 10})
    assert response.status_code == 200
    files = [row for row in flatten(response) if row['source_table'] == 'local_file']
    assert len(files) == 1 and files[0]['agent'] == 'apex'
    limited = client.get('/api/memory', query_string={'limit': 1})
    assert len(flatten(limited)) == 1
    db_only = client.get('/api/memory', query_string={'include_local': '0'})
    assert all(row['source_table'] == 'memory_apex' for row in flatten(db_only))


def test_memory_ui_has_only_apex_tabs_and_handles_http_errors():
    js = (ROOT / 'frontend/static/js/views/memory.js').read_text()
    tabs = js.split('function renderMemoryAgentTabs()', 1)[1].split(
        "document.addEventListener('DOMContentLoaded'", 1)[0]
    assert '/api/agents/config' not in tabs
    assert 'data-agent="apex"' in tabs
    assert "window.__memoryAgent = 'apex'" in js
    assert 'if (!r.ok) throw new Error(data.error' in js
    template = (ROOT / 'frontend/templates/terminal_base.html').read_text()
    panel = template.split('id="memory-agent-tabs"', 1)[1].split(
        'id="memory-source-tabs"', 1)[0]
    assert panel.count('data-agent=') == 1
    assert 'data-agent="apex"' in panel
