"""Money Hub newsletter generation.

Builds a local-first market/business digest from the live Financial, Trading,
and Business pillar summaries, then stores it in Knowledge Center surfaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import os
import re
import sqlite3
import urllib.request
from typing import Any
from urllib.parse import urlencode, urlparse, urljoin

from utils.db._connection import get_connection
from utils.db.knowledge import write_knowledge

_OG_IMAGE_CACHE: dict[str, str] = {}
_MONEY_HUB_SENT_ITEMS_DDL = (
    "CREATE TABLE IF NOT EXISTS money_hub_sent_items ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "evidence_id INTEGER, "
    "source_url TEXT NOT NULL, "
    "title TEXT DEFAULT '', "
    "topic TEXT DEFAULT '', "
    "newsletter_day TEXT NOT NULL, "
    "sent_at TEXT DEFAULT (datetime('now')), "
    "UNIQUE(source_url, newsletter_day))"
)
_NEWSLETTER_FEEDBACK_DDL = (
    "CREATE TABLE IF NOT EXISTS newsletter_article_feedback ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "evidence_id INTEGER, "
    "source_url TEXT DEFAULT '', "
    "topic TEXT DEFAULT '', "
    "vote TEXT NOT NULL, "
    "created_at TEXT DEFAULT (datetime('now')), "
    "note TEXT DEFAULT '')"
)


def _local_now() -> datetime:
    """Return the operator-local time for dated KC artifacts."""
    return datetime.now().astimezone()


def _fetch_og_image(url: str, timeout: float = 4.0) -> str:
    """Best-effort fetch of an article's og:image / twitter:image for inbox visuals."""
    if not url:
        return ""
    if url in _OG_IMAGE_CACHE:
        return _OG_IMAGE_CACHE[url]
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (SwarmKC newsletter)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(120_000).decode("utf-8", errors="ignore")
    except Exception:
        _OG_IMAGE_CACHE[url] = ""
        return ""
    found = ""
    for pattern in (
        r'<meta[^>]+property=["\\\']og:image["\\\'][^>]+content=["\\\']([^"\\\']+)',
        r'<meta[^>]+name=["\\\']twitter:image["\\\'][^>]+content=["\\\']([^"\\\']+)',
        r'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+property=["\\\']og:image',
    ):
        m = re.search(pattern, raw, flags=re.IGNORECASE)
        if m:
            found = m.group(1).strip()
            break
    if found and found.startswith("//"):
        found = "https:" + found
    if found and found.startswith("/"):
        try:
            found = urljoin(url, found)
        except Exception:
            pass
    _OG_IMAGE_CACHE[url] = found
    return found


DOC_PREFIX = "MONEY_HUB_DAILY_NEWSLETTER"
TASK_NAME = "money_hub_daily_newsletter"
SAP_AU_DOC_PREFIX = "SAP_AU_MONTHLY_NEWSLETTER"
SAP_AU_TASK_NAME = "sap_au_monthly_newsletter"

_SAP_AU_DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
    ("SAP News", "https://news.sap.com/feed/"),
    ("Google News \u2014 SAP Australia", "https://news.google.com/rss/search?q=SAP+Australia&hl=en-AU&gl=AU&ceid=AU:en"),
    ("Google News \u2014 SAP S/4HANA", "https://news.google.com/rss/search?q=SAP+S%2F4HANA&hl=en-AU&gl=AU&ceid=AU:en"),
    ("Google News \u2014 ATO Payroll STP", "https://news.google.com/rss/search?q=ATO+payroll+single+touch+payroll&hl=en-AU&gl=AU&ceid=AU:en"),
    ("Google News \u2014 AU Enterprise IT", "https://news.google.com/rss/search?q=Australia+enterprise+software+OR+ERP&hl=en-AU&gl=AU&ceid=AU:en"),
    ("Google News \u2014 AU Cyber Compliance", "https://news.google.com/rss/search?q=Australia+cyber+security+compliance+enterprise&hl=en-AU&gl=AU&ceid=AU:en"),
)


_SENT_LINKS_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS sap_au_sent_links ("
    "link TEXT PRIMARY KEY, title TEXT, first_sent_at TEXT DEFAULT (datetime('now')))"
)


def _load_sent_links() -> set[str]:
    conn = get_connection()
    try:
        conn.execute(_SENT_LINKS_TABLE_DDL)
        rows = conn.execute("SELECT link FROM sap_au_sent_links").fetchall()
        return {str(r[0]) for r in rows if r and r[0]}
    finally:
        conn.close()


