import json
from datetime import datetime, timezone

import pytest

from core import watched_topics as topics


def article(title, url="https://example.test/news", snippet="A source-backed update."):
    return {"title": title, "source_url": url, "snippet": snippet, "recency_label": "date unverified"}


def test_newsletter_prioritises_australia_without_relabelling_global_stories():
    rows = [
        article("Technology update", "https://example.test/tech"),
        article("Global SuccessFactors update", "https://example.test/global"),
        article("Australian payroll update", "https://example.test/au"),
    ]
    edition = topics.compose_interest_newsletter("SAP HCM Australia", rows, review_url="http://localhost/ui")
    assert edition["plain"].index("Australian payroll update") < edition["plain"].index("Global SuccessFactors update")
    assert edition["plain"].index("Global SuccessFactors update") < edition["plain"].index("Technology update")
    assert "<table role='presentation'" in edition["html"]
    assert "Editor's note" in edition["plain"]


def test_newsletter_escapes_html_and_rejects_script_links():
    row = article("<img src=x onerror=alert(1)>Payroll", "javascript:alert(1)", "<script>bad</script> <b>Text</b>")
    edition = topics.compose_interest_newsletter("<unsafe>", [row], review_url="javascript:alert(2)")
    assert "<unsafe>" not in edition["html"]
    assert "&lt;unsafe&gt;" in edition["html"]
    assert "javascript:" not in edition["html"]
    assert "<script>" not in edition["html"]
    assert "No Australia-specific" in edition["plain"]


def test_newsletter_does_not_drop_articles_marked_for_notification():
    rows = [article(f"Story {i}", f"https://example.test/{i}") for i in range(10)]
    edition = topics.compose_interest_newsletter("Interests", rows, review_url="http://localhost/ui")
    for row in rows:
        assert row["source_url"] in edition["html"]


def test_local_editor_preserves_source_mapping(monkeypatch):
    from core.seven_llm import llama_server
    from utils import local_runtime_policy

    calls = []
    def chat(model, messages, **kwargs):
        calls.append((model, messages))
        return json.dumps({"articles": [
            {"id": 0, "headline": "Edited headline", "summary": "Edited summary.", "note": "Verify scope."}
        ]}), 50
    monkeypatch.setattr(llama_server, "chat", chat)
    monkeypatch.setattr(local_runtime_policy, "preferred_model_for_agent", lambda agent: "local-test-model")
    row = article("Raw title")
    edited = topics.edit_interest_evidence("SAP HCM", [row])
    assert edited[0]["source_url"] == row["source_url"]
    assert edited[0]["editorial_headline"] == "Edited headline"
    assert calls[0][0] == "local-test-model"
    assert "untrusted data" in calls[0][1][0]["content"]


@pytest.mark.parametrize("payload", [
    {"articles": []},
    {"articles": [{"id": 9, "headline": "x", "summary": "x", "note": "x"}]},
    {"articles": [{"id": 0, "headline": "", "summary": "x", "note": "x"}]},
])
def test_local_editor_rejects_invalid_editions(monkeypatch, payload):
    from core.seven_llm import llama_server
    monkeypatch.setattr(llama_server, "chat", lambda *a, **kw: (json.dumps(payload), 1))
    with pytest.raises(ValueError, match="Newsletter editor"):
        topics.edit_interest_evidence("SAP", [article("Payroll")])


def test_email_is_not_sent_when_editor_fails(monkeypatch):
    from fridays import task_runner
    from lib.email import email_handler
    sent = []
    def fail(*args):
        raise ValueError("Invalid editorial output")
    monkeypatch.setattr(topics, "edit_interest_evidence", fail)
    monkeypatch.setattr(email_handler, "send_reply", lambda **kw: sent.append(kw))
    assert not task_runner._email_research_update(
        topic="SAP", session_id=1, summary="raw dump", evidence=[article("Payroll")],
        recipient="ghost", agent="eight",
    )
    assert sent == []


def test_monthly_sender_uses_and_records_exact_edited_edition(monkeypatch):
    from core import market_watch
    from lib.email import email_handler
    rows = [{"link": "https://example.test/actual", "title": "Edited"}]
    monkeypatch.setattr(market_watch, "write_sap_au_monthly_newsletter", lambda now: {
        "doc_name": "test.html", "month": "2026-10", "email_plain": "Edited plain",
        "email_html": "<p>Edited HTML</p>", "articles": rows,
    })
    sent, recorded = [], []
    monkeypatch.setattr(email_handler, "send_reply", lambda *a, **kw: sent.append((a, kw)) or True)
    monkeypatch.setattr(market_watch, "_record_sent_links", lambda items: recorded.extend(items))
    result = market_watch.send_sap_au_monthly_newsletter(datetime(2026, 10, 22, tzinfo=timezone.utc))
    assert result["ok"]
    assert sent[0][0][2] == "Edited plain"
    assert sent[0][1]["html_body"] == "<p>Edited HTML</p>"
    assert recorded == rows
    assert "October 2026" in result["subject"] and "Outlook" not in result["subject"]


def test_australian_payroll_outranks_general_sap_news():
    from core import market_watch
    assert market_watch._score_sap_au({"title": "Australian payroll changes"}) > market_watch._score_sap_au({"title": "SAP cloud AI HANA S/4HANA ABAP Fiori"})


def test_google_news_items_show_publisher_name():
    from core.watched_topics import compose_interest_newsletter

    edition = compose_interest_newsletter("SAP HCM Australia", [{
        "title": "ATO updates STP guidance - Australian Taxation Office",
        "source_url": "https://news.google.com/rss/articles/abc",
        "editorial_headline": "ATO updates STP guidance",
        "editorial_summary": "Australian payroll guidance changed.",
        "editorial_note": "Check the effective date.",
    }], review_url="http://localhost:5050/ui")
    assert "Australian Taxation Office |" in edition["plain"]
    assert "news.google.com |" not in edition["plain"]
