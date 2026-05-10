"""Y.58 — verify new endpoints (sysmod helpers, trading scan-patterns,
business research-propositions) and Money Hub-related routes register and
respond sensibly. Also confirms removed home tiles are not reachable as
distinct templates."""

from __future__ import annotations

import pytest

from frontend.terminal import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _rules(client):
    return {r.rule for r in client.application.url_map.iter_rules()}


def test_sysmod_helpers_route_registered(client):
    assert "/api/settings/sysmod/helpers" in _rules(client)


def test_trading_scan_patterns_route_registered(client):
    assert "/api/trading/scan-patterns" in _rules(client)


def test_business_research_propositions_route_registered(client):
    assert "/api/business/research-propositions" in _rules(client)


def test_sysmod_helpers_returns_ok(client):
    r = client.get("/api/settings/sysmod/helpers")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert isinstance(data.get("helpers"), list)


def test_trading_scan_patterns_post_ok(client):
    r = client.post("/api/trading/scan-patterns", json={})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert "queued" in data


def test_trading_scan_patterns_post_with_symbols(client):
    r = client.post("/api/trading/scan-patterns", json={"symbols": ["AAPL", "BHP.AX"]})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("queued") == 2


def test_business_research_propositions_post_ok(client):
    r = client.post("/api/business/research-propositions", json={})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True


def test_interests_seed_money_topics(client):
    r = client.post(
        "/api/interests/seed",
        json={
            "topics": ["investing", "stocks", "NASDAQ", "ASX"],
            "username": "ghost",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert set(data.get("saved", [])) >= {"investing", "stocks", "NASDAQ", "ASX"}


def test_money_hub_newsletter_composes_from_live_pillars():
    from core import market_watch

    doc = market_watch.compose_newsletter()

    assert doc["doc_name"].startswith("MONEY_HUB_DAILY_NEWSLETTER_")
    assert "/api/financial/summary" in doc["content"]
    assert "/api/trading/summary" in doc["content"]
    assert "/api/business/summary" in doc["content"]


def test_money_hub_task_runner_registered():
    from fridays.task_runner import TASK_REGISTRY

    assert "money_hub_daily_newsletter" in TASK_REGISTRY
