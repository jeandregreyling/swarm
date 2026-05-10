from frontend.terminal import create_app
from utils.db.approvals import create_approval_token, use_approval_token


def test_one_click_notify_approval_link_consumes_token():
    app = create_app()
    token = create_approval_token("notify", "approval-test@example.invalid", "pytest")

    with app.test_client() as client:
        response = client.get(f"/approve/notify/{token}")

    assert response.status_code == 200
    assert b"notification" in response.data.lower()
    assert use_approval_token(token) is None


def test_one_click_approval_rejects_action_mismatch():
    app = create_app()
    token = create_approval_token("ignore", "approval-mismatch@example.invalid", "pytest")

    with app.test_client() as client:
        response = client.get(f"/approve/trust/{token}")

    assert response.status_code == 400
