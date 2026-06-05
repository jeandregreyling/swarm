from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.services import identity as ident
from frontend.terminal import create_app


def test_local_agent_reports_offline_when_ollama_runtime_is_down(monkeypatch):
    monkeypatch.setattr(ident, '_reg_runtime', lambda: {'qwen': 'local'})
    monkeypatch.setattr(ident, '_reg_models', lambda: {'qwen': 'qwen:latest'})
    monkeypatch.setattr(ident, '_ollama_runtime_running', lambda: False)
    from frontend.services import DISABLED_AGENTS
    DISABLED_AGENTS.discard('qwen')
    assert ident._agent_reachability_status('qwen') == 'offline'


def test_direct_seven_agent_uses_seven_runtime_reachability(monkeypatch):
    monkeypatch.setattr(ident, '_reg_runtime', lambda: {'seven': 'local'})
    monkeypatch.setattr(ident, '_reg_models', lambda: {'seven': 'seven-direct:daily'})
    monkeypatch.setattr(ident, '_ollama_runtime_running', lambda: False)
    monkeypatch.setattr(ident, '_seven_runtime_running', lambda: True)
    from frontend.services import DISABLED_AGENTS
    DISABLED_AGENTS.discard('seven')
    assert ident._agent_reachability_status('seven') == 'online'

    monkeypatch.setattr(ident, '_seven_runtime_running', lambda: False)
    assert ident._agent_reachability_status('seven') == 'offline'


def test_ghost_owner_stays_online_even_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(ident, '_ollama_runtime_running', lambda: False)
    assert ident._agent_reachability_status('ghost') == 'online'


def test_agents_status_endpoint_marks_local_agents_down_when_reachability_is_offline(monkeypatch, tmp_path):
    db = str(tmp_path / 'agents_status.db')
    hive_db = str(tmp_path / 'hive.db')
    monkeypatch.setenv('SWARM_DB', db)
    monkeypatch.setenv('SWARM_DB_PATH', db)
    monkeypatch.setenv('SWARM_HIVE_DB', hive_db)
    monkeypatch.setenv('SWARM_HIVE_TOKENS', str(tmp_path / 'tokens.jsonl'))

    import utils.db._connection as conn_mod
    conn_mod.DB_PATH = db
    import core.hive.registry as hive_registry
    hive_registry.reset_singleton()

    app = create_app()
    app.testing = True

    import importlib
    agents_mod = importlib.import_module('blueprints.agents')
    monkeypatch.setattr(
        agents_mod,
        '_agent_reachability_status',
        lambda name: 'offline' if str(name).lower() == 'qwen' else 'online',
    )

    with app.test_client() as client:
        resp = client.get('/api/agents/status')
    assert resp.status_code == 200
    rows = resp.get_json()
    qwen = next(row for row in rows if row['name'] == 'qwen')
    assert qwen['status'] == 'down'
