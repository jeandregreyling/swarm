import json
import os
from pathlib import Path
import sys

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / "utils")]


def test_evidence_default_is_independent_private_and_persistent(tmp_path, monkeypatch):
    from frontend.blueprints import studio_evidence

    monkeypatch.delenv("SWARM_DB", raising=False)
    fake_module = tmp_path / "frontend" / "blueprints" / "studio_evidence.py"
    monkeypatch.setattr(studio_evidence, "__file__", str(fake_module))
    conn = studio_evidence._db()
    path = Path(conn.execute("pragma database_list").fetchone()[2])
    assert path == tmp_path / "runtime" / "studio-evidence.sqlite"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700
    conn.close()
    app = Flask(__name__)
    app.register_blueprint(studio_evidence.studio_evidence_bp)
    with app.test_client() as client:
        receipt = {
            "kind": "local_agent_teaching", "job_id": "local-fridays-repair-20261024",
            "agent": "qwen", "status": "correction", "stage": "test",
            "error": "Actual rejected output", "output": "Local generated artifact",
        }
        assert client.post("/api/studio/evidence/pin", json=receipt).get_json()["ok"] is True
        data = client.get("/api/studio/evidence").get_json()
        assert data["items"][0]["payload"] == receipt
    assert not (tmp_path / "swarm_memory.db").exists()


def test_explicit_evidence_override_is_preserved(tmp_path, monkeypatch):
    from frontend.blueprints import studio_evidence

    override = tmp_path / "explicit.sqlite"
    override.touch(mode=0o640)
    monkeypatch.setenv("SWARM_DB", str(override))
    conn = studio_evidence._db()
    assert conn.execute("pragma database_list").fetchone()[2] == str(override)
    conn.close()
    assert os.stat(override).st_mode & 0o777 == 0o640


def test_studio_ledger_calls_existing_evidence_api_without_html_injection():
    source = (ROOT / "frontend/static/js/views/studio.js").read_text()
    ledger = source.split("function loadStudioTeachingLedger()", 1)[1].split(
        "// Handler for New Proposal", 1)[0]
    assert 'fetch("/api/studio/evidence?limit=100")' in ledger
    assert "data.items" in ledger
    assert "payloadPre.textContent = JSON.stringify(item.payload, null, 2)" in ledger
    assert "innerHTML" not in ledger
    assert "loadStudioTeachingLedger();" in source.split(
        "function loadStudioTeachingLedger()", 1)[0]
