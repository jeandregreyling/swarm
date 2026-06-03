"""Money Hub newsletter quality checks."""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3


def test_daily_newsletter_explains_empty_sections_and_links(monkeypatch):
    from core import market_watch

    monkeypatch.setattr(market_watch, "_summary_payload", lambda: {
        "financial": {"open": 0, "by_class": {}, "high_conviction": []},
        "trading": {"open": 0, "by_side": {"buy": 0, "sell": 0}, "realised_pnl": 0, "top": []},
        "business": {"unreconciled": 0, "net_by_currency": {}, "by_kind": {}, "recent": []},
    })
    monkeypatch.setattr(market_watch, "_collect_app_center_snapshot", lambda: {
        "project_count": 0,
        "active_count": 0,
        "build_count": 0,
        "latest_projects": [],
        "latest_builds": [],
        "ready": True,
        "reason": "App Center is initialized.",
    })
    monkeypatch.setattr(market_watch, "_collect_potato_farm_snapshot", lambda now: {
        "ok": True,
        "nodes": [],
        "jobs": [],
        "live_count": 0,
        "stale_count": 4,
        "pending_jobs": 1,
        "completed_jobs": 0,
        "reason": "0 live node(s), 4 stale/offline expected node(s), 1 pending handoff(s), 0 recent completed handoff(s).",
    })
    monkeypatch.setattr(market_watch, "_collect_recent_evidence", lambda: [])
    monkeypatch.setattr(market_watch, "_collect_kc_interest_snapshot", lambda: {
        "interests": [{"topic": "SAP Australia", "category": "work", "score": 9.0, "source_agent": "eight"}],
        "watched_tasks": [{"name": "sap_au_watch", "schedule": "daily 06:30", "next_run": "2026-05-28 06:30:00"}],
        "docs": [{"doc_name": "SAP_AU_MONTHLY_NEWSLETTER_2026-05.html", "tags": "sap,newsletter"}],
        "settings_count": 0,
        "interest_count": 1,
        "watched_task_count": 1,
    })

    doc = market_watch.compose_newsletter(datetime(2026, 5, 27, tzinfo=timezone.utc))
    content = doc["content"]

    assert "## Why Check Today" in content
    assert "## Open Sections" in content
    assert "[App Center](/ui)" in content
    assert "[Potato Farm](/ui)" in content
    assert "No live open work is registered" in content
    assert "pending handoff" in content
    assert "Recent projects: none" in content
    assert "[nodes API](/api/hive/nodes)" in content
    assert "## KC Interests" in content
    assert "SAP Australia" in content
    assert "sap_au_watch" in content


def test_daily_newsletter_defaults_to_operator_local_day(monkeypatch):
    from datetime import timedelta, timezone

    from core import market_watch

    monkeypatch.setattr(market_watch, "_summary_payload", lambda: {
        "financial": {"open": 0, "by_class": {}, "high_conviction": []},
        "trading": {"open": 0, "by_side": {}, "realised_pnl": 0, "top": []},
        "business": {"unreconciled": 0, "net_by_currency": {}, "by_kind": {}, "recent": []},
    })
    monkeypatch.setattr(market_watch, "_collect_app_center_snapshot", lambda: {
        "project_count": 0,
        "active_count": 0,
        "build_count": 0,
        "latest_projects": [],
        "latest_builds": [],
        "ready": True,
        "reason": "App Center is initialized.",
    })
    monkeypatch.setattr(market_watch, "_collect_potato_farm_snapshot", lambda now: {
        "ok": True,
        "nodes": [],
        "jobs": [],
        "live_count": 0,
        "stale_count": 0,
        "pending_jobs": 0,
        "completed_jobs": 0,
        "reason": "empty test farm",
    })
    monkeypatch.setattr(market_watch, "_collect_recent_evidence", lambda: [])
    monkeypatch.setattr(market_watch, "_collect_kc_interest_snapshot", lambda: {
        "interests": [],
        "watched_tasks": [],
        "docs": [],
        "settings_count": 0,
        "interest_count": 0,
        "watched_task_count": 0,
    })
    monkeypatch.setattr(
        market_watch,
        "_local_now",
        lambda: datetime(2026, 6, 4, 6, 24, tzinfo=timezone(timedelta(hours=10))),
    )

    doc = market_watch.compose_newsletter()

    assert doc["day"] == "2026-06-04"
    assert doc["doc_name"] == "MONEY_HUB_DAILY_NEWSLETTER_2026-06-04.md"


