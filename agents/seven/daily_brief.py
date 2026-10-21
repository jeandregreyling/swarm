"""agents/seven/daily_brief.py — Seven's Daily Brief.

A real prose narrative — not a JSON dump — synthesised from the day's:
  · seven_episodes        what happened
  · seven_beliefs         what Seven now thinks is true (high-confidence)
  · curiosity_questions   what Seven is wondering about
  · seven_learnings       what worked / what didn't
  · seven_callouts        what bullshit Seven flagged (his or yours)
  · bullshit_detector     build hygiene snapshot

Output: a single markdown document written to:
    audit/seven_daily_<YYYY-MM-DD>.md

Public API:
    compose_daily(now=None) -> dict   {date, path, body, summary}
    last_brief() -> dict | None
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT = ROOT / "audit"

_DEFAULT_NEWS_FEEDS: tuple[tuple[str, str], ...] = (
    ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
    ("Hacker News", "https://hnrss.org/frontpage"),
)


def _db_path() -> str:
    return os.environ.get("SWARM_MEMORY_DB") \
        or os.environ.get("SWARM_DB_PATH") \
        or str(ROOT / "swarm_memory.db")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _safe(con, sql, *args) -> list:
    try:
        return list(con.execute(sql, args).fetchall())
    except sqlite3.OperationalError:
        return []


def _episode_narrative(rows: list) -> str:
    if not rows:
        return "_The day was quiet — no episodes captured._"
    lines = []
    for r in rows[:8]:
        when = _dt.datetime.fromtimestamp(r["ts"]).strftime("%H:%M")
        kind = r["kind"] or "?"
        actor = r["actor"] or "?"
        action = r["action"] or "?"
        rec = r["record_id"] or ""
        lines.append(f"- `{when}` **{actor}** · _{kind}_ → {action} `{rec}`")
    if len(rows) > 8:
        lines.append(f"- _…and {len(rows) - 8} more_")
    return "\n".join(lines)


def _beliefs_block(rows: list) -> str:
    if not rows:
        return "_No beliefs touched today._"
    lines = []
    for r in rows[:10]:
        lines.append(f"- **{r['subject']}** · _{r['predicate']}_ = `{r['object']}` (conf={r['confidence']:.2f})")
    return "\n".join(lines)


def _curiosity_block(rows: list) -> str:
    if not rows:
        return "_Nothing wondering — Seven is settled._"
    lines = []
    for r in rows[:6]:
        lines.append(f"- `#{r['id']}` ({r['asked_by']}, sal={r['salience']:.2f}) — {r['question']}")
    return "\n".join(lines)


def _learnings_block(rows: list) -> tuple[str, int, int]:
    pos = sum(1 for r in rows if r["kind"] == "positive")
    neg = sum(1 for r in rows if r["kind"] == "negative")
    if not rows:
        return "_No reactions captured today._", 0, 0
    lines = []
    for r in rows[:6]:
        sym = "🟢" if r["kind"] == "positive" else "🔴"
        when = _dt.datetime.fromtimestamp(r["ts"]).strftime("%H:%M")
        trig = r["trigger"] or ""
        lines.append(f"- {sym} `{when}` _{trig!r}_ → {(r['seven_msg'] or '')[:80].strip()!r}")
    return "\n".join(lines), pos, neg


def _callouts_block(rows: list) -> tuple[str, int, int]:
    if not rows:
        return "_No callouts — clean signal all day._", 0, 0
    user_n = sum(1 for r in rows if r["target"] == "user")
    seven_n = sum(1 for r in rows if r["target"] == "seven")
    lines = []
    for r in rows[:8]:
        sym = {"info": "·", "warn": "⚠️", "callout": "🛑"}.get(r["severity"], "·")
        when = _dt.datetime.fromtimestamp(r["ts"]).strftime("%H:%M")
        lines.append(
            f"- `{when}` {sym} **{r['target']}/{r['rule']}** — _{(r['snippet'] or '')[:80]!r}_ → {r['note']}"
        )
    return "\n".join(lines), user_n, seven_n


def _detector_block() -> tuple[str, dict]:
    try:
        from ops.bullshit_detector import scan
        d = scan()
    except Exception as exc:  # noqa: BLE001
        return f"_detector unavailable: {exc}_", {}
    glyph = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(d.get("stamp"), "⚪")
    body = (
        f"{glyph} **{d.get('stamp')}** · score {d.get('score')}/100 · "
        f"crit {d.get('by_severity', {}).get('critical', 0)} · "
        f"warn {d.get('by_severity', {}).get('warning', 0)} · "
        f"info {d.get('by_severity', {}).get('info', 0)} · "
        f"files {d.get('files_scanned', 0)}"
    )
    return body, d


def _html_to_text(raw: str) -> str:
    if not raw:
        return ''
    text = re.sub(r'<[^>]+>', ' ', raw)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_image_urls(raw: str) -> list[str]:
    if not raw:
        return []
    out = re.findall(r'https?://[^\s\"\'>]+\.(?:png|jpg|jpeg|webp|gif)', raw, flags=re.IGNORECASE)
    # Preserve order while deduping.
    seen: set[str] = set()
    uniq: list[str] = []
    for url in out:
        if url in seen:
            continue
        seen.add(url)
        uniq.append(url)
    return uniq


def _source_name(sub: dict) -> str:
    title = str(sub.get('title') or '').strip()
    if title:
        return title
    url = str(sub.get('url') or '').strip()
    return url.replace('https://', '').replace('http://', '')[:60] if url else 'unknown source'


def _collect_articles(max_feeds: int = 4, per_feed: int = 4) -> tuple[list[dict], list[str]]:
    """Pull live RSS/Atom items from enabled subscriptions.

    Returns (articles, issues). We degrade gracefully if feeds are absent or
    network/content parsing fails.
    """
    try:
        from core import feeds as _feeds
    except Exception as exc:  # noqa: BLE001
        return [], [f'feeds unavailable: {exc}']

    issues: list[str] = []
    articles: list[dict] = []
    subs = _feeds.list_subscriptions('seven')
    enabled = [s for s in subs if bool(s.get('enabled')) and s.get('kind') in ('rss', 'atom')]
    if not enabled:
        # Honest fallback: pull from known public feeds if the operator has
        # not configured personal subscriptions yet.
        enabled = [
            {'title': title, 'url': url, 'kind': 'rss', 'enabled': True}
            for title, url in _DEFAULT_NEWS_FEEDS
        ]
    for sub in enabled[:max_feeds]:
        url = str(sub.get('url') or '').strip()
        if not url:
            continue
        try:
            rows = _feeds.fetch_rss(url, limit=per_feed, timeout=6.0)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{_source_name(sub)}: {exc}")
            continue
        for row in rows:
            title = str(row.get('title') or '').strip()
            if not title:
                continue
            raw_summary = str(row.get('summary') or '')
            plain_summary = _html_to_text(raw_summary)
            images = _extract_image_urls(raw_summary)
            articles.append({
                'source': _source_name(sub),
                'title': title,
                'link': str(row.get('link') or '').strip(),
                'published': str(row.get('published') or '').strip(),
                'summary': plain_summary,
                'images': images,
            })
    return articles, issues


def _article_score(article: dict) -> int:
    text = (article.get('title', '') + ' ' + article.get('summary', '')).lower()
    high = ('security', 'breach', 'vulnerability', 'ransomware', 'earnings',
            'inflation', 'rate', 'regulation', 'ai', 'gpu', 'chip', 'market')
    med = ('policy', 'risk', 'outage', 'latency', 'cloud', 'supply', 'trade')
    score = 0
    for w in high:
        if w in text:
            score += 3
    for w in med:
        if w in text:
            score += 1
    return score


def _topic_label(article: dict) -> str:
    text = (article.get('title', '') + ' ' + article.get('summary', '')).lower()
    if any(k in text for k in ('security', 'breach', 'vulnerability', 'ransomware', 'patch')):
        return 'Cyber'
    if any(k in text for k in ('earnings', 'market', 'stock', 'bond', 'rate', 'inflation')):
        return 'Markets'
    if any(k in text for k in ('ai', 'model', 'gpu', 'chip', 'llm')):
        return 'AI'
    if any(k in text for k in ('policy', 'law', 'regulation', 'compliance')):
        return 'Policy'
    return 'General'


def _bottom_up_explanation(article: dict) -> tuple[str, str, str, str]:
    title = article.get('title', '')
    summary = article.get('summary', '')
    if len(summary) > 260:
        summary = summary[:257].rstrip() + '...'
    signal = f"The direct signal is: {title}."
    system = "This can alter operational risk, cost curves, or execution speed within the next few cycles."
    stack = "If this touches your stack, priorities shift in scheduling, hardening, or budget allocation before product work."
    action = "Track one measurable follow-up today: impact on latency, cost, incident exposure, or delivery confidence."
    if summary:
        signal = f"The direct signal is: {summary}"
    return signal, system, stack, action


def _newsroom_block(articles: list[dict], issues: list[str]) -> tuple[str, str]:
    if not articles:
        fallback = "_No feed articles available today. Add RSS/Atom sources in Feeds to enable article-grounded newsroom analysis._"
        if issues:
            fallback += "\n\n" + "\n".join(f"- feed issue: {i}" for i in issues[:5])
        return fallback, "_No newsroom article-mix chart available without feed articles._"

    ranked = sorted(articles, key=_article_score, reverse=True)
    top = ranked[:6]
    cards: list[str] = []
    topic_counts: dict[str, int] = {}
    for idx, a in enumerate(top, start=1):
        topic = _topic_label(a)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        score = _article_score(a)
        signal, system, stack, action = _bottom_up_explanation(a)
        image_md = f"\n![{a['title']}]({a['images'][0]})\n" if a.get('images') else ""
        link = a.get('link') or ''
        source_line = f"Source: **{a.get('source') or 'unknown'}**"
        if link:
            source_line += f" · [{link}]({link})"
        if a.get('published'):
            source_line += f" · {a['published']}"
        cards.append(
            f"### {idx}. {a['title']}\n"
            f"{source_line}\n"
            f"{image_md}"
            f"- Relevance score: **{score}** · Topic: **{topic}**\n"
            f"- What happened: {signal}\n"
            f"- Bottom-up (why you should care):\n"
            f"  - Layer 1 (signal): {signal}\n"
            f"  - Layer 2 (system): {system}\n"
            f"  - Layer 3 (your stack): {stack}\n"
            f"  - Action today: {action}\n"
            f"\n<details><summary>Article excerpt</summary>\n\n{a.get('summary') or '_No summary provided by source._'}\n\n</details>"
        )

    topic_pie = "\n".join(f"    \"{k}\" : {v}" for k, v in sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0])))
    table_lines = [
        "| # | Topic | Relevance | Source |",
        "|---|---|---:|---|",
    ]
    for idx, a in enumerate(top, start=1):
        table_lines.append(
            f"| {idx} | {_topic_label(a)} | {_article_score(a)} | {a.get('source') or 'unknown'} |"
        )
    chart_block = (
        "```mermaid\n"
        "pie title Story Topic Mix\n"
        f"{topic_pie}\n"
        "```\n\n"
        + "\n".join(table_lines)
    )

    if issues:
        cards.append("#### Feed issues\n" + "\n".join(f"- {i}" for i in issues[:5]))
    return "\n\n".join(cards), chart_block


def _ops_chart(episodes_n: int, beliefs_n: int, pos_n: int, neg_n: int, user_n: int, seven_n: int) -> str:
    return (
        "```mermaid\n"
        "xychart-beta\n"
        "    title \"Daily Operational Signals\"\n"
        "    x-axis [episodes, beliefs, positive, negative, user_callouts, seven_callouts]\n"
        f"    bar [{episodes_n}, {beliefs_n}, {pos_n}, {neg_n}, {user_n}, {seven_n}]\n"
        "```"
    )


def _conviction_summary(callouts_rows: list) -> str:
    """Average a tiny conviction estimate over the day's Seven turns."""
    seven_callouts = [r for r in callouts_rows if r["target"] == "seven"]
    if not seven_callouts:
        return "🟢 high — no hedge-words or contradictions on Seven's side today."
    n = len(seven_callouts)
    if n <= 2:
        return f"🟡 mostly clean — {n} witness flags on Seven's responses today."
    return f"🔴 wobbly — {n} witness flags on Seven's responses today; tighten up."


