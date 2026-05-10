"""Money Hub newsletter generation.

Builds a local-first market/business digest from the live Financial, Trading,
and Business pillar summaries, then stores it in Knowledge Center surfaces.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from utils.db._connection import get_connection
from utils.db.knowledge import write_knowledge


DOC_PREFIX = "MONEY_HUB_DAILY_NEWSLETTER"
TASK_NAME = "money_hub_daily_newsletter"


def _summary_payload() -> dict[str, Any]:
    from frontend.blueprints import business_bp, financial_bp, trading_bp

    return {
        "financial": financial_bp.summary_for_seven(),
        "trading": trading_bp.summary_for_seven(),
        "business": business_bp.summary_for_seven(),
    }


def compose_newsletter(now: datetime | None = None) -> dict[str, str]:
    """Return the current Money Hub newsletter without writing it."""
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    payload = _summary_payload()
    financial = payload["financial"]
    trading = payload["trading"]
    business = payload["business"]

    lines = [
        f"# Money Hub Daily Newsletter - {day}",
        "",
        "Source provenance:",
        "- financial: /api/financial/summary",
        "- trading: /api/trading/summary",
        "- business: /api/business/summary",
        "- scheduler: Tasker PYTHON money_hub_daily_newsletter",
        "",
        "## Financial Desk",
        f"- Open items: {financial.get('open', 0)}",
        f"- By class: {financial.get('by_class', {})}",
        f"- High conviction: {financial.get('high_conviction', [])}",
        "",
        "## Trading Desk",
        f"- Open signals: {trading.get('open', 0)}",
        f"- By side: {trading.get('by_side', {})}",
        f"- Realised P/L: {trading.get('realised_pnl', 0.0)}",
        f"- Top signals: {trading.get('top', [])}",
        "",
        "## Business Desk",
        f"- Unreconciled entries: {business.get('unreconciled', 0)}",
        f"- Net by currency: {business.get('net_by_currency', {})}",
        f"- By kind: {business.get('by_kind', {})}",
        f"- Recent entries: {business.get('recent', [])}",
        "",
        "## Next Review",
        "Tasker should refresh this daily so Show Me The Money has a durable Knowledge trail instead of transient UI state.",
    ]
    return {
        "day": day,
        "doc_name": f"{DOC_PREFIX}_{day}.md",
        "content": "\n".join(lines),
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


def ensure_tasker_schedule() -> int:
    """Ensure the daily Money Hub newsletter task exists in Tasker."""
    from fridays.scheduler import add_task

    return int(add_task(TASK_NAME, "daily 07:20", "PYTHON", TASK_NAME, created_by="system") or 0)


def run() -> str:
    doc = write_newsletter()
    task_id = ensure_tasker_schedule()
    return f"money_hub_daily_newsletter ok - {doc['doc_name']} - task_id={task_id}"


if __name__ == "__main__":
    print(run())
