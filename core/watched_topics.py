"""core.watched_topics — small helpers around the SAP/watched-topic stack.

Each function here corresponds to one low-risk story in P-00221285D1
that needed an explicit, testable surface so other modules and the
Studio UI can consume them without re-implementing copy or thresholds.

Stories:
  * S-A8032C5016 — watched-topic UX copy (single source of truth)
  * S-A60F04117B — SAP watcher seed evidence baseline
  * S-AA5F5A23C0 — SAP watcher confidence threshold
  * S-3AF5EBCF59 — SAP watcher summary template
  * S-C97E117533 — SAP watcher manual run button (helper only;
                   the UI button calls this from Tasker run-now)
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Optional


# ── S-A8032C5016 — UX copy ──────────────────────────────────────────────────

# Single source of truth for watched-topic surfaces. Templates use
# ``str.format(**ctx)`` so callers can substitute without mangling copy.
UX_COPY: Dict[str, str] = {
    "list_empty":
        "No watched topics yet. Add one to start tracking news and "
        "evidence — Seven will summarise hits at your chosen cadence.",
    "card_subtitle":
        "Watched topic · {cadence_human} · last hit {last_hit_human}",
    "manual_run_button":
        "Run now",
    "manual_run_running":
        "Checking sources… this usually takes under a minute.",
    "manual_run_done":
        "Done — {new_count} new, {updated_count} updated, "
        "{skipped_count} below threshold.",
    "manual_run_no_results":
        "No new evidence. Sources are quiet for this topic.",
    "confidence_low":
        "Low confidence — Seven will hold this until corroborated.",
    "confidence_borderline":
        "Borderline — single source, needs a second corroborating hit.",
    "confidence_high":
        "Strong signal — multiple independent sources agree.",
    "digest_intro":
        "Here's what changed for **{topic_key}** since {since_human}:",
}


def copy_for(key: str, **ctx: Any) -> str:
    """Look up a UX copy key and apply ``ctx``. Unknown key returns a
    safe placeholder so missing copy never crashes the surface."""
    template = UX_COPY.get(key)
    if not template:
        return f"[missing copy: {key}]"
    try:
        return template.format(**ctx)
    except (KeyError, IndexError) as e:
        missing = e.args[0] if e.args else "?"
        return f"{template}  [missing field: {missing}]"


# ── S-AA5F5A23C0 — confidence threshold ────────────────────────────────────

# Thresholds chosen so a single weak hit (~0.3) is held, two independent
# hits (~0.5 each → averaged ~0.5) is "borderline", and three hits or one
# strong hit (≥0.7) is "high". Adjust by editing this table only.
CONFIDENCE_BANDS: List[tuple[float, str]] = [
    (0.70, "high"),
    (0.45, "borderline"),
    (0.0,  "low"),
]


def confidence_band(score: float) -> str:
    """Map a numeric confidence score (0..1) to a UX-stable band.

    S-AA5F5A23C0 — keeps the watcher's thresholding logic in one place.
    """
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "low"
    if s != s or s < 0 or s > 1:  # NaN / out of range
        return "low"
    for cutoff, band in CONFIDENCE_BANDS:
        if s >= cutoff:
            return band
    return "low"


def should_notify(score: float) -> bool:
    """Return True when the watcher should send a notification for this
    score. 'low' is suppressed; 'borderline' and 'high' notify."""
    return confidence_band(score) in ("borderline", "high")


# ── S-A60F04117B — seed evidence baseline ──────────────────────────────────

# A watched topic with zero prior evidence is statistically a cold-start:
# every hit looks novel, so we'd spam the user. The baseline adds a few
# synthetic "already seen" anchors (topic-key strings + an old timestamp)
# so the dedupe layer suppresses obvious self-references on day one.

def seed_baseline_for(topic_key: str, *, anchor_terms: Optional[Iterable[str]] = None,
                       now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Return a list of evidence rows that should be inserted as the
    baseline for *topic_key*. Caller is responsible for INSERTing —
    this function only describes the shape so it can be unit-tested
    without a database.
    """
    if not topic_key:
        return []
    base_ts = float(now if now is not None else time.time()) - 30 * 86400
    rows: List[Dict[str, Any]] = []
    seen = set()
    for term in (anchor_terms or [topic_key, topic_key.replace('_', ' '),
                                   topic_key.replace('-', ' ')]):
        slug = (term or '').strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        rows.append({
            "topic_key": topic_key,
            "evidence_url": f"seed://{topic_key}/{slug}",
            "title": f"baseline anchor: {slug}",
            "snippet": "",
            "score": 0.0,
            "confidence_band": "low",
            "is_historical": 1,
            "created_at": base_ts,
        })
    return rows