def compose_daily(now: float | None = None) -> dict:
    """Compose and write today's brief. Returns {date, path, body, summary}."""
    now_ts = now if now is not None else time.time()
    date = _dt.date.fromtimestamp(now_ts)
    iso = date.strftime("%Y-%m-%d")
    midnight = _dt.datetime.combine(date, _dt.time.min).timestamp()

    con = _connect()
    try:
        episodes = _safe(con,
            "SELECT ts, kind, record_id, action, actor FROM seven_episodes "
            "WHERE ts >= ? ORDER BY ts DESC LIMIT 50", midnight)
        beliefs = _safe(con,
            "SELECT subject, predicate, object, confidence, last_seen "
            "FROM seven_beliefs WHERE last_seen >= ? "
            "ORDER BY confidence DESC, last_seen DESC LIMIT 12", midnight)
        curiosities = _safe(con,
            "SELECT id, asked_by, question, salience FROM curiosity_questions "
            "WHERE status='open' ORDER BY salience DESC, asked_at DESC LIMIT 8")
        learnings = _safe(con,
            "SELECT ts, kind, trigger, seven_msg FROM seven_learnings "
            "WHERE ts >= ? ORDER BY ts DESC LIMIT 12",
            int(midnight))
        callouts = _safe(con,
            "SELECT ts, target, severity, rule, snippet, note FROM seven_callouts "
            "WHERE ts >= ? ORDER BY ts DESC LIMIT 30", midnight)
    finally:
        con.close()

    learnings_md, pos_n, neg_n = _learnings_block(learnings)
    callouts_md, user_n, seven_n = _callouts_block(callouts)
    detector_md, det = _detector_block()
    conviction_md = _conviction_summary(callouts)
    articles, feed_issues = _collect_articles()
    newsroom_md, charts_md = _newsroom_block(articles, feed_issues)
    ops_chart_md = _ops_chart(len(episodes), len(beliefs), pos_n, neg_n, user_n, seven_n)

    summary = (
        f"episodes={len(episodes)} beliefs_touched={len(beliefs)} "
        f"open_curiosities={len(curiosities)} learnings_pos={pos_n} learnings_neg={neg_n} "
        f"callouts_user={user_n} callouts_seven={seven_n} "
        f"detector={det.get('stamp', '?')}/{det.get('score', '?')}"
    )

    body = f"""# Seven's Daily Brief · {iso}

> Generated by `agents/seven/daily_brief.compose_daily()` at \
{_dt.datetime.fromtimestamp(now_ts).strftime('%H:%M:%S')} local. \
This is what Seven noticed today.

## Conviction
{conviction_md}

## Build hygiene
{detector_md}

## Newsroom (article-grounded)
{newsroom_md}

## Visuals
{ops_chart_md}

{charts_md}

## What happened
{_episode_narrative(episodes)}

## What I now hold to be true
{_beliefs_block(beliefs)}

## What I'm still wondering about
{_curiosity_block(curiosities)}

## How the conversation went
- positive reactions: **{pos_n}**
- negative reactions: **{neg_n}**

{learnings_md}

## Bullshit ledger (witness)
- on you: **{user_n}**  ·  on me: **{seven_n}**

{callouts_md}

---
_summary_: `{summary}`
"""

    AUDIT.mkdir(exist_ok=True)
    out_path = AUDIT / f"seven_daily_{iso}.md"
    out_path.write_text(body)
    return {"date": iso, "path": str(out_path), "body": body, "summary": summary}


def last_brief() -> dict | None:
    if not AUDIT.is_dir():
        return None
    files = sorted(AUDIT.glob("seven_daily_*.md"))
    if not files:
        return None
    p = files[-1]
    return {"date": p.stem.replace("seven_daily_", ""),
            "path": str(p), "body": p.read_text()}


__all__ = ["compose_daily", "last_brief"]
