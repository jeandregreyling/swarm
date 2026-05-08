from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "frontend"))

from terminal import create_app


def test_repo_service_file_uses_project_venv_python():
    service = (ROOT / "swarm-terminal.service").read_text()
    assert "/home/seven/swarm/.venv/bin/python3 /home/seven/swarm/frontend/terminal.py" in service


def test_terminal_health_reports_media_center_blueprint_loaded():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/_health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] in {"healthy", "degraded"}
    assert "media_center_bp" in payload["blueprints_loaded"]
    assert "media_center_bp" not in payload["blueprints_failed"]
