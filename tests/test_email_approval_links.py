from pathlib import Path
import pytest
from frontend.terminal import create_app
from utils.db.approvals import create_approval_token, use_approval_token


def _ensure_tables(db_path: str):
    from utils.db._schema import initialise_database
    initialise_database()


def test_one_click_notify_approval_link_consumes_token(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_test.db'
    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    _ensure_tables(str(db))

    app = create_app()
    token = create_approval_token("notify", "approval-test@example.invalid", "pytest")

    with app.test_client() as client:
        response = client.get(f"/approve/notify/{token}")

    assert response.status_code == 200
    assert b"notification" in response.data.lower()
    assert use_approval_token(token) is None


def test_one_click_approval_rejects_action_mismatch(tmp_path, monkeypatch):
    db = tmp_path / 'swarm_test.db'
    monkeypatch.setenv('SWARM_DB_PATH', str(db))
    _ensure_tables(str(db))

    app = create_app()
    token = create_approval_token("ignore", "approval-mismatch@example.invalid", "pytest")

    with app.test_client() as client:
        response = client.get(f"/approve/trust/{token}")

    assert response.status_code == 400