# ── S-3AF5EBCF59 — summary template ─────────────────────────────────────────

# Plain-text summary template for digest emails / Discord posts. Kept
# intentionally minimal so different channels can wrap it.
SUMMARY_TEMPLATE = (
    "Watched topic: {topic_key}\n"
    "Window: {since_human} → {now_human}\n"
    "Hits: {hit_count}  ·  new: {new_count}  ·  updated: {updated_count}\n"
    "Confidence: {band}  ·  top score: {top_score:.2f}\n"
    "\n"
    "Top items:\n"
    "{top_items_block}\n"
    "\n"
    "— Seven"
)


def render_summary(
    topic_key: str,
    *,
    since_human: str,
    now_human: str,
    hits: List[Dict[str, Any]],
    new_count: int = 0,
    updated_count: int = 0,
) -> str:
    """Render a digest-style summary for a watched topic.

    S-3AF5EBCF59 — single template so email + Discord + UI cards stay
    in sync. ``hits`` is a list of evidence rows (best-first); only the
    top 5 are shown in the body.
    """
    if not hits:
        return (
            f"Watched topic: {topic_key}\n"
            f"Window: {since_human} → {now_human}\n"
            f"No new evidence in this window.\n\n— Seven"
        )
    top_items = []
    for h in hits[:5]:
        title = (h.get("title") or h.get("evidence_url") or "(untitled)").strip()
        url = (h.get("evidence_url") or "").strip()
        score = float(h.get("score") or 0.0)
        top_items.append(f"  • [{score:.2f}] {title}\n    {url}".rstrip())
    top_score = max(float(h.get("score") or 0.0) for h in hits)
    return SUMMARY_TEMPLATE.format(
        topic_key=topic_key,
        since_human=since_human,
        now_human=now_human,
        hit_count=len(hits),
        new_count=new_count,
        updated_count=updated_count,
        band=confidence_band(top_score),
        top_score=top_score,
        top_items_block="\n".join(top_items),
    )


# ── S-C97E117533 — manual-run trigger (helper) ─────────────────────────────

def manual_run_payload(topic_key: str) -> Dict[str, Any]:
    """Return the payload the Studio "Run now" button should POST to
    the Tasker run-now endpoint. Encapsulates the request shape so the
    UI doesn't have to hard-code keys.

    S-C97E117533 — the actual button lives in the Studio UI; this
    helper guarantees the payload contract.
    """
    if not topic_key:
        raise ValueError("topic_key required")
    return {
        "task_kind": "watched_topic",
        "topic_key": str(topic_key),
        "trigger": "manual",
        "requested_at": time.time(),
    }


__all__ = [
    "UX_COPY", "copy_for",
    "CONFIDENCE_BANDS", "confidence_band", "should_notify",
    "seed_baseline_for",
    "SUMMARY_TEMPLATE", "render_summary", "render_summary_html",
    "manual_run_payload",
]


# ── STEP-SAP-NEWSLETTER-RICH-MEDIA-20260430 — rich HTML digest ───────────────
# The plain-text render_summary stays the source of truth for email/Discord
# fallbacks. This HTML variant adds source thumbnails, host badges, and a
# card layout so the in-app SAP/watched-topic newsletter is readable at a
# glance instead of a bare list of links.

