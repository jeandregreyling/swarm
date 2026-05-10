import subprocess
import sys


def _run_isolated():
    """Run approval-link logic in a fresh Python process so suite-order
    pollution (earlier tests that call create_app() or monkeypatch DB
    state) cannot affect us."""
    code = '''
import sys
sys.path.insert(0, '/home/seven/swarm')
from frontend.terminal import create_app
from utils.db.approvals import create_approval_token, use_approval_token

app = create_app()
token = create_approval_token("notify", "approval-test@example.invalid", "pytest")
with app.test_client() as client:
    response = client.get(f"/approve/notify/{token}")
assert response.status_code == 200, f"got {response.status_code}"
assert b"notification" in response.data.lower()
assert use_approval_token(token) is None
print("OK")
'''
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True, text=True, timeout=15,
    )
    return result


def test_one_click_notify_approval_link_consumes_token():
    result = _run_isolated()
    assert result.returncode == 0, result.stdout + result.stderr


def test_one_click_approval_rejects_action_mismatch():
    code = '''
import sys
sys.path.insert(0, '/home/seven/swarm')
from frontend.terminal import create_app
from utils.db.approvals import create_approval_token
app = create_app()
token = create_approval_token("ignore", "approval-mismatch@example.invalid", "pytest")
with app.test_client() as client:
    response = client.get(f"/approve/trust/{token}")
assert response.status_code == 400, f"got {response.status_code}"
print("OK")
'''
    result = subprocess.run(
        [sys.executable, '-c', code],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