def _record_sent_links(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    conn = get_connection()
    try:
        conn.execute(_SENT_LINKS_TABLE_DDL)
        conn.executemany(
            "INSERT OR IGNORE INTO sap_au_sent_links (link, title) VALUES (?, ?)",
            [(it.get("link") or "", it.get("title") or "") for it in items if it.get("link")],
        )
        conn.commit()
    finally:
        conn.close()


def _parse_evidence_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"undated", "unknown", "none"}:
        return None
    raw = raw.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            dt = datetime.strptime(raw[:19] if fmt.endswith("%S") else raw[:10], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _looks_historical(text: str, now: datetime) -> bool:
    blob = (text or "").lower()
    if re.search(r"\b(?:[2-9]|[1-9]\d+)\s+years?\s+ago\b", blob):
        return True
    current_year = now.year
    for m in re.finditer(r"\b(20\d{2})\b", blob):
        try:
            if current_year - int(m.group(1)) >= 2:
                return True
        except ValueError:
            continue
    return False


def _evidence_is_fresh(item: dict[str, Any], now: datetime, *, max_age_days: int = 45) -> tuple[bool, str]:
    if int(item.get("is_historical") or 0):
        return False, "marked historical"
    text = " ".join(str(item.get(k) or "") for k in ("title", "snippet", "reason", "evidence_date", "recency_label"))
    if _looks_historical(text, now):
        return False, "content appears years old"
    evidence_dt = _parse_evidence_datetime(item.get("evidence_date"))
    if evidence_dt:
        age = now - evidence_dt.astimezone(timezone.utc)
        if age > timedelta(days=max_age_days):
            return False, f"evidence date older than {max_age_days} days"
    else:
        label = str(item.get("recency_label") or "").lower()
        score = float(item.get("recency_score") or 0)
        if any(k in label for k in ("old", "historical", "stale")):
            return False, "recency label is stale"
        if score < 0.85 and not any(k in label for k in ("today", "fresh", "recent", "this week")):
            return False, "missing a current evidence date"
    return True, "fresh"


def _load_money_hub_sent_urls(conn: sqlite3.Connection) -> set[str]:
    ensure_newsletter_feedback_schema(conn)
    rows = conn.execute("SELECT source_url FROM money_hub_sent_items").fetchall()
    return {str(r[0]) for r in rows if r and r[0]}


def _record_money_hub_sent_evidence(items: list[dict[str, Any]], newsletter_day: str) -> None:
    if not items:
        return
    conn = get_connection()
    try:
        ensure_newsletter_feedback_schema(conn)
        conn.executemany(
            "INSERT OR IGNORE INTO money_hub_sent_items "
            "(evidence_id, source_url, title, topic, newsletter_day) VALUES (?,?,?,?,?)",
            [
                (
                    int(it.get("id") or 0),
                    str(it.get("source_url") or ""),
                    str(it.get("title") or ""),
                    str(it.get("topic") or it.get("topic_key") or ""),
                    newsletter_day,
                )
                for it in items
                if it.get("source_url")
            ],
        )
        conn.commit()
    finally:
        conn.close()


def record_newsletter_article_feedback(evidence_id: int, vote: str, note: str = "") -> dict[str, Any]:
    vote = (vote or "").strip().lower()
    if vote not in {"up", "down"}:
        raise ValueError("vote must be up or down")
    conn = get_connection()
    try:
        ensure_newsletter_feedback_schema(conn)
        row = conn.execute(
            "SELECT id, topic, topic_key, title, source_url FROM watched_topic_evidence WHERE id=?",
            (int(evidence_id),),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "evidence not found", "evidence_id": int(evidence_id)}
        item = dict(row)
        topic = str(item.get("topic") or item.get("topic_key") or "").strip()
        source_url = str(item.get("source_url") or "")
        conn.execute(
            "INSERT INTO newsletter_article_feedback (evidence_id, source_url, topic, vote, note) VALUES (?,?,?,?,?)",
            (int(evidence_id), source_url, topic, vote, note or ""),
        )
        conn.execute(
            "UPDATE watched_topic_evidence SET review_status=?, review_note=?, updated_at=datetime('now') WHERE id=?",
            ("liked" if vote == "up" else "disliked", f"newsletter feedback: {vote}", int(evidence_id)),
        )
        if topic:
            delta = 1.5 if vote == "up" else -1.25
            conn.execute(
                """INSERT INTO user_interests (username, topic, category, source, score, active, source_agent, updated_at)
                   VALUES ('ghost', ?, 'watched_research', 'newsletter_feedback', ?, 1, 'money_hub', datetime('now'))
                   ON CONFLICT(username, topic) DO UPDATE SET
                     score=max(0, user_interests.score + excluded.score),
                     active=CASE WHEN max(0, user_interests.score + excluded.score) > 0 THEN 1 ELSE active END,
                     source='newsletter_feedback',
                     source_agent='money_hub',
                     updated_at=datetime('now')""",
                (topic, delta),
            )
        write_knowledge(
            f"money-hub-feedback-{evidence_id}-{vote}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            f"Newsletter article feedback: {vote} for {topic or source_url}. {note or ''}".strip(),
            "money-hub",
            category="fact",
            importance=7 if vote == "up" else 6,
        )
        conn.commit()
        return {"ok": True, "evidence_id": int(evidence_id), "vote": vote, "topic": topic, "source_url": source_url}
    finally:
        conn.close()


def _summary_payload() -> dict[str, Any]:
    from frontend.blueprints import business_bp, financial_bp, trading_bp

    return {
        "financial": financial_bp.summary_for_seven(),
        "trading": trading_bp.summary_for_seven(),
        "business": business_bp.summary_for_seven(),
    }


def ensure_newsletter_feedback_schema(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or get_connection()
    try:
        conn.execute(_MONEY_HUB_SENT_ITEMS_DDL)
        conn.execute(_NEWSLETTER_FEEDBACK_DDL)
        conn.commit()
    finally:
        if own:
            conn.close()


def _html_to_text(raw: str) -> str:
    if not raw:
        return ""
    txt = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", txt).strip()


def _extract_image_url(raw: str) -> str:
    if not raw:
        return ""
    m = re.search(r"https?://[^\s\"'>]+\.(?:png|jpg|jpeg|webp|gif)", raw, flags=re.IGNORECASE)
    return m.group(0) if m else ""


def _feed_source_name(sub: dict[str, Any]) -> str:
    t = str(sub.get("title") or "").strip()
    if t:
        return t
    u = str(sub.get("url") or "").strip()
    return u.replace("https://", "").replace("http://", "")[:64] if u else "unknown"


def _score_sap_au(item: dict[str, Any]) -> int:
    blob = (str(item.get("title") or "") + " " + str(item.get("summary") or "")).lower()
    score = 0
    high = (
        "sap", "s/4hana", "hcm", "successfactors", "abap", "fiori", "hana",
        "australia", "ato", "payroll", "superannuation", "compliance", "regulation",
    )
    med = ("tax", "employment", "privacy", "cyber", "ai", "cloud", "cost", "market")
    for w in high:
        if w in blob:
            score += 4
    for w in med:
        if w in blob:
            score += 1
    return score


def _topic_for_item(item: dict[str, Any]) -> str:
    blob = (str(item.get("title") or "") + " " + str(item.get("summary") or "")).lower()
    if any(k in blob for k in ("payroll", "hcm", "successfactors", "superannuation", "ato")):
        return "People & Payroll"
    if any(k in blob for k in ("cyber", "security", "privacy", "breach", "vulnerability")):
        return "Cyber & Risk"
    if any(k in blob for k in ("tax", "compliance", "regulation", "law", "policy")):
        return "Policy & Compliance"
    if any(k in blob for k in ("ai", "cloud", "fiori", "abap", "hana", "s/4")):
        return "Platform & Delivery"
    return "Markets & Operations"


def _collect_sap_au_articles(max_feeds: int = 6, per_feed: int = 8, exclude_links: set[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    from core import feeds as _feeds

    exclude_links = exclude_links or set()
    issues: list[str] = []
    rows: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    subs = _feeds.list_subscriptions("seven")
    enabled = [s for s in subs if bool(s.get("enabled")) and s.get("kind") in ("rss", "atom")]
    if not enabled:
        enabled = [{"title": t, "url": u, "kind": "rss", "enabled": True} for t, u in _SAP_AU_DEFAULT_FEEDS]

    for sub in enabled[:max_feeds]:
        url = str(sub.get("url") or "").strip()
        if not url:
            continue
        try:
            fetched = _feeds.fetch_rss(url, limit=per_feed, timeout=7.0)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{_feed_source_name(sub)}: {exc}")
            continue
        for it in fetched:
            title = str(it.get("title") or "").strip()
            link = str(it.get("link") or "").strip()
            if not title:
                continue
            if link and (link in exclude_links or link in seen_links):
                continue
            if link:
                seen_links.add(link)
            raw_summary = str(it.get("summary") or "")
            rows.append({
                "title": title,
                "link": link,
                "published": str(it.get("published") or "").strip(),
                "summary": _html_to_text(raw_summary),
                "image": _extract_image_url(raw_summary),
                "source": _feed_source_name(sub),
            })
    ranked = sorted(rows, key=_score_sap_au, reverse=True)
    top = ranked[:12]
    for item in top[:8]:
        if not item.get("image") and item.get("link"):
            item["image"] = _fetch_og_image(item["link"])
    return top, issues


def _bottom_up(item: dict[str, Any]) -> dict[str, str]:
    lead = item.get("summary") or item.get("title") or ""
    if len(lead) > 240:
        lead = lead[:237].rstrip() + "..."
    return {
        "signal": lead,
        "system": "This changes either compliance pressure, operating cost, or delivery risk in the SAP landscape.",
        "stack": "For SAP Australia teams this shifts rollout sequencing, payroll/tax controls, and support backlog priorities.",
        "action": "Pick one measurable action this month: control uplift, automation cutover, or risk burn-down with owner/date.",
    }


def _bars(values: list[int], labels: list[str]) -> str:
    if not values:
        return ""
    mx = max(values) if max(values) > 0 else 1
    out = ["<div style='display:grid;gap:6px;margin-top:8px;'>"]
    for v, label in zip(values, labels):
        width = int((v / mx) * 100)
        out.append(
            "<div style='display:grid;grid-template-columns:140px 1fr 36px;gap:8px;align-items:center;'>"
            f"<div style='font-size:12px;color:#64748b;'>{html.escape(label)}</div>"
            f"<div style='height:10px;background:#e2e8f0;border-radius:999px;overflow:hidden;'><div style='height:100%;width:{width}%;background:linear-gradient(90deg,#0ea5e9,#10b981);'></div></div>"
            f"<div style='font-size:12px;color:#0f172a;font-weight:700;text-align:right;'>{v}</div>"
            "</div>"
        )
    out.append("</div>")
    return "".join(out)


def _dict_count_total(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    total = 0
    for v in value.values():
        try:
            total += int(v or 0)
        except (TypeError, ValueError):
            continue
    return total


def _fmt_dict(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(f"{k}: {v}" for k, v in sorted(value.items()))


def _fmt_link(label: str, href: str) -> str:
    return f"[{label}]({href})"


def _desk_summary(name: str, data: dict[str, Any], open_count: int, details: list[str]) -> dict[str, Any]:
    if open_count:
        status = "attention"
        reason = f"{open_count} open item{'s' if open_count != 1 else ''} need review, reconciliation, or an explicit defer decision."
        action = f"Open {name} and clear, annotate, or schedule the highest-risk item."
    else:
        status = "quiet"
        reason = "No live open work is registered, so there is no decision pressure from this desk today."
        action = f"Use {name} only if you need to add fresh data; otherwise spend the review time on active desks."
    return {
        "name": name,
        "status": status,
        "open": open_count,
        "reason": reason,
        "action": action,
        "details": details,
        "raw": data,
    }


def _collect_app_center_snapshot() -> dict[str, Any]:
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_projects'"
        ).fetchone()
        if not exists:
            return {
                "project_count": 0,
                "active_count": 0,
                "build_count": 0,
                "latest_projects": [],
                "latest_builds": [],
                "ready": False,
                "reason": "App Center tables have not been initialized yet; opening Studio > App Center will create them.",
            }
        projects = conn.execute(
            "SELECT project_id, name, kind, framework, status, studio_project_id, updated_at "
            "FROM app_projects ORDER BY updated_at DESC LIMIT 8"
        ).fetchall()
        builds_exist = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_builds'"
        ).fetchone()
        builds = []
        if builds_exist:
            builds = conn.execute(
                "SELECT build_id, project_id, target, status, asset_id, error, updated_at "
                "FROM app_builds ORDER BY updated_at DESC LIMIT 8"
            ).fetchall()
        project_count = conn.execute("SELECT COUNT(*) FROM app_projects").fetchone()[0]
        active_count = conn.execute(
            "SELECT COUNT(*) FROM app_projects WHERE status IN ('draft','active','paused')"
        ).fetchone()[0]
        build_count = conn.execute("SELECT COUNT(*) FROM app_builds").fetchone()[0] if builds_exist else 0
        return {
            "project_count": int(project_count or 0),
            "active_count": int(active_count or 0),
            "build_count": int(build_count or 0),
            "latest_projects": [dict(r) for r in projects],
            "latest_builds": [dict(r) for r in builds],
            "ready": True,
            "reason": "App Center is initialized and can create projects, attach targets, and queue builds.",
        }
    except sqlite3.Error as exc:
        return {
            "project_count": 0,
            "active_count": 0,
            "build_count": 0,
            "latest_projects": [],
            "latest_builds": [],
            "ready": False,
            "reason": f"App Center database read failed: {exc}",
        }
    finally:
        conn.close()


def _collect_potato_farm_snapshot(now: datetime) -> dict[str, Any]:
    try:
        from core.hive import get_registry
        from frontend.blueprints.hive import _with_expected_farm_nodes

        reg = get_registry()
        nodes = _with_expected_farm_nodes(reg.list_nodes())
        jobs = reg.list_jobs(limit=25)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reason": f"Potato Farm read failed: {exc}",
            "nodes": [],
            "jobs": [],
            "live_count": 0,
            "stale_count": 0,
            "pending_jobs": 0,
            "completed_jobs": 0,
        }
    now_ts = int(now.timestamp())
    live_count = 0
    stale_count = 0
    for n in nodes:
        if n.get("offline") or not n.get("last_seen_ts"):
            stale_count += 1
            continue
        age = max(0, now_ts - int(n.get("last_seen_ts") or 0))
        n["age_s"] = age
        if age < 180:
            live_count += 1
        else:
            stale_count += 1
    pending_jobs = sum(1 for j in jobs if j.get("status") == "pending")
    completed_jobs = sum(1 for j in jobs if j.get("status") == "completed")
    return {
        "ok": True,
        "nodes": nodes,
        "jobs": jobs,
        "live_count": live_count,
        "stale_count": stale_count,
        "pending_jobs": pending_jobs,
        "completed_jobs": completed_jobs,
        "reason": (
            f"{live_count} live node(s), {stale_count} stale/offline expected node(s), "
            f"{pending_jobs} pending handoff(s), {completed_jobs} recent completed handoff(s)."
        ),
    }


def _collect_recent_evidence(limit: int = 6, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='watched_topic_evidence'"
        ).fetchone()
        if not exists:
            return []
        sent_urls = _load_money_hub_sent_urls(conn)
        rows = conn.execute(
            "SELECT id, topic_key, topic, title, source_url, snippet, reason, quality_score, novelty_score, "
            "qualified, notified, evidence_date, recency_score, recency_label, is_historical, created_at "
            "FROM watched_topic_evidence WHERE qualified=1 "
            "ORDER BY created_at DESC LIMIT ?",
            (max(limit * 8, 30),),
        ).fetchall()
        selected: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            url = str(item.get("source_url") or "")
            if url and url in sent_urls:
                continue
            fresh, fresh_reason = _evidence_is_fresh(item, now)
            item["fresh"] = fresh
            item["fresh_reason"] = fresh_reason
            if fresh:
                selected.append(item)
            if len(selected) >= limit:
                break
        return selected
    finally:
        conn.close()


def _collect_recent_evidence_for_now(now: datetime) -> list[dict[str, Any]]:
    try:
        return _collect_recent_evidence(now=now)
    except TypeError:
        return _collect_recent_evidence()


def _clean_evidence_text(value: Any, *, max_len: int = 360) -> str:
    text = _html_to_text(str(value or ""))
    text = re.sub(r"\bqualified:\s*quality=.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text).strip(" -")
    if len(text) > max_len:
        text = text[: max_len - 3].rsplit(" ", 1)[0].rstrip(" ,.;:") + "..."
    return text


def _source_label(url: str) -> str:
    if not url:
        return "source"
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        host = ""
    return host or "source"


def _topic_reason(topic: str, title: str, snippet: str) -> str:
    blob = f"{topic} {title} {snippet}".lower()
    if any(k in blob for k in ("payday super", "single touch payroll", "stp", "ato", "superannuation")):
        return "Payroll/compliance signal: check whether this changes controls, calendar timing, or employee-payroll obligations."
    if any(k in blob for k in ("successfactors", "employee central", "hcm", "core payroll")):
        return "SAP HR signal: useful for SuccessFactors scope, integration, and support backlog decisions."
    if any(k in blob for k in ("course", "training", "demo", "youtube")):
        return "Learning signal: use it to decide whether the material is worth a deeper skills or process review."
    if any(k in blob for k in ("case study", "reduction", "automation", "reporting", "documents")):
        return "Operational signal: points at a possible automation, reporting, or document-handling improvement."
    return "KC signal: relevant to a watched interest, but needs a human skim before it becomes an action."


def _read_if(topic: str, title: str, snippet: str) -> str:
    blob = f"{topic} {title} {snippet}".lower()
    if any(k in blob for k in ("payday super", "single touch payroll", "stp", "ato")):
        return "Read if you are checking Australian payroll compliance or upcoming control changes."
    if "successfactors" in blob or "employee central" in blob:
        return "Read if you are tracking SAP SuccessFactors capability, configuration, or implementation scope."
    if any(k in blob for k in ("training", "course", "demo", "youtube")):
        return "Read if you want a quick sense of whether the training/demo is worth saving."
    if any(k in blob for k in ("case study", "automation", "reporting", "documents")):
        return "Read if you are looking for practical examples to turn into a Studio task."
    return "Read if this topic is still active in KC and you want to promote it into a task."


def _evidence_brief(item: dict[str, Any]) -> dict[str, str]:
    title = _clean_evidence_text(item.get("title"), max_len=140) or "Untitled evidence"
    snippet = _clean_evidence_text(item.get("snippet"), max_len=420)
    topic = _clean_evidence_text(item.get("topic") or item.get("topic_key"), max_len=90)
    url = str(item.get("source_url") or "").strip()
    evidence_id = str(item.get("id") or "")
    if not snippet or snippet.lower() == title.lower() or snippet.lower() in {"youtube", "scribd"}:
        snippet = "The crawler captured limited page text, so treat this as a source to inspect rather than a fully extracted article."
    return {
        "title": title,
        "topic": topic or "watched topic",
        "url": url,
        "source": _source_label(url),
        "inside": snippet,
        "why": _topic_reason(topic, title, snippet),
        "read_if": _read_if(topic, title, snippet),
        "score": (
            f"quality {float(item.get('quality_score') or 0):.2f}, "
            f"novelty {float(item.get('novelty_score') or 0):.2f}, "
            f"{'notified' if item.get('notified') else 'not yet notified'}"
        ),
        "like_url": _abs_link("/api/newsletter/feedback?" + urlencode({"evidence_id": evidence_id, "vote": "up"})) if evidence_id else "",
        "dislike_url": _abs_link("/api/newsletter/feedback?" + urlencode({"evidence_id": evidence_id, "vote": "down"})) if evidence_id else "",
    }


def _collect_kc_interest_snapshot(limit: int = 10) -> dict[str, Any]:
    """Read KC-owned interests and their downstream newsletter/research hooks."""
    conn = get_connection()
    try:
        interests = []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_interests'").fetchone():
            rows = conn.execute(
                "SELECT topic, category, source, source_agent, score, updated_at "
                "FROM user_interests WHERE active=1 "
                "ORDER BY score DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            interests = [dict(r) for r in rows]

        watched_tasks = []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scheduled_tasks'").fetchone():
            rows = conn.execute(
                "SELECT name, schedule, action_data, last_run, next_run, enabled "
                "FROM scheduled_tasks "
                "WHERE enabled=1 AND (action_data LIKE 'interest_research_update%' "
                "OR name LIKE '%newsletter%' OR name LIKE '%sap%') "
                "ORDER BY COALESCE(next_run, ''), name LIMIT ?",
                (limit,),
            ).fetchall()
            watched_tasks = [dict(r) for r in rows]

        docs = []
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_docs'").fetchone():
            rows = conn.execute(
                "SELECT doc_name, tags, updated_at FROM project_docs "
                "WHERE tags LIKE '%newsletter%' OR tags LIKE '%sap%' OR tags LIKE '%interest%' "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            docs = [dict(r) for r in rows]

        settings_count = 0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='watched_topic_settings'").fetchone():
            settings_count = int(conn.execute("SELECT COUNT(*) FROM watched_topic_settings").fetchone()[0] or 0)

        return {
            "interests": interests,
            "watched_tasks": watched_tasks,
            "docs": docs,
            "settings_count": settings_count,
            "interest_count": len(interests),
            "watched_task_count": len(watched_tasks),
        }
    finally:
        conn.close()


def compose_newsletter(now: datetime | None = None) -> dict[str, str]:
    """Return the current Money Hub newsletter without writing it."""
    now = now or _local_now()
    day = now.date().isoformat()
    payload = _summary_payload()
    financial = payload["financial"]
    trading = payload["trading"]
    business = payload["business"]

    desks = [
        _desk_summary(
            "Financial",
            financial,
            int(financial.get("open", 0) or 0),
            [
                f"By class: {_fmt_dict(financial.get('by_class'))}",
                f"High conviction: {financial.get('high_conviction') or 'none'}",
            ],
        ),
        _desk_summary(
            "Trading",
            trading,
            int(trading.get("open", 0) or _dict_count_total(trading.get("by_side"))),
            [
                f"By side: {_fmt_dict(trading.get('by_side'))}",
                f"Realised P/L: {trading.get('realised_pnl', 0.0)}",
                f"Top signals: {trading.get('top') or 'none'}",
            ],
        ),
        _desk_summary(
            "Business",
            business,
            int(business.get("unreconciled", 0) or 0),
            [
                f"Net by currency: {_fmt_dict(business.get('net_by_currency'))}",
                f"By kind: {_fmt_dict(business.get('by_kind'))}",
                f"Recent entries: {business.get('recent') or 'none'}",
            ],
        ),
    ]
    app_center = _collect_app_center_snapshot()
    farm = _collect_potato_farm_snapshot(now)
    evidence = _collect_recent_evidence_for_now(now)
    kc_interests = _collect_kc_interest_snapshot()

    check_reasons: list[str] = []
    if kc_interests["interest_count"]:
        if not evidence:
            check_reasons.append(
                f"KC interests: {kc_interests['interest_count']} active interest(s) exist, but no watched evidence is currently stored."
            )
        if not kc_interests["watched_task_count"]:
            check_reasons.append("KC interests: no active watched-topic/newsletter task is wired to push interest updates downstream.")
    else:
        check_reasons.append("KC interests: no active interests are registered, so Money Hub has no upstream preference stream.")
    for desk in desks:
        if desk["open"]:
            check_reasons.append(f"{desk['name']}: {desk['reason']}")
    if app_center["project_count"] == 0:
        check_reasons.append("App Center: no app/game project is registered yet, so build work has nowhere durable to land.")
    elif app_center["build_count"] == 0:
        check_reasons.append("App Center: projects exist but no build has been queued, so there is no artifact trail yet.")
    if farm.get("pending_jobs"):
        check_reasons.append(f"Potato Farm: {farm['pending_jobs']} pending handoff(s) need a worker claim or cleanup.")
    if farm.get("stale_count"):
        check_reasons.append(f"Potato Farm: {farm['stale_count']} expected node(s) are stale/offline, which limits distributed execution.")
    if not check_reasons:
        check_reasons.append("No urgent desk/farm/app blocker is visible; use this issue as a quick confirmation pass.")

    project_rows = app_center["latest_projects"][:5]
    build_rows = app_center["latest_builds"][:5]
    node_rows = farm.get("nodes", [])[:6]
    job_rows = farm.get("jobs", [])[:6]

    lines = [
        f"# Money Hub Daily Newsletter - {day}",
        "",
        "## Why Check Today",
        *[f"- {reason}" for reason in check_reasons],
        "",
        "## Open Sections",
        f"- {_fmt_link('Money Hub', '/ui')} - review Financial, Trading, Business, Markets, and iBank tabs.",
        f"- {_fmt_link('App Center', '/ui')} - create app/game build projects, attach targets, and queue builds.",
        f"- {_fmt_link('Potato Farm', '/ui')} - inspect live nodes, handoffs, and GPU proof.",
        "",
        "## KC Interests",
        f"- Active interests: {kc_interests['interest_count']}",
        f"- Active interest/newsletter tasks: {kc_interests['watched_task_count']}",
        f"- Watched-topic settings rows: {kc_interests['settings_count']}",
    ]
    if kc_interests["interests"]:
        lines.append("- Interest queue:")
        for item in kc_interests["interests"][:8]:
            lines.append(
                f"  - {item.get('topic')} ({item.get('category') or 'general'}, score {item.get('score')})"
                + (f" via {item.get('source_agent')}" if item.get("source_agent") else "")
            )
    else:
        lines.append("- Interest queue: empty.")
    if kc_interests["watched_tasks"]:
        lines.append("- Downstream schedules:")
        for task in kc_interests["watched_tasks"][:8]:
            lines.append(
                f"  - {task.get('name')}: {task.get('schedule')} -> {task.get('next_run') or 'no next run'}"
            )
    else:
        lines.append("- Downstream schedules: none wired.")
    if kc_interests["docs"]:
        lines.append("- Recent KC interest/newsletter docs:")
        for doc in kc_interests["docs"][:6]:
            lines.append(f"  - {doc.get('doc_name')} ({doc.get('tags') or 'no tags'})")
    lines += [
        "",
        "## Desk Summaries",
    ]
    for desk in desks:
        lines += [
            f"### {desk['name']} Desk",
            f"- Status: {desk['status']} ({desk['open']} open)",
            f"- Summary: {desk['reason']}",
            f"- Next action: {desk['action']}",
            *[f"- {d}" for d in desk["details"]],
            "",
        ]

    lines += [
        "## App Center",
        f"- Summary: {app_center['reason']}",
        f"- Projects: {app_center['project_count']} total, {app_center['active_count']} active/draft/paused",
        f"- Builds: {app_center['build_count']} total",
        f"- Links: {_fmt_link('projects API', '/api/app-center/projects')} · {_fmt_link('registry API', '/api/app-center/registry')}",
    ]
    if project_rows:
        lines.append("- Recent projects:")
        for p in project_rows:
            lines.append(
                f"  - {p.get('name') or p.get('project_id')} ({p.get('kind')}/{p.get('framework')}, {p.get('status')})"
                + (f" · Studio {p.get('studio_project_id')}" if p.get("studio_project_id") else "")
            )
    else:
        lines.append("- Recent projects: none. Create one from Studio > App Center so build work has a durable home.")
    if build_rows:
        lines.append("- Recent builds:")
        for b in build_rows:
            state = b.get("status")
            extra = f" · asset {b.get('asset_id')}" if b.get("asset_id") else ""
            if b.get("error"):
                extra += f" · error {b.get('error')}"
            lines.append(f"  - {b.get('build_id')} {b.get('target')} {state}{extra}")
    else:
        lines.append("- Recent builds: none queued yet.")

    lines += [
        "",
        "## Potato Farm",
        f"- Summary: {farm['reason']}",
        f"- Links: {_fmt_link('nodes API', '/api/hive/nodes')} · {_fmt_link('jobs API', '/api/hive/jobs')} · {_fmt_link('Android install', '/api/hive/install/android')}",
    ]
    if node_rows:
        lines.append("- Nodes:")
        for n in node_rows:
            age = n.get("age_s")
            age_txt = "offline/expected" if n.get("offline") else f"{age}s old" if age is not None else "unknown age"
            caps = ", ".join((n.get("telemetry") or {}).get("capabilities") or []) or "no capabilities"
            lines.append(f"  - {n.get('node_id')} ({n.get('platform')}) - {age_txt}; {caps}")
    if job_rows:
        lines.append("- Recent handoffs:")
        for j in job_rows:
            lines.append(f"  - {j.get('job_id')} {j.get('kind')} -> {j.get('node_id') or 'auto'}: {j.get('status')} ({j.get('capability_req') or 'no capability'})")

    lines += [
        "",
        "## Watched Evidence",
    ]
    if evidence:
        for item in evidence[:6]:
            brief = _evidence_brief(item)
            title_part = _fmt_link(brief["title"], brief["url"]) if brief["url"] else brief["title"]
            lines += [
                f"- {title_part}",
                f"  - What is inside: {brief['inside']}",
                f"  - Why it matters: {brief['why']}",
                f"  - Read if: {brief['read_if']}",
                f"  - Source: {brief['source']} ({brief['score']})",
            ]
    else:
        lines.append("- No watched-topic evidence rows are currently registered. That means this issue is an operational state check, not a news digest.")

    lines += [
        "",
        "## Source Provenance",
        f"- {_fmt_link('financial summary', '/api/financial/summary')}",
        f"- {_fmt_link('trading summary', '/api/trading/summary')}",
        f"- {_fmt_link('business summary', '/api/business/summary')}",
        "- KC interests: user_interests",
        "- watched-topic evidence: watched_topic_evidence",
        "- schedules: scheduled_tasks",
        f"- {_fmt_link('App Center projects', '/api/app-center/projects')}",
        f"- {_fmt_link('Potato Farm nodes', '/api/hive/nodes')}",
        f"- scheduler: Tasker PYTHON money_hub_daily_newsletter",
    ]
    return {
        "day": day,
        "doc_name": f"{DOC_PREFIX}_{day}.md",
        "content": "\n".join(lines),
    }


def _abs_link(path: str) -> str:
    base = os.environ.get("SWARM_PUBLIC_URL") or os.environ.get("SWARM_BASE_URL") or "http://100.87.66.45:5050"
    return base.rstrip("/") + "/" + str(path or "").lstrip("/")


def compose_money_hub_email(now: datetime | None = None) -> dict[str, str]:
    """Compose a visual daily Money Hub email from KC-first state."""
    now = now or _local_now()
    day = now.date().isoformat()
    payload = _summary_payload()
    financial = payload["financial"]
    trading = payload["trading"]
    business = payload["business"]
    app_center = _collect_app_center_snapshot()
    farm = _collect_potato_farm_snapshot(now)
    evidence = _collect_recent_evidence_for_now(now)
    kc = _collect_kc_interest_snapshot()

    issue_no = now.strftime("%y%m%d")
    live_nodes = int(farm.get("live_count") or 0)
    stale_nodes = int(farm.get("stale_count") or 0)
    pending_jobs = int(farm.get("pending_jobs") or 0)
    app_projects = int(app_center.get("project_count") or 0)
    app_builds = int(app_center.get("build_count") or 0)
    interest_count = int(kc.get("interest_count") or 0)
    task_count = int(kc.get("watched_task_count") or 0)
    evidence_count = len(evidence or [])

    primary_actions: list[dict[str, str]] = []
    if not evidence:
        primary_actions.append({
            "label": "Harvest SAP signals",
            "why": "KC has SAP/SuccessFactors watches, but no fresh eligible evidence for today's issue.",
            "href": _abs_link("/ui"),
            "heat": "HOT",
        })
    if app_projects == 0:
        primary_actions.append({
            "label": "Create App Center trail",
            "why": "No app/game project is registered, so build work has no durable artifact path.",
            "href": _abs_link("/ui"),
            "heat": "WARM",
        })
    if stale_nodes or pending_jobs:
        primary_actions.append({
            "label": "Recover Potato Farm",
            "why": f"{stale_nodes} stale/offline node(s), {pending_jobs} pending handoff(s).",
            "href": _abs_link("/api/hive/nodes"),
            "heat": "HOT" if pending_jobs else "WARM",
        })
    if not primary_actions:
        primary_actions.append({
            "label": "Quick daily confirmation",
            "why": "No urgent blocker is visible; skim the system pulse and move on.",
            "href": _abs_link("/ui"),
            "heat": "COOL",
        })

    def esc(v: Any) -> str:
        return html.escape(str(v or ""))

    def heat_color(label: str) -> str:
        return {"HOT": "#ff5e3a", "WARM": "#ffb347", "COOL": "#5ee3ff"}.get(label, "#5ee3ff")

    def metric(label: str, value: Any, note: str, color: str) -> str:
        return (
            "<td width='33.33%' style='padding:8px'>"
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            "style='border-collapse:separate;border-spacing:0;background:#111b2d;border:1px solid #223756;border-radius:14px'>"
            f"<tr><td style='padding:16px;font-family:Inter,Segoe UI,Arial,sans-serif'>"
            f"<div style='font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7f96b5'>{esc(label)}</div>"
            f"<div style='font-size:34px;font-weight:900;color:{color};line-height:1;margin-top:8px'>{esc(value)}</div>"
            f"<div style='font-size:12px;line-height:1.45;color:#b8c6d9;margin-top:8px'>{esc(note)}</div>"
            "</td></tr></table></td>"
        )

    action_rows = []
    for idx, item in enumerate(primary_actions[:4], 1):
        color = heat_color(item["heat"])
        action_rows.append(
            "<tr>"
            f"<td width='48' style='padding:14px 10px 14px 18px;font-family:Georgia,serif;font-size:28px;font-weight:900;color:#f7b84b'>{idx:02d}</td>"
            f"<td style='padding:14px 10px;font-family:Inter,Segoe UI,Arial,sans-serif'>"
            f"<div style='font-size:10px;letter-spacing:2px;text-transform:uppercase;color:{color};font-weight:800'>{esc(item['heat'])} ACTION</div>"
            f"<div style='font-size:17px;font-weight:800;color:#ffffff;margin-top:3px'>{esc(item['label'])}</div>"
            f"<div style='font-size:13px;line-height:1.45;color:#b8c6d9;margin-top:4px'>{esc(item['why'])}</div>"
            "</td>"
            f"<td width='130' style='padding:14px 18px 14px 8px;text-align:right'>"
            f"<a href='{esc(item['href'])}' style='display:inline-block;background:#f7b84b;color:#111b2d;text-decoration:none;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:12px;font-weight:900;letter-spacing:1px;text-transform:uppercase;padding:12px 16px;border-radius:999px;box-shadow:0 0 22px rgba(247,184,75,.35)'>Open</a>"
            "</td></tr>"
        )

    interest_rows = []
    for item in (kc.get("interests") or [])[:8]:
        interest_rows.append(
            "<tr>"
            f"<td style='padding:8px 0;color:#ffffff;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:14px;font-weight:700'>{esc(item.get('topic'))}</td>"
            f"<td style='padding:8px 0;color:#8ea3bf;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:12px;text-align:right'>{esc(item.get('category') or 'general')} · {esc(item.get('score'))}</td>"
            "</tr>"
        )
    if not interest_rows:
        interest_rows.append("<tr><td style='padding:8px 0;color:#8ea3bf;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px'>No active KC interests.</td></tr>")

    schedule_rows = []
    for task in (kc.get("watched_tasks") or [])[:7]:
        schedule_rows.append(
            "<tr>"
            f"<td style='padding:8px 0;color:#ffffff;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px;font-weight:700'>{esc(task.get('name'))}</td>"
            f"<td style='padding:8px 0;color:#8ea3bf;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:12px;text-align:right'>{esc(task.get('next_run') or task.get('schedule'))}</td>"
            "</tr>"
        )

    evidence_block = (
        f"<div style='font-size:13px;line-height:1.55;color:#b8c6d9'>No fresh eligible watched-topic evidence for today's issue. Older or previously sent sources are being held back; run the SAP watches again to harvest current items with usable dates.</div>"
        if not evidence else
        "".join(
            (
                "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
                "style='margin:0 0 14px;border-collapse:separate;border-spacing:0;background:#0f1d33;border:1px solid #223756;border-radius:14px'>"
                "<tr><td style='padding:16px 18px;font-family:Inter,Segoe UI,Arial,sans-serif'>"
                f"<div style='font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#f7b84b;font-weight:900'>{esc(brief['topic'])} · {esc(brief['source'])}</div>"
                f"<a href='{esc(brief['url'] or '#')}' style='display:block;color:#ffffff;font-size:17px;line-height:1.25;font-weight:900;text-decoration:none;margin-top:5px'>{esc(brief['title'])}</a>"
                f"<div style='font-size:13px;line-height:1.55;color:#d5e3f6;margin-top:10px'><strong style='color:#ffffff'>What is inside:</strong> {esc(brief['inside'])}</div>"
                f"<div style='font-size:13px;line-height:1.55;color:#b8c6d9;margin-top:8px'><strong style='color:#ffffff'>Why it matters:</strong> {esc(brief['why'])}</div>"
                f"<div style='font-size:13px;line-height:1.55;color:#b8c6d9;margin-top:8px'><strong style='color:#ffffff'>Read if:</strong> {esc(brief['read_if'])}</div>"
                f"<div style='font-size:11px;line-height:1.4;color:#7f96b5;margin-top:10px;text-transform:uppercase;letter-spacing:1px'>{esc(brief['score'])}</div>"
                + (
                    "<div style='margin-top:12px'>"
                    f"<a href='{esc(brief['like_url'])}' style='display:inline-block;background:#163f2d;color:#7ef0a3;text-decoration:none;font-size:12px;font-weight:900;padding:9px 12px;border-radius:999px;margin-right:8px'>Useful</a>"
                    f"<a href='{esc(brief['dislike_url'])}' style='display:inline-block;background:#3b1d25;color:#ff9db0;text-decoration:none;font-size:12px;font-weight:900;padding:9px 12px;border-radius:999px'>Not useful</a>"
                    "</div>"
                    if brief.get("like_url") else ""
                )
                + "</td></tr></table>"
            )
            for brief in [_evidence_brief(e) for e in evidence[:5]]
        )
    )

    plain = "\n".join([
        f"Money Hub Daily - {day}",
        "",
        "Top actions:",
        *[f"- {a['label']}: {a['why']} ({a['href']})" for a in primary_actions],
        "",
        f"KC interests: {interest_count}; scheduled flows: {task_count}; evidence rows: {evidence_count}",
        f"App Center: {app_projects} projects, {app_builds} builds",
        f"Potato Farm: {live_nodes} live, {stale_nodes} stale/offline, {pending_jobs} pending",
        "",
        "Evidence briefs:",
        *[
            f"- {b['title']}: {b['inside']} Why it matters: {b['why']} Read if: {b['read_if']} ({b['url']})"
            for b in [_evidence_brief(e) for e in evidence[:5]]
        ],
    ])

    html_doc = (
        "<!doctype html><html><body style='margin:0;background:#070d18;padding:0'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#070d18'><tr><td align='center' style='padding:24px 10px'>"
        "<table role='presentation' width='680' cellpadding='0' cellspacing='0' style='max-width:680px;border-collapse:separate;border-spacing:0;background:#0a1426;border:1px solid #1c3050;border-radius:22px;overflow:hidden;box-shadow:0 28px 80px rgba(0,0,0,.55)'>"
        "<tr><td style='padding:0;background:#1d3761;background-image:linear-gradient(135deg,#18345f 0%,#256f83 46%,#8f2d55 100%)'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr><td style='padding:38px 34px 32px'>"
        f"<div style='font-family:SFMono-Regular,Consolas,monospace;font-size:11px;letter-spacing:5px;text-transform:uppercase;color:#f7b84b;font-weight:800'>FRIDAYS · MONEY HUB · ISSUE {issue_no}</div>"
        "<div style='font-family:Georgia,Times New Roman,serif;font-size:54px;line-height:.95;font-weight:900;color:#ffffff;margin-top:16px;text-shadow:0 4px 28px rgba(0,0,0,.45)'>Money Hub</div>"
        f"<div style='font-family:Georgia,Times New Roman,serif;font-size:36px;line-height:1;font-style:italic;font-weight:900;color:#f7b84b;margin-top:6px'>KC-first daily · {esc(day)}</div>"
        "<div style='font-family:Inter,Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.55;color:#eef5ff;margin-top:20px;max-width:540px'>Your interests start in Knowledge Center. This issue shows what KC is pushing downstream into Money Hub, App Center, Potato Farm, and Tasker.</div>"
        "</td></tr></table></td></tr>"
        "<tr><td style='padding:24px 24px 8px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        + metric("KC interests", interest_count, f"{task_count} downstream schedule(s)", "#f7b84b")
        + metric("Watched evidence", evidence_count, "novel findings stored", "#5ee3ff")
        + metric("Potato Farm", f"{live_nodes}/{live_nodes + stale_nodes}", f"{pending_jobs} pending handoff(s)", "#ffb347")
        + "</tr></table></td></tr>"
        "<tr><td style='padding:20px 32px 8px'>"
        "<div style='font-family:SFMono-Regular,Consolas,monospace;font-size:10px;letter-spacing:4px;color:#f7b84b;text-transform:uppercase;margin-bottom:12px'>THE MOVES</div>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#0f1d33;border:1px solid #223756;border-radius:16px'>"
        + "".join(action_rows) +
        "</table></td></tr>"
        "<tr><td style='padding:24px 32px 8px'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        "<td valign='top' width='50%' style='padding-right:10px'>"
        "<div style='font-family:SFMono-Regular,Consolas,monospace;font-size:10px;letter-spacing:3px;color:#f7b84b;text-transform:uppercase;margin-bottom:10px'>KC INTEREST QUEUE</div>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='border-top:1px solid #223756'>" + "".join(interest_rows) + "</table>"
        "</td><td valign='top' width='50%' style='padding-left:10px'>"
        "<div style='font-family:SFMono-Regular,Consolas,monospace;font-size:10px;letter-spacing:3px;color:#f7b84b;text-transform:uppercase;margin-bottom:10px'>DOWNSTREAM SCHEDULES</div>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='border-top:1px solid #223756'>" + "".join(schedule_rows) + "</table>"
        "</td></tr></table></td></tr>"
        "<tr><td style='padding:24px 32px 30px'>"
        "<div style='font-family:SFMono-Regular,Consolas,monospace;font-size:10px;letter-spacing:3px;color:#f7b84b;text-transform:uppercase;margin-bottom:10px'>EVIDENCE STATUS</div>"
        f"{evidence_block}"
        "<div style='margin-top:22px'>"
        f"<a href='{esc(_abs_link('/ui'))}' style='display:inline-block;background:#f7b84b;color:#111b2d;text-decoration:none;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px;font-weight:900;letter-spacing:2px;text-transform:uppercase;padding:15px 24px;border-radius:999px'>Open Fridays</a>"
        f"<a href='{esc(_abs_link('/api/tasker/tasks'))}' style='display:inline-block;margin-left:10px;border:1px solid #f7b84b;color:#f7b84b;text-decoration:none;font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px;font-weight:800;letter-spacing:1px;text-transform:uppercase;padding:14px 20px;border-radius:999px'>Tasker feed</a>"
        "</div></td></tr>"
        "</table></td></tr></table></body></html>"
    )
    return {
        "day": day,
        "subject": f"Money Hub Daily - KC-first issue - {day}",
        "plain": plain,
        "html": html_doc,
        "evidence": evidence,
    }


def compose_sap_au_monthly_newsletter(now: datetime | None = None) -> dict[str, str]:
    """Compose a rich monthly SAP Australia newsletter.

    Includes article-backed cards, bottom-up explanations, and visual trend
    blocks so the output is presentation-ready for Studio.
    """
    now = now or datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    payload = _summary_payload()
    financial = payload["financial"]
    trading = payload["trading"]
    business = payload["business"]
    articles, issues = _collect_sap_au_articles(exclude_links=_load_sent_links())

    topic_counts: dict[str, int] = {}
    cards_html: list[str] = []
    cards_md: list[str] = []
    for idx, item in enumerate(articles[:8], start=1):
        topic = _topic_for_item(item)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        score = _score_sap_au(item)
        expl = _bottom_up(item)
        link = item.get("link") or ""
        image = item.get("image") or ""
        host = ""
        try:
            host = urlparse(link).netloc
        except Exception:
            host = ""
        image_html = (
            f"<img src='{html.escape(image)}' alt='' style='width:100%;height:180px;object-fit:cover;border-radius:10px;'>"
            if image else
            "<div style='height:180px;border-radius:10px;background:linear-gradient(135deg,#0ea5e9,#6366f1);'></div>"
        )
        source_line = f"{html.escape(item.get('source') or 'source')}"
        if host:
            source_line += f" · {html.escape(host)}"
        cards_html.append(
            "<article style='border:1px solid #dbeafe;border-radius:14px;padding:12px;background:#ffffff;box-shadow:0 8px 24px rgba(15,23,42,.06);'>"
            f"{image_html}"
            f"<h3 style='margin:10px 0 4px;font-size:18px;line-height:1.25;color:#0f172a;'>{html.escape(item['title'])}</h3>"
            f"<div style='font-size:12px;color:#64748b;'>{source_line} · relevance {score} · {html.escape(topic)}</div>"
            f"<p style='margin:10px 0 0;color:#1e293b;'><strong>Bottom-up:</strong> {html.escape(expl['signal'])}</p>"
            f"<p style='margin:6px 0 0;color:#334155;'><strong>System:</strong> {html.escape(expl['system'])}</p>"
            f"<p style='margin:6px 0 0;color:#334155;'><strong>Your stack:</strong> {html.escape(expl['stack'])}</p>"
            f"<p style='margin:6px 0 0;color:#334155;'><strong>Action:</strong> {html.escape(expl['action'])}</p>"
            + (f"<p style='margin-top:10px;'><a href='{html.escape(link)}' target='_blank' rel='noopener'>Open source article</a></p>" if link else "")
            + "</article>"
        )
        cards_md.append(
            f"### {idx}. {item['title']}\n"
            f"- Source: {item.get('source') or 'source'}"
            + (f" · [{link}]({link})" if link else "") + "\n"
            f"- Relevance: {score} · Topic: {topic}\n"
            f"- Bottom-up\n"
            f"  - Signal: {expl['signal']}\n"
            f"  - System: {expl['system']}\n"
            f"  - Your stack: {expl['stack']}\n"
            f"  - Action: {expl['action']}\n"
        )

    trend_values = [
        int(financial.get("open", 0) or 0),
        int(trading.get("open", 0) or 0),
        int(business.get("unreconciled", 0) or 0),
        len(articles),
    ]
    trend_labels = ["Financial Open", "Trading Open", "Business Unreconciled", "Story Count"]
    trend_html = _bars(trend_values, trend_labels)

    topic_rows = sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    topic_table_html = "".join(
        f"<tr><td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;'>{html.escape(k)}</td>"
        f"<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:700;'>{v}</td></tr>"
        for k, v in topic_rows
    ) or "<tr><td colspan='2' style='padding:6px 8px;color:#64748b;'>No stories captured</td></tr>"

    issues_html = "".join(f"<li>{html.escape(i)}</li>" for i in issues[:6])
    issues_block_html = (
        f"<section style='margin-top:16px;'><h3 style='font-size:16px;color:#0f172a;'>Feed quality notes</h3><ul>{issues_html}</ul></section>"
        if issues else ""
    )

    html_doc = (
        "<div style='font-family:Inter,Segoe UI,system-ui,sans-serif;background:linear-gradient(180deg,#f8fbff,#eef6ff);"
        "padding:20px;color:#0f172a;'>"
        "<section style='max-width:1080px;margin:0 auto;'>"
        f"<header style='border-radius:18px;padding:24px;background:radial-gradient(circle at top right,#22d3ee,#2563eb 55%,#0f172a 110%);color:#f8fafc;'>"
        f"<div style='font-size:12px;letter-spacing:.12em;text-transform:uppercase;opacity:.9;'>SAP Australia Monthly Intelligence</div>"
        f"<h1 style='margin:8px 0 4px;font-size:34px;line-height:1.1;'>Executive Newsletter · {month}</h1>"
        "<p style='margin:0;max-width:760px;font-size:15px;line-height:1.5;'>Bottom-up analysis from source articles and live Swarm desks: what changed, why it matters systemically, and what to execute next.</p>"
        "</header>"
        "<section style='display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-top:16px;'>"
        "<div style='background:#fff;border:1px solid #dbeafe;border-radius:14px;padding:14px;'>"
        "<h2 style='margin:0 0 8px;font-size:18px;'>Operational pulse</h2>"
        f"{trend_html}"
        "</div>"
        "<div style='background:#fff;border:1px solid #dbeafe;border-radius:14px;padding:14px;'>"
        "<h2 style='margin:0 0 8px;font-size:18px;'>Story mix</h2>"
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'><thead><tr><th style='text-align:left;padding:6px 8px;border-bottom:1px solid #cbd5e1;'>Topic</th><th style='text-align:right;padding:6px 8px;border-bottom:1px solid #cbd5e1;'>Count</th></tr></thead><tbody>"
        f"{topic_table_html}</tbody></table>"
        "</div>"
        "</section>"
        "<section style='margin-top:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;'>"
        + ("".join(cards_html) if cards_html else "<div style='background:#fff;border:1px solid #dbeafe;border-radius:14px;padding:12px;'>No article cards yet. Connect RSS feeds in Feeds tab for richer monthly output.</div>")
        + "</section>"
        + issues_block_html
        + "</section></div>"
    )

    md_doc = "\n".join([
        f"# SAP Australia Monthly Newsletter - {month}",
        "",
        "Source provenance:",
        "- financial: /api/financial/summary",
        "- trading: /api/trading/summary",
        "- business: /api/business/summary",
        "- feeds: /api/feeds/subscriptions + RSS/Atom",
        "",
        "## Bottom-up narrative and insights",
        *cards_md,
        "",
        "## Metrics",
        f"- Financial open: {trend_values[0]}",
        f"- Trading open: {trend_values[1]}",
        f"- Business unreconciled: {trend_values[2]}",
        f"- Story count: {trend_values[3]}",
        "",
        "```mermaid",
        "xychart-beta",
        "    title \"SAP AU Monthly Pulse\"",
        "    x-axis [financial_open, trading_open, business_unreconciled, stories]",
        f"    bar [{trend_values[0]}, {trend_values[1]}, {trend_values[2]}, {trend_values[3]}]",
        "```",
    ])

    return {
        "month": month,
        "doc_name": f"{SAP_AU_DOC_PREFIX}_{month}.html",
        "content": html_doc,
        "content_md": md_doc,
    }


def write_newsletter(now: datetime | None = None) -> dict[str, str]:
    """Write or refresh today's newsletter in KC project_docs and knowledge."""
    doc = compose_newsletter(now)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM project_docs WHERE doc_name=? ORDER BY id DESC LIMIT 1",
            (doc["doc_name"],),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                (doc["content"], "money-hub,markets,business,newsletter", row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc["doc_name"], doc["content"], "money-hub,markets,business,newsletter"),
            )
        conn.commit()
    finally:
        conn.close()

    write_knowledge(
        f"money-hub-newsletter-{doc['day']}",
        doc["content"],
        "money-hub",
        category="fact",
        importance=7,
    )
    return doc


def write_money_hub_visual_newsletter(now: datetime | None = None) -> dict[str, Any]:
    """Write or refresh the visual daily Money Hub artifact in KC."""
    email_doc = compose_money_hub_email(now)
    doc_name = f"MONEY_HUB_DAILY_NEWSLETTER_{email_doc['day']}_VISUAL.html"
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM project_docs WHERE doc_name=? ORDER BY id DESC LIMIT 1",
            (doc_name,),
        ).fetchone()
        tags = "money-hub,markets,business,newsletter,visual,kc"
        if row:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                (email_doc["html"], tags, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc_name, email_doc["html"], tags),
            )
        conn.commit()
    finally:
        conn.close()

    write_knowledge(
        f"money-hub-newsletter-visual-{email_doc['day']}",
        email_doc["plain"],
        "money-hub",
        category="fact",
        importance=8,
    )
    return {"ok": True, "doc_name": doc_name, "subject": email_doc["subject"], "day": email_doc["day"]}


def send_money_hub_daily_newsletter(now: datetime | None = None) -> dict[str, Any]:
    """Send the visual daily Money Hub email and store it in KC project_docs."""
    from config import GHOST_EMAIL
    from lib.email.email_handler import send_reply

    written = write_money_hub_visual_newsletter(now)
    email_doc = compose_money_hub_email(now)
    ok = bool(send_reply(
        GHOST_EMAIL,
        email_doc["subject"],
        email_doc["plain"],
        html_body=email_doc["html"],
        sender_name="Swarm KC",
    ))
    if ok:
        _record_money_hub_sent_evidence(list(email_doc.get("evidence") or []), email_doc["day"])
    return {"ok": ok, "doc_name": written["doc_name"], "subject": email_doc["subject"], "to": GHOST_EMAIL}


def write_sap_au_monthly_newsletter(now: datetime | None = None) -> dict[str, str]:
    """Write monthly SAP Australia newsletter to Studio + Knowledge."""
    doc = compose_sap_au_monthly_newsletter(now)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM project_docs WHERE doc_name=? ORDER BY id DESC LIMIT 1",
            (doc["doc_name"],),
        ).fetchone()
        tags = "sap,australia,newsletter,monthly,insights"
        if row:
            conn.execute(
                "UPDATE project_docs SET content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                (doc["content"], tags, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO project_docs (doc_name, content, tags) VALUES (?,?,?)",
                (doc["doc_name"], doc["content"], tags),
            )
        conn.commit()
    finally:
        conn.close()

    write_knowledge(
        f"sap-au-newsletter-{doc['month']}",
        doc["content_md"],
        "sap",
        category="fact",
        importance=8,
    )
    return doc


def _sap_kc_gossip_email_html(primary: dict[str, Any], recent: list[dict[str, Any]]) -> tuple[str, str]:
    """Fridays-themed monthly outlook email. Gmail-safe tables, gold CTAs, signal heat dots."""

    def esc(v: Any) -> str:
        return html.escape(str(v or ""))

    now = datetime.now(timezone.utc)
    if now.month == 12:
        outlook_dt = now.replace(year=now.year + 1, month=1, day=1)
    else:
        outlook_dt = now.replace(month=now.month + 1, day=1)
    outlook_label = outlook_dt.strftime("%B %Y")
    issued_label = now.strftime("%d %b %Y")
    articles, _issues = _collect_sap_au_articles(exclude_links=_load_sent_links())
    hero_url = next((a.get("image") for a in articles if a.get("image")), "")

    GRADIENT = "linear-gradient(135deg,#2a4a6e 0%,#3a6186 45%,#89253e 100%)"
    GOLD = "#f7b84b"
    INK = "#13243b"
    BG = "#070d18"
    CARD = "#0f1d33"
    EDGE = "#1c3050"
    MONO = "SFMono-Regular,Consolas,'Fira Code',monospace"
    SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif"
    DISPLAY = "'Playfair Display',Georgia,'Times New Roman',serif"

    def heat(score: int) -> tuple[str, str, str]:
        # color, label, rgba glow
        if score >= 8:
            return ("#ff5e3a", "HOT", "rgba(255,94,58,0.55)")
        if score >= 4:
            return ("#ffb347", "WARM", "rgba(255,179,71,0.45)")
        return ("#5ee3ff", "COOL", "rgba(94,227,255,0.45)")

    # ---------------- masthead ----------------
    masthead = (
        f"<tr><td bgcolor='#2a4a6e' style='padding:0;background:#2a4a6e;background-image:{GRADIENT}'>"
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'>"
        "<tr><td style='padding:42px 32px 36px'>"
        f"<div style='font-family:{MONO};font-size:11px;letter-spacing:5px;text-transform:uppercase;color:{GOLD};margin-bottom:18px'>"
        f"&#9670;&nbsp;FRIDAYS&nbsp;&middot;&nbsp;ISSUE&nbsp;{now.strftime('%y%m').upper()}&nbsp;&middot;&nbsp;{esc(issued_label).upper()}&nbsp;&#9670;</div>"
        f"<div style='font-family:{DISPLAY};font-size:54px;line-height:0.95;font-weight:900;color:#ffffff;letter-spacing:-1.5px;text-shadow:0 4px 28px rgba(0,0,0,0.45)'>"
        f"SAP&nbsp;Australia</div>"
        f"<div style='font-family:{DISPLAY};font-size:44px;line-height:1;font-weight:900;font-style:italic;color:{GOLD};letter-spacing:-1px;margin-top:6px;text-shadow:0 0 22px rgba(247,184,75,0.45)'>"
        f"{esc(outlook_label)} &mdash; outlook</div>"
        f"<div style='font-family:{SANS};font-size:14px;line-height:1.6;color:#f1ecdc;margin-top:22px;max-width:500px'>"
        f"Six plays projected from {len(articles)} live signals. Skip the news. Act on the gold box. Tap the glowing pill.</div>"
        "</td></tr></table></td></tr>"
    )

    # ---------------- TL;DR strip ----------------
    tldr_rows: list[str] = []
    for idx, item in enumerate(articles[:6], start=1):
        ex = _bottom_up(item)
        score = _score_sap_au(item)
        dot, lbl, glow = heat(score)
        tldr_rows.append(
            "<tr>"
            f"<td valign='top' width='44' style='padding:10px 6px 10px 0;font-family:{DISPLAY};font-size:22px;font-weight:900;color:{GOLD};text-align:right'>{idx:02d}</td>"
            f"<td valign='middle' width='16' style='padding:10px 10px'>"
            f"<div style='width:10px;height:10px;border-radius:50%;background:{dot};box-shadow:0 0 12px {glow},0 0 4px {dot}'></div></td>"
            f"<td valign='top' style='padding:10px 0;font-family:{SANS};font-size:13px;line-height:1.45;color:#dde7f5'>"
            f"<a href='{esc(item.get('link') or '#')}' style='color:#ffffff;text-decoration:none;font-weight:600'>{esc(item.get('title'))}</a>"
            f"<div style='font-family:{MONO};font-size:10px;letter-spacing:1px;color:{dot};margin-top:3px;text-transform:uppercase'>{lbl} &middot; {esc(ex.get('action'))[:90]}</div>"
            "</td></tr>"
        )
    tldr_block = (
        "<tr><td style='padding:28px 32px 8px'>"
        f"<div style='font-family:{MONO};font-size:10px;letter-spacing:4px;color:{GOLD};text-transform:uppercase;margin-bottom:14px'>"
        f"&#9670;&nbsp;TL;DR&nbsp;&middot;&nbsp;THE&nbsp;SIX&nbsp;PLAYS&nbsp;&#9670;</div>"
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' style='background:#0a1426;border:1px solid {EDGE};border-radius:12px'>"
        "<tr><td style='padding:6px 18px'>"
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'>"
        + "".join(tldr_rows) +
        "</table></td></tr></table></td></tr>"
    )

    # ---------------- story chapters ----------------
    story_rows: list[str] = []
    for idx, item in enumerate(articles[:6], start=1):
        link = item.get("link") or ""
        img = item.get("image") or ""
        host = ""
        try:
            host = urlparse(link).netloc
        except Exception:
            host = ""
        expl = _bottom_up(item)
        signal = expl.get("signal") or item.get("title") or ""
        if len(signal) > 220:
            signal = signal[:217].rstrip() + "\u2026"
        action = expl.get("action") or ""
        score = _score_sap_au(item)
        dot, heat_label, glow = heat(score)

        if img:
            hero = (
                f"<tr><td style='padding:0;background:#000'>"
                f"<a href='{esc(link)}' style='text-decoration:none;display:block'>"
                f"<img src='{esc(img)}' width='600' alt='' style='display:block;width:100%;max-width:600px;height:300px;object-fit:cover;border:0;opacity:0.85'/></a>"
                "</td></tr>"
            )
        else:
            hero = (
                f"<tr><td bgcolor='#2a4a6e' height='180' style='height:180px;background:#2a4a6e;background-image:{GRADIENT}'>&nbsp;</td></tr>"
            )

        cta = (
            f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' style='margin-top:22px'>"
            f"<tr><td bgcolor='{GOLD}' style='border-radius:999px;box-shadow:0 0 0 1px {GOLD},0 0 28px rgba(247,184,75,0.65),0 0 60px rgba(247,184,75,0.35),0 8px 22px rgba(137,37,62,0.45)'>"
            f"<a href='{esc(link)}' style='display:inline-block;padding:16px 30px;font-family:{SANS};font-size:13px;font-weight:900;letter-spacing:2px;text-transform:uppercase;color:{INK};text-decoration:none'>"
            f"&#9656;&nbsp;Read this play&nbsp;&#9656;</a>"
            "</td></tr></table>"
        ) if link else ""

        story_rows.append(
            "<tr><td style='padding:30px 22px 6px'>"
            f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' style='background:{CARD};border:1px solid {EDGE};border-left:4px solid {dot};border-radius:14px;overflow:hidden;box-shadow:0 0 0 1px rgba(247,184,75,0.04),0 18px 40px rgba(0,0,0,0.45),0 0 80px {glow}'>"
            + hero +
            "<tr><td style='padding:24px 26px 28px'>"
            "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'><tr>"
            f"<td valign='top' width='80' style='font-family:{DISPLAY};font-size:60px;line-height:0.9;font-weight:900;color:{GOLD};text-shadow:0 0 18px rgba(247,184,75,0.45);padding-right:14px'>{idx:02d}</td>"
            f"<td valign='top'>"
            f"<div style='font-family:{MONO};font-size:10px;letter-spacing:3px;color:{dot};text-transform:uppercase;margin-bottom:4px'>"
            f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;background:{dot};box-shadow:0 0 10px {glow};vertical-align:middle;margin-right:8px'></span>"
            f"{esc(heat_label)} &middot; signal&nbsp;{score:02d} &middot; {esc(outlook_label)}</div>"
            f"<div style='font-family:{DISPLAY};font-size:26px;line-height:1.15;font-weight:800;color:#ffffff;margin-top:6px'>"
            f"<a href='{esc(link)}' style='color:#ffffff;text-decoration:none'>{esc(item.get('title'))}</a></div>"
            "</td></tr></table>"
            f"<div style='font-family:{SANS};font-size:14px;line-height:1.6;color:#cfdcef;margin-top:18px'>"
            f"<span style='font-family:{MONO};font-size:10px;letter-spacing:2px;color:{GOLD};text-transform:uppercase'>// SO WHAT</span><br/>{esc(signal)}</div>"
            f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' style='margin-top:18px'>"
            f"<tr><td bgcolor='{GOLD}' style='padding:16px 18px;border-radius:10px;font-family:{SANS};font-size:14px;line-height:1.55;color:{INK};box-shadow:inset 0 0 0 1px rgba(19,36,59,0.15),0 0 28px rgba(247,184,75,0.25)'>"
            f"<div style='font-family:{MONO};font-size:10px;letter-spacing:3px;color:{INK};text-transform:uppercase;margin-bottom:6px;opacity:0.7'>// DO NEXT</div>"
            f"<strong>{esc(action)}</strong></td></tr></table>"
            f"<div style='font-family:{MONO};font-size:10px;color:#6f87a3;margin-top:18px;letter-spacing:2px;text-transform:uppercase'>"
            f"SRC &middot; {esc(item.get('source') or '')}{(' &middot; ' + esc(host)) if host else ''}</div>"
            f"{cta}"
            "</td></tr></table></td></tr>"
        )

    # ---------------- trail ----------------
    trail = "".join([
        f"<tr><td style='padding:8px 32px;font-family:{MONO};font-size:11px;color:#7c93b3;letter-spacing:1px;border-top:1px solid {EDGE}'>"
        f"<span style='color:{GOLD};font-weight:700'>&#9670; #{int(r.get('id') or 0)}</span> &nbsp; {esc(r.get('doc_name'))} "
        f"<span style='color:#3d5675'>&middot; {esc(r.get('updated_at'))}</span></td></tr>"
        for r in recent[:6]
    ])

    plain_lines = [
        f"Fridays \u2014 SAP Australia {outlook_label} Outlook",
        f"Issued {issued_label}",
        "",
        "The six plays:",
    ]
    for a in articles[:6]:
        ex = _bottom_up(a)
        plain_lines.append(f"- {a.get('title')} \u2192 {ex.get('action')} ({a.get('link') or ''})")
    plain = "\n".join(plain_lines)

    wrapped = (
        f"<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>"
        f"<link rel='preconnect' href='https://fonts.googleapis.com'/>"
        f"<link href='https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,800;0,900;1,900&family=Fira+Code:wght@400;700&display=swap' rel='stylesheet'/>"
        f"</head><body style='margin:0;padding:0;background:{BG}'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' bgcolor='{BG}' style='background:{BG}'>"
        "<tr><td align='center' style='padding:28px 10px'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='600' style='max-width:600px;background:#0a1426;border-radius:18px;overflow:hidden;box-shadow:0 0 0 1px rgba(247,184,75,0.08),0 30px 80px rgba(0,0,0,0.7),0 0 120px rgba(137,37,62,0.25)'>"
        + masthead
        + tldr_block
        + f"<tr><td style='padding:30px 32px 6px;font-family:{MONO};font-size:10px;letter-spacing:4px;color:{GOLD};text-transform:uppercase'>"
        f"&#9670;&nbsp;THE&nbsp;CHAPTERS&nbsp;&#9670;</td></tr>"
        + "".join(story_rows)
        + f"<tr><td style='padding:34px 32px 12px;font-family:{MONO};font-size:10px;letter-spacing:4px;color:{GOLD};text-transform:uppercase'>"
        f"&#9670;&nbsp;KC&nbsp;ARTIFACT&nbsp;TRAIL&nbsp;&#9670;</td></tr>"
        + trail
        + f"<tr><td bgcolor='#2a4a6e' style='padding:30px 32px;background:#2a4a6e;background-image:{GRADIENT};font-family:{MONO};font-size:11px;color:#ffffff;letter-spacing:3px;text-align:center;text-transform:uppercase'>"
        f"<div style='font-family:{DISPLAY};font-size:20px;font-style:italic;color:{GOLD};letter-spacing:0;text-transform:none;margin-bottom:8px;text-shadow:0 0 18px rgba(247,184,75,0.5)'>&mdash; Fridays &mdash;</div>"
        f"Issued {esc(issued_label)} &middot; Outlook {esc(outlook_label)}"
        "</td></tr>"
        "</table></td></tr></table></body></html>"
    )
    return plain, wrapped


def send_sap_au_monthly_newsletter(now: datetime | None = None) -> dict[str, Any]:
    """Compose + write SAP AU monthly newsletter, then email as Swarm KC artifact."""
    from config import GHOST_EMAIL
    from lib.email.email_handler import send_reply

    written = write_sap_au_monthly_newsletter(now)

    conn = get_connection()
    try:
        primary = conn.execute(
            "SELECT id, doc_name, content, tags, updated_at FROM project_docs WHERE doc_name=? ORDER BY id DESC LIMIT 1",
            (written["doc_name"],),
        ).fetchone()
        recent = conn.execute(
            "SELECT id, doc_name, tags, updated_at FROM project_docs ORDER BY id DESC LIMIT 8"
        ).fetchall()
    finally:
        conn.close()

    primary_dict = dict(primary) if primary else {
        "id": 0,
        "doc_name": written["doc_name"],
        "content": written["content"],
        "tags": "sap,australia,newsletter,monthly,insights",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    recent_dicts = [dict(r) for r in recent]

    plain, wrapped_html = _sap_kc_gossip_email_html(primary_dict, recent_dicts)
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.month == 12:
        outlook_dt = now_dt.replace(year=now_dt.year + 1, month=1, day=1)
    else:
        outlook_dt = now_dt.replace(month=now_dt.month + 1, day=1)
    subject = f"Swarm KC \u2014 SAP Australia {outlook_dt.strftime('%B %Y')} Outlook (issued {now_dt.strftime('%d %b %Y')})"
    ok = bool(send_reply(
        GHOST_EMAIL,
        subject,
        plain,
        html_body=wrapped_html,
        sender_name="Swarm KC",
    ))

    if ok:
        try:
            sent_articles, _ = _collect_sap_au_articles(exclude_links=_load_sent_links())
            _record_sent_links(sent_articles[:6])
        except Exception:
            pass

    return {
        "ok": ok,
        "doc_name": written["doc_name"],
        "month": written["month"],
        "subject": subject,
        "to": GHOST_EMAIL,
    }


def ensure_tasker_schedule() -> int:
    """Ensure the daily Money Hub newsletter task exists in Tasker."""
    from fridays.scheduler import add_task

    return int(add_task(TASK_NAME, "daily 07:20", "PYTHON", TASK_NAME, created_by="system") or 0)


def ensure_monthly_tasker_schedule() -> int:
    """Ensure monthly SAP Australia newsletter task exists."""
    from fridays.scheduler import add_task

    return int(add_task(SAP_AU_TASK_NAME, "monthly 1 08:30", "PYTHON", SAP_AU_TASK_NAME, created_by="system") or 0)


def run() -> str:
    doc = write_money_hub_visual_newsletter()
    task_id = ensure_tasker_schedule()
    return f"money_hub_daily_newsletter ok - {doc['doc_name']} - task_id={task_id}"


def run_sap_au_monthly() -> str:
    doc = write_sap_au_monthly_newsletter()
    task_id = ensure_monthly_tasker_schedule()
    return f"sap_au_monthly_newsletter ok - {doc['doc_name']} - task_id={task_id}"


def run_sap_au_monthly_send() -> str:
    sent = send_sap_au_monthly_newsletter()
    task_id = ensure_monthly_tasker_schedule()
    status = "ok" if sent["ok"] else "failed"
    return f"sap_au_monthly_send {status} - {sent['doc_name']} - task_id={task_id}"


def run_money_hub_daily_send() -> str:
    sent = send_money_hub_daily_newsletter()
    task_id = ensure_tasker_schedule()
    status = "ok" if sent["ok"] else "failed"
    return f"money_hub_daily_send {status} - {sent['doc_name']} - task_id={task_id}"


if __name__ == "__main__":
    print(run())