def _favicon_url(evidence_url: str) -> str:
    if not evidence_url:
        return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(evidence_url).netloc
        if not host:
            return ""
        return f"https://www.google.com/s2/favicons?domain={host}&sz=64"
    except Exception:
        return ""


def render_summary_html(
    topic_key: str,
    *,
    since_human: str,
    now_human: str,
    hits: List[Dict[str, Any]],
    new_count: int = 0,
    updated_count: int = 0,
    header_image: str = "",
) -> str:
    """Render a card-layout HTML digest for a watched topic.

    ``header_image`` is an optional Media Center asset URL — when supplied
    it becomes the digest banner. Each hit card shows its thumbnail (from
    ``hit['thumbnail']`` / ``hit['image_url']`` / favicon fallback), title,
    host, score badge, and an open-in-new-tab link.
    """
    import html as _html
    if not hits:
        return (
            f"<div class='wt-digest wt-digest-empty'>"
            f"<h3>{_html.escape(topic_key)}</h3>"
            f"<p style='color:#888;'>No new evidence in window "
            f"{_html.escape(since_human)} → {_html.escape(now_human)}.</p>"
            f"</div>"
        )
    top_score = max(float(h.get("score") or 0.0) for h in hits)
    band = confidence_band(top_score)
    band_color = {"high": "#4caf50", "medium": "#f59e0b", "low": "#888"}.get(band, "#888")
    cards: List[str] = []
    for h in hits[:8]:
        title = _html.escape((h.get("title") or h.get("evidence_url") or "(untitled)").strip())
        url = _html.escape((h.get("evidence_url") or "").strip())
        score = float(h.get("score") or 0.0)
        thumb = (h.get("thumbnail") or h.get("image_url") or "").strip()
        if not thumb:
            thumb = _favicon_url(url)
        try:
            from urllib.parse import urlparse
            host = urlparse(url).netloc if url else ""
        except Exception:
            host = ""
        thumb_html = (
            f"<img src='{_html.escape(thumb)}' alt='' loading='lazy' "
            f"style='width:56px;height:56px;border-radius:6px;object-fit:cover;flex:0 0 56px;background:#222;'>"
            if thumb else
            "<div style='width:56px;height:56px;border-radius:6px;background:#222;flex:0 0 56px;'></div>"
        )
        cards.append(
            f"<a href='{url}' target='_blank' rel='noopener' "
            f"style='display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid #333;border-radius:8px;text-decoration:none;color:inherit;background:#15171b;'>"
            f"{thumb_html}"
            f"<div style='flex:1;min-width:0;'>"
            f"<div style='font-weight:600;font-size:13px;color:#dde;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{title}</div>"
            f"<div style='font-size:10px;color:#888;margin-top:2px;'>{_html.escape(host)} · score {score:.2f}</div>"
            f"</div>"
            f"</a>"
        )
    header = (
        f"<img src='{_html.escape(header_image)}' alt='' "
        f"style='width:100%;max-height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px;'>"
        if header_image else ""
    )
    return (
        f"<div class='wt-digest' style='font-family:system-ui,sans-serif;color:#dde;max-width:680px;'>"
        f"{header}"
        f"<h3 style='margin:0 0 4px;'>{_html.escape(topic_key)}</h3>"
        f"<div style='font-size:11px;color:#888;margin-bottom:10px;'>"
        f"{_html.escape(since_human)} → {_html.escape(now_human)} · "
        f"<span style='color:{band_color};font-weight:600;'>{band.upper()}</span> · "
        f"hits {len(hits)} · new {new_count} · updated {updated_count}"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;gap:6px;'>"
        + "".join(cards)
        + f"</div>"
        f"<div style='margin-top:10px;font-size:10px;color:#666;'>— Seven</div>"
        f"</div>"
    )
