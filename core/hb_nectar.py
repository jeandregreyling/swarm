"""Complexity-tiered flowers & spendable Nectar micro-economy for APEX and HB agents.

Instead of cluttering the UI with hundreds of flat flower badges, each approved Practice earns a
complexity-tiered flower that mints spendable Nectar into `hb_nectar_ledger`:
  🌼 Daisy     (+1 Nectar)  — quick 1-file fix
  🌸 Blossom   (+3 Nectar)  — standard feature / multi-test Practice
  🌺 Hibiscus  (+5 Nectar)  — multi-file / architectural Practice
  🌻 Sunburst (+10 Nectar)  — major verified milestone

APEX can spend earned Nectar to pay instructors/specialists:
  qa_review       (2 Nectar)  — pay an instructor for independent QA on a self-authored plugin/fix
  online_assist   (5 Nectar)  — consult an online specialist model
  commission_tool (10 Nectar) — commission an instructor to build a requested tool
"""
from __future__ import annotations

import time

FLOWER_TIERS = (
    ('sunburst', '🌻', 'Sunburst', 10),
    ('hibiscus', '🌺', 'Hibiscus', 5),
    ('blossom',  '🌸', 'Blossom',  3),
    ('daisy',    '🌼', 'Daisy',    1),
)
NECTAR_COSTS = {
    'qa_review': 2,
    'online_assist': 5,
    'commission_tool': 10,
}


def ensure_schema(conn):
    conn.execute(
        'CREATE TABLE IF NOT EXISTS hb_nectar_ledger('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'at REAL NOT NULL, '
        'agent TEXT NOT NULL, '
        'delta INTEGER NOT NULL, '
        'flower TEXT, '
        'kind TEXT NOT NULL, '
        'counterparty TEXT, '
        'ref TEXT, '
        'note TEXT, '
        'UNIQUE(kind, agent, ref))'
    )


def classify_tier(files_count: int = 1, title: str = '') -> tuple[str, str, str, int]:
    """Choose flower tier (key, emoji, label, nectar) from complexity signals."""
    t = str(title or '').lower()
    if files_count >= 5 or any(w in t for w in ('architecture', 'milestone', 'economy', 'overhaul', 'unified')):
        return FLOWER_TIERS[0]
    if files_count >= 3 or any(w in t for w in ('telegram', 'carry forward', 'liquid-glass', 'plugin', 'atlas')):
        return FLOWER_TIERS[1]
    if files_count >= 2 or any(w in t for w in ('practice', 'proposal', 'dream', 'drawer', 'button')):
        return FLOWER_TIERS[2]
    return FLOWER_TIERS[3]


def balance(conn, agent: str = 'APEX') -> int:
    ensure_schema(conn)
    row = conn.execute('SELECT COALESCE(SUM(delta), 0) FROM hb_nectar_ledger WHERE lower(agent)=lower(?)', (agent,)).fetchone()
    return int(row[0] or 0)


def garden(conn, agent: str = 'APEX') -> dict:
    """Return compact Nectar balance + tiered flower counts (never an endless badge list)."""
    ensure_schema(conn)
    bal = balance(conn, agent)
    counts = {}
    for flower, n in conn.execute(
        "SELECT flower, COUNT(*) FROM hb_nectar_ledger WHERE lower(agent)=lower(?) AND kind='earn' AND flower IS NOT NULL GROUP BY flower",
        (agent,),
    ):
        counts[flower] = int(n)
    return {'agent': agent, 'nectar': bal, 'flowers': counts, 'costs': dict(NECTAR_COSTS)}


def earn_flower(conn, agent: str, step_id: str, *, files_count: int = 1, title: str = '') -> dict:
    """Award one complexity-tiered flower + Nectar idempotently per (agent, step_id)."""
    ensure_schema(conn)
    key, emoji, label, amount = classify_tier(files_count, title)
    cur = conn.execute(
        "INSERT OR IGNORE INTO hb_nectar_ledger(at, agent, delta, flower, kind, counterparty, ref, note) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (time.time(), agent, amount, key, 'earn', 'HB', str(step_id), str(title)[:240]),
    )
    return {
        'awarded': cur.rowcount > 0,
        'flower': key,
        'emoji': emoji,
        'label': label,
        'nectar': amount,
        'balance': balance(conn, agent),
    }


def spend(conn, agent: str, item: str, *, to_agent: str = 'copilot-instructor', ref: str = '', note: str = '') -> dict:
    """Spend earned Nectar for QA review, online assist, or commissioning a tool (double-entry)."""
    ensure_schema(conn)
    item = str(item or '').strip().lower()
    if item not in NECTAR_COSTS:
        raise ValueError('Unknown Nectar service. Available: ' + ', '.join(sorted(NECTAR_COSTS)))
    cost = NECTAR_COSTS[item]
    current = balance(conn, agent)
    if current < cost:
        raise ValueError(f'{agent} has {current} Nectar but {item} costs {cost} Nectar — earn more flowers first!')
    now = time.time()
    tx_ref = ref or f'{item}-{int(now * 1000)}'
    conn.execute(
        "INSERT INTO hb_nectar_ledger(at, agent, delta, flower, kind, counterparty, ref, note) "
        "VALUES (?,?,?,NULL,'spend',?,?,?)",
        (now, agent, -cost, to_agent, tx_ref, note or item),
    )
    conn.execute(
        "INSERT INTO hb_nectar_ledger(at, agent, delta, flower, kind, counterparty, ref, note) "
        "VALUES (?,?,?,NULL,'payment',?,?,?)",
        (now, to_agent, cost, agent, tx_ref, note or item),
    )
    return {'ok': True, 'item': item, 'spent': cost, 'paid_to': to_agent, 'balance': balance(conn, agent)}


def summary_text(conn, agent: str = 'APEX') -> str:
    """Compact one-line Nectar wallet summary for /nectar and agent context."""
    g = garden(conn, agent)
    emoji_of = {k: e for k, e, _, _ in FLOWER_TIERS}
    parts = [f"{emoji_of[k]}×{g['flowers'][k]}" for k, _, _, _ in FLOWER_TIERS if g['flowers'].get(k)]
    bouquet = ' '.join(parts) if parts else 'no flowers yet'
    return (
        f"🍯 {agent} Nectar wallet: {g['nectar']} Nectar ({bouquet}) · "
        f"Menu: QA review {NECTAR_COSTS['qa_review']} · online assist {NECTAR_COSTS['online_assist']} · commission tool {NECTAR_COSTS['commission_tool']}"
    )