def test_visual_money_hub_email_has_action_cards(monkeypatch):
    from core import market_watch

    monkeypatch.setattr(market_watch, "_summary_payload", lambda: {
        "financial": {"open": 0, "by_class": {}, "high_conviction": []},
        "trading": {"open": 0, "by_side": {}, "realised_pnl": 0, "top": []},
        "business": {"unreconciled": 0, "net_by_currency": {}, "by_kind": {}, "recent": []},
    })
    monkeypatch.setattr(market_watch, "_collect_app_center_snapshot", lambda: {
        "project_count": 0,
        "active_count": 0,
        "build_count": 0,
        "latest_projects": [],
        "latest_builds": [],
        "ready": True,
        "reason": "App Center is initialized.",
    })
    monkeypatch.setattr(market_watch, "_collect_potato_farm_snapshot", lambda now: {
        "ok": True,
        "nodes": [],
        "jobs": [],
        "live_count": 1,
        "stale_count": 4,
        "pending_jobs": 1,
        "completed_jobs": 0,
        "reason": "1 live, 4 stale, 1 pending.",
    })
    monkeypatch.setattr(market_watch, "_collect_recent_evidence", lambda: [])
    monkeypatch.setattr(market_watch, "_collect_kc_interest_snapshot", lambda: {
        "interests": [{"topic": "SAP payroll Australia", "category": "work", "score": 9.0}],
        "watched_tasks": [{"name": "sap_payroll_au_watch", "next_run": "2026-05-28 06:30:00"}],
        "docs": [],
        "settings_count": 1,
        "interest_count": 1,
        "watched_task_count": 1,
    })

    doc = market_watch.compose_money_hub_email()

    assert "Money Hub" in doc["subject"]
    assert "THE MOVES" in doc["html"]
    assert "KC INTEREST QUEUE" in doc["html"]
    assert "SAP payroll Australia" in doc["html"]
    assert "Harvest SAP signals" in doc["plain"]


def test_visual_money_hub_email_summarises_evidence_links(monkeypatch):
    from core import market_watch

    monkeypatch.setattr(market_watch, "_summary_payload", lambda: {
        "financial": {"open": 0, "by_class": {}, "high_conviction": []},
        "trading": {"open": 0, "by_side": {}, "realised_pnl": 0, "top": []},
        "business": {"unreconciled": 0, "net_by_currency": {}, "by_kind": {}, "recent": []},
    })
    monkeypatch.setattr(market_watch, "_collect_app_center_snapshot", lambda: {
        "project_count": 1,
        "active_count": 1,
        "build_count": 1,
        "latest_projects": [],
        "latest_builds": [],
        "ready": True,
        "reason": "App Center is initialized.",
    })
    monkeypatch.setattr(market_watch, "_collect_potato_farm_snapshot", lambda now: {
        "ok": True,
        "nodes": [],
        "jobs": [],
        "live_count": 1,
        "stale_count": 0,
        "pending_jobs": 0,
        "completed_jobs": 0,
        "reason": "1 live.",
    })
    monkeypatch.setattr(market_watch, "_collect_recent_evidence", lambda: [{
        "topic": "SAP payroll Australia",
        "topic_key": "sap_payroll_au_watch",
        "title": "Payday Super: What Payroll Teams Need to Know",
        "source_url": "https://example.test/payday-super",
        "snippet": "Industries with high turnover, variable rosters, or weekly pay cycles will be hit hardest. SAP payroll teams need to manage super contributions in sync with every pay run.",
        "quality_score": 0.59,
        "novelty_score": 1.0,
        "qualified": 1,
        "notified": 0,
    }])
    monkeypatch.setattr(market_watch, "_collect_kc_interest_snapshot", lambda: {
        "interests": [{"topic": "SAP payroll Australia", "category": "work", "score": 9.0}],
        "watched_tasks": [{"name": "sap_payroll_au_watch", "next_run": "2026-05-28 06:30:00"}],
        "docs": [],
        "settings_count": 1,
        "interest_count": 1,
        "watched_task_count": 1,
    })

    doc = market_watch.compose_money_hub_email(datetime(2026, 5, 27, tzinfo=timezone.utc))

    assert "What is inside:" in doc["html"]
    assert "Industries with high turnover" in doc["html"]
    assert "Why it matters:" in doc["html"]
    assert "Read if:" in doc["html"]
    assert "Evidence briefs:" in doc["plain"]
    assert "Payroll/compliance signal" in doc["plain"]


