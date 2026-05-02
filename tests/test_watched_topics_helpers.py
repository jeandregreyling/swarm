"""SAP/watched-topic helpers (P-00221285D1).

Covers:
  * S-A8032C5016 — watched-topic UX copy
  * S-AA5F5A23C0 — SAP watcher confidence threshold
  * S-A60F04117B — SAP watcher seed evidence baseline
  * S-3AF5EBCF59 — SAP watcher summary template
  * S-C97E117533 — SAP watcher manual run button (helper)
"""
from __future__ import annotations

import time

import pytest

from core import watched_topics as wt


# ── UX copy ────────────────────────────────────────────────────────────────

def test_copy_for_returns_template_when_no_ctx():
    assert "No watched topics yet" in wt.copy_for("list_empty")


def test_copy_for_substitutes_ctx():
    out = wt.copy_for(
        "manual_run_done", new_count=2, updated_count=1, skipped_count=4
    )
    assert "2 new" in out and "1 updated" in out and "4 below" in out


def test_copy_for_unknown_key_is_safe():
    out = wt.copy_for("does_not_exist_at_all")
    assert "missing copy" in out


def test_copy_for_missing_field_is_safe():
    out = wt.copy_for("manual_run_done")  # template requires fields
    assert "missing field" in out


# ── Confidence threshold ───────────────────────────────────────────────────

@pytest.mark.parametrize("score, band", [
    (0.95, "high"),
    (0.70, "high"),
    (0.69, "borderline"),
    (0.45, "borderline"),
    (0.44, "low"),
    (0.0, "low"),
    (-0.5, "low"),
    (1.5, "low"),
    (float("nan"), "low"),
])
def test_confidence_band_table(score, band):
    assert wt.confidence_band(score) == band


def test_confidence_band_handles_garbage():
    assert wt.confidence_band("not a number") == "low"
    assert wt.confidence_band(None) == "low"


def test_should_notify_only_for_borderline_and_high():
    assert wt.should_notify(0.9) is True
    assert wt.should_notify(0.5) is True
    assert wt.should_notify(0.2) is False
    assert wt.should_notify(0.0) is False


# ── Seed baseline ──────────────────────────────────────────────────────────

def test_seed_baseline_for_returns_anchors():
    rows = wt.seed_baseline_for("sap_news_au", now=1_700_000_000)
    assert rows
    assert all(r["topic_key"] == "sap_news_au" for r in rows)
    assert all(r["is_historical"] == 1 for r in rows)
    # Anchors are ~30 days in the past so they don't get displayed as new.
    assert all(r["created_at"] < 1_700_000_000 - 28 * 86400 for r in rows)


def test_seed_baseline_dedupes_overlapping_terms():
    rows = wt.seed_baseline_for(
        "sap-news", anchor_terms=["sap-news", "sap-news", "sap news"]
    )
    slugs = {r["evidence_url"] for r in rows}
    # underscore vs dash vs space should converge to two unique slugs
    assert len(slugs) == 2


def test_seed_baseline_empty_topic_returns_empty():
    assert wt.seed_baseline_for("") == []


# ── Summary template ───────────────────────────────────────────────────────

def test_render_summary_no_hits():
    out = wt.render_summary(
        "topic_x", since_human="yesterday", now_human="now", hits=[],
    )
    assert "topic_x" in out
    assert "No new evidence" in out


def test_render_summary_with_hits():
    hits = [
        {"title": "Big news", "evidence_url": "https://a.example/1", "score": 0.82},
        {"title": "Smaller item", "evidence_url": "https://b.example/2", "score": 0.55},
    ]
    out = wt.render_summary(
        "topic_y", since_human="2026-05-01 00:00", now_human="2026-05-02 00:00",
        hits=hits, new_count=1, updated_count=1,
    )
    assert "topic_y" in out
    assert "Big news" in out
    assert "Smaller item" in out
    assert "0.82" in out
    assert "Confidence: high" in out
    assert "new: 1" in out


# ── Manual-run payload ─────────────────────────────────────────────────────

def test_manual_run_payload_shape():
    p = wt.manual_run_payload("sap_news_au")
    assert p["task_kind"] == "watched_topic"
    assert p["topic_key"] == "sap_news_au"
    assert p["trigger"] == "manual"
    assert isinstance(p["requested_at"], float)


def test_manual_run_payload_rejects_empty_topic():
    with pytest.raises(ValueError):
        wt.manual_run_payload("")
