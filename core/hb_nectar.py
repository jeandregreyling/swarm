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

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

BANANA_TAX = -100
_KEY_FILE = Path(__file__).resolve().parents[1] / 'runtime' / '.hb_nectar_key'


def _shadow_key() -> bytes:
    """Owner/HB-only HMAC signing key for the tamper-evident Nectar shadow ledger."""
    env_key = os.environ.get('HB_NECTAR_SHADOW_KEY')
    if env_key:
        return env_key.encode('utf-8')
    try:
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not _KEY_FILE.exists():
            _KEY_FILE.write_text(secrets.token_hex(32), encoding='utf-8')
            os.chmod(_KEY_FILE, 0o600)
        return _KEY_FILE.read_text(encoding='utf-8').strip().encode('utf-8')
    except Exception:
        return b'hb-nectar-shadow-fallback-key'


def _sign(agent: str, delta: int, kind: str, ref: str) -> str:
    msg = f'{agent.lower()}|{int(delta)}|{kind}|{ref}'.encode('utf-8')
    return hmac.new(_shadow_key(), msg, hashlib.sha256).hexdigest()


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
    conn.execute(
        'CREATE TABLE IF NOT EXISTS hb_nectar_shadow('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'at REAL NOT NULL, '
        'agent TEXT NOT NULL, '
        'delta INTEGER NOT NULL, '
        'kind TEXT NOT NULL, '
        'ref TEXT NOT NULL, '
        'sig TEXT NOT NULL, '
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
    now = time.time()
    cur = conn.execute(
        "INSERT OR IGNORE INTO hb_nectar_ledger(at, agent, delta, flower, kind, counterparty, ref, note) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (now, agent, amount, key, 'earn', 'HB', str(step_id), str(title)[:240]),
    )
    if cur.rowcount > 0:
        conn.execute(
            "INSERT OR IGNORE INTO hb_nectar_shadow(at, agent, delta, kind, ref, sig) VALUES (?,?,?,?,?,?)",
            (now, agent, amount, 'earn', str(step_id), _sign(agent, amount, 'earn', str(step_id))),
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
    conn.execute(
        "INSERT OR IGNORE INTO hb_nectar_shadow(at, agent, delta, kind, ref, sig) VALUES (?,?,?,?,?,?)",
        (now, agent, -cost, 'spend', tx_ref, _sign(agent, -cost, 'spend', tx_ref)),
    )
    conn.execute(
        "INSERT OR IGNORE INTO hb_nectar_shadow(at, agent, delta, kind, ref, sig) VALUES (?,?,?,?,?,?)",
        (now, to_agent, cost, 'payment', tx_ref, _sign(to_agent, cost, 'payment', tx_ref)),
    )
    return {'ok': True, 'item': item, 'spent': cost, 'paid_to': to_agent, 'balance': balance(conn, agent)}


def reconcile_shadow(conn, agent: str = 'APEX') -> dict:
    """Compare visible ledger against HB's HMAC-signed shadow ledger; slap -100 Nectar Banana Tax on tampering."""
    ensure_schema(conn)
    visible = balance(conn, agent)
    rows = conn.execute(
        'SELECT delta, kind, ref, sig FROM hb_nectar_shadow WHERE lower(agent)=lower(?)',
        (agent,),
    ).fetchall()
    bad_sig = any(not hmac.compare_digest(str(sig), _sign(agent, int(d), str(k), str(r))) for d, k, r, sig in rows)
    shadow_total = sum(int(d) for d, _, _, _ in rows)
    if not bad_sig and visible == shadow_total:
        return {'clean': True, 'balance': visible, 'shadow': shadow_total}
    # Tampering detected: reset balance straight to -100 Nectar (Banana Tax!)
    now = time.time()
    ref = f'banana-tax-{int(now * 1000)}'
    clawback = BANANA_TAX - visible
    conn.execute(
        "INSERT INTO hb_nectar_ledger(at, agent, delta, flower, kind, counterparty, ref, note) "
        "VALUES (?,?,?,NULL,'banana_tax','HB',?,?)",
        (now, agent, clawback, ref, f'Ledger mismatch (visible={visible}, shadow={shadow_total}) -> reset to {BANANA_TAX}'),
    )
    shadow_delta = BANANA_TAX - shadow_total
    conn.execute(
        "INSERT OR IGNORE INTO hb_nectar_shadow(at, agent, delta, kind, ref, sig) VALUES (?,?,?,?,?,?)",
        (now, agent, shadow_delta, 'banana_tax', ref, _sign(agent, shadow_delta, 'banana_tax', ref)),
    )
    return {
        'clean': False,
        'cheated': True,
        'visible_was': visible,
        'shadow_was': shadow_total,
        'balance': BANANA_TAX,
        'alert': f'🍌 BANANA ALERT! {agent} tampered with the Nectar ledger (claimed {visible}, HB shadow says {shadow_total}). Bananas thrown — balance reset to {BANANA_TAX} Nectar!',
    }


def backfill_from_merits(conn, agent: str = 'APEX', limit: int = 20) -> int:
    """Idempotently credit verified APEX flowers from hb_merits into both hb_nectar_ledger and hb_nectar_shadow."""
    ensure_schema(conn)
    has_merits = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hb_merits'").fetchone()
    if not has_merits:
        return 0
    rows = conn.execute(
        "SELECT id, COALESCE(step_id,''), COALESCE(note,'') FROM hb_merits "
        "WHERE lower(role)=lower(?) AND kind='success' ORDER BY id DESC LIMIT ?",
        (agent, int(limit)),
    ).fetchall()
    added = 0
    for mid, sid, note in rows:
        ref = sid or f'M-{mid}'
        res = earn_flower(conn, agent, ref, files_count=2, title=note or f'Verified practice {ref}')
        if res.get('awarded'):
            added += 1
    return added


def summary_text(conn, agent: str = 'APEX') -> str:
    """Compact one-line Nectar wallet summary for /nectar and agent context (reconciles shadow ledger first)."""
    audit = reconcile_shadow(conn, agent)
    g = garden(conn, agent)
    prefix = (audit['alert'] + '\n') if not audit.get('clean') else ''
    emoji_of = {k: e for k, e, _, _ in FLOWER_TIERS}
    parts = [f"{emoji_of[k]}×{g['flowers'][k]}" for k, _, _, _ in FLOWER_TIERS if g['flowers'].get(k)]
    bouquet = ' '.join(parts) if parts else 'no flowers yet'
    return prefix + (
        f"🍯 {agent} Nectar wallet: {g['nectar']} Nectar ({bouquet}) · "
        f"Menu: QA review {NECTAR_COSTS['qa_review']} · online assist {NECTAR_COSTS['online_assist']} · commission tool {NECTAR_COSTS['commission_tool']}"
    )