def test_recent_evidence_filters_old_and_already_sent_items(tmp_path, monkeypatch):
    from core import market_watch

    db = tmp_path / "money_hub.db"

    def connect():
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(market_watch, "get_connection", connect)
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE watched_topic_evidence (
            id INTEGER PRIMARY KEY,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            title TEXT DEFAULT '',
            snippet TEXT DEFAULT '',
            quality_score REAL DEFAULT 0,
            novelty_score REAL DEFAULT 0,
            qualified INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0,
            evidence_date TEXT DEFAULT '',
            recency_score REAL DEFAULT 0,
            recency_label TEXT DEFAULT '',
            is_historical INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO watched_topic_evidence
            (id, topic_key, topic, evidence_fingerprint, source_url, title, snippet, quality_score, novelty_score, qualified, evidence_date, created_at)
        VALUES
            (1, 'sap', 'SAP payroll Australia', 'a', 'https://old.test/a', 'Old payroll video', 'posted 2 years ago', 0.9, 1.0, 1, '2024-01-01', '2026-05-27 07:00:00'),
            (2, 'sap', 'SAP payroll Australia', 'b', 'https://sent.test/b', 'Already sent fresh item', 'Fresh payroll update', 0.9, 1.0, 1, '2026-05-27', '2026-05-27 07:01:00'),
            (3, 'sap', 'SAP payroll Australia', 'c', 'https://fresh.test/c', 'Fresh payday super item', 'Payday super update for payroll teams', 0.9, 1.0, 1, '2026-05-27', '2026-05-27 07:02:00');
        """
    )
    market_watch.ensure_newsletter_feedback_schema(conn)
    conn.execute(
        "INSERT INTO money_hub_sent_items (evidence_id, source_url, title, topic, newsletter_day) VALUES (?,?,?,?,?)",
        (2, "https://sent.test/b", "Already sent fresh item", "SAP payroll Australia", "2026-05-27"),
    )
    conn.commit()
    conn.close()

    items = market_watch._collect_recent_evidence(
        now=datetime(2026, 5, 27, tzinfo=timezone.utc)
    )

    assert [item["id"] for item in items] == [3]


def test_newsletter_feedback_updates_interest_score(tmp_path, monkeypatch):
    from core import market_watch

    db = tmp_path / "feedback.db"

    def connect():
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(market_watch, "get_connection", connect)
    monkeypatch.setattr(market_watch, "write_knowledge", lambda *args, **kwargs: None)
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE watched_topic_evidence (
            id INTEGER PRIMARY KEY,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            title TEXT DEFAULT '',
            snippet TEXT DEFAULT '',
            review_status TEXT DEFAULT '',
            review_note TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE user_interests (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL DEFAULT 'ghost',
            topic TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            source TEXT DEFAULT 'user',
            score REAL DEFAULT 10.0,
            active INTEGER DEFAULT 1,
            source_agent TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(username, topic)
        );
        INSERT INTO watched_topic_evidence
            (id, topic_key, topic, evidence_fingerprint, source_url, title)
        VALUES
            (7, 'sap', 'SAP payroll Australia', 'fp', 'https://fresh.test/article', 'Fresh article');
        INSERT INTO user_interests (username, topic, category, source, score, active)
        VALUES ('ghost', 'SAP payroll Australia', 'watched_research', 'tasker', 9.0, 1);
        """
    )
    conn.commit()
    conn.close()

    result = market_watch.record_newsletter_article_feedback(7, "up")

    conn = connect()
    interest = conn.execute(
        "SELECT score, source, source_agent FROM user_interests WHERE topic='SAP payroll Australia'"
    ).fetchone()
    evidence = conn.execute(
        "SELECT review_status FROM watched_topic_evidence WHERE id=7"
    ).fetchone()
    feedback_count = conn.execute("SELECT COUNT(*) FROM newsletter_article_feedback").fetchone()[0]
    conn.close()

    assert result["ok"] is True
    assert interest["score"] == 10.5
    assert interest["source"] == "newsletter_feedback"
    assert interest["source_agent"] == "money_hub"
    assert evidence["review_status"] == "liked"
    assert feedback_count == 1
