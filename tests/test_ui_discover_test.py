import pytest
from frontend.app import create_app

# Reuse the enrollment and client fixtures from the existing identity tests
@pytest.fixture
def client():
    """Provide a Flask test client for the application."""
    app = create_app()
    return app.test_client()

@pytest.fixture
def enrolled_agent(client):
    """Enroll a test agent and return its bearer token."""
    resp = client.post("/api/agent/v1/enroll", json={"name": "test-agent"})
    resp.raise_for_status()
    return resp.json["token"]

# Test that an authenticated request to /api/agent/v1/tools returns controls with provenance

def test_ui_discover_with_identity(enrolled_agent, client):
    headers = {"Authorization": f"Bearer {enrolled_agent}"}
    resp = client.get("/api/agent/v1/tools", headers=headers)
    assert resp.status_code == 200, f"Unexpected status {resp.status_code}"
    data = resp.json
    # Expect a list of controls, each with a provenance field
    assert isinstance(data, list), "Response should be a list of controls"
    for ctrl in data:
        assert "provenance" in ctrl, "Control missing provenance"

# Test that a request without identity is denied

def test_ui_discover_without_identity(client):
    resp = client.get("/api/agent/v1/tools")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
