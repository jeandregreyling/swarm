from __future__ import annotations

import importlib
from flask import Flask
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FRONTEND) not in sys.path:
    sys.path.insert(0, str(FRONTEND))


def test_agents_zoo_ping_get_snapshot(monkeypatch):
    agents_module = importlib.import_module('frontend.blueprints.agents')

    app = Flask(__name__)
    app.register_blueprint(agents_module.agents_bp)
    client = app.test_client()

    monkeypatch.setattr(
        agents_module,
        '_get_zoo_ping_snapshot',
        lambda: {
            'ok': True,
            'checked_at': '2026-05-29T01:02:03Z',
            'summary': {'agents_checked': 4, 'active': 1, 'disabled': 1, 'orphaned': 2},
            'orphaned_names': ['nine', 'qwen'],
            'breakdown': {
                'active': ['seven'],
                'local_faults': [{'name': 'qwen'}],
                'paid_faults': [{'name': 'nine'}],
                'disabled': [{'name': 'gemma'}],
            },
            'top_reasons': [{'reason': 'ollama unreachable', 'count': 1}],
            'items': [],
        },
    )

    resp = client.get('/api/agents/zoo-ping')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['summary']['orphaned'] == 2


def test_agents_zoo_ping_post_executes_census(monkeypatch):
    agents_module = importlib.import_module('frontend.blueprints.agents')

    app = Flask(__name__)
    app.register_blueprint(agents_module.agents_bp)
    client = app.test_client()

    monkeypatch.setattr(
        agents_module,
        '_full_zoo_ping',
        lambda: {
            'ok': True,
            'checked_at': '2026-05-29T01:02:03Z',
            'summary': {'agents_checked': 4, 'active': 1, 'disabled': 1, 'orphaned': 2},
            'results': {'nine': {'registry_status': 'STATUS_ORPHANED'}},
        },
    )

    resp = client.post('/api/agents/zoo-ping')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['summary']['agents_checked'] == 4


def test_monitor_payload_includes_zoo_census(monkeypatch):
    system_module = importlib.import_module('frontend.blueprints.system')
    monitor_module = importlib.import_module('monitor')
    registry_module = importlib.import_module('utils.db.registry')

    app = Flask(__name__)
    app.register_blueprint(system_module.system_bp)
    client = app.test_client()

    monkeypatch.setattr(
        monitor_module,
        'get_system_status',
        lambda: {
            'cpu_percent': 10,
            'ram_percent': 20,
            'swap_percent': 0,
            'active_models': [],
            'active_models_count': 0,
            'timestamp': 'now',
            'open_tickets': 0,
            'queue_depth': 0,
            'queue_processing': 0,
            'consults_today': 0,
            'disks': [],
            'memory_pools': {},
            'active_model': 'none',
        },
    )
    monkeypatch.setattr(system_module, '_CHAT_JOBS', {})
    monkeypatch.setattr(system_module, '_cleanup_chat_jobs_locked', lambda: None)
    monkeypatch.setattr(system_module, '_get_duck_flags_today', lambda: 0)
    monkeypatch.setattr(
        registry_module,
        'get_zoo_ping_snapshot',
        lambda: {
            'ok': True,
            'checked_at': '2026-05-29T01:02:03Z',
            'summary': {'agents_checked': 4, 'active': 1, 'disabled': 1, 'orphaned': 2},
            'orphaned_names': ['nine', 'qwen'],
            'breakdown': {
                'active': ['seven'],
                'local_faults': [{'name': 'qwen'}],
                'paid_faults': [{'name': 'nine'}],
                'disabled': [{'name': 'gemma'}],
            },
            'top_reasons': [{'reason': 'ollama unreachable', 'count': 1}],
            'items': [],
        },
    )

    resp = client.get('/api/monitor')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'zoo_census' in data
    assert data['zoo_census']['summary']['orphaned'] == 2
    assert data['zoo_census']['breakdown']['active'] == ['seven']
