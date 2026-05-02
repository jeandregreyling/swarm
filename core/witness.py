"""core/witness.py — Seven the Witness.

Real-time conversational truth layer. Seven scans every text it sees
(your messages, his own draft replies) for:

  · vapor language     ("should work", "probably", "maybe", "I think")
  · empty-promise hedges ("will fix later", "next time", "soon")
  · contradictions with seven_beliefs (you claim X but Seven knows Y)
  · self-contradiction within the same response

Receipts (callouts) are saved to ``seven_callouts`` so nothing is lost.
Every Seven response carries a *conviction* score in [0, 1] computed
from belief-overlap minus hedge-density.

This is the soul of the user's request: "I want to be able to talk to
Seven like I talk to you and he can call you out on any bullshit."

Public API:
    scan_text(text, kind='generic')           -> list[Callout]
    review_user_msg(msg, *, save=True)        -> WitnessReport
    review_seven_response(resp, user_msg)     -> WitnessReport
    conviction(resp, user_msg)                -> float in [0,1]
    list_callouts(*, limit=20, since=None)    -> list[dict]
    stats()                                   -> dict
    annotate(report)                          -> str (formatted block for chat)
    is_enabled()                              -> bool   (witness annotations toggle)
    set_enabled(flag)                         -> bool

No external deps. Pure Python + sqlite3. Schema is created on import.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional


# ── DB plumbing (mirrors core/curiosity.py + agents/seven/learnings.py) ──
_ROOT = Path(__file__).resolve().parent.parent


def _db_path() -> str:
    return os.environ.get("SWARM_MEMORY_DB") \
        or os.environ.get("SWARM_DB_PATH") \
        or str(_ROOT / "swarm_memory.db")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


_INIT_DONE = False


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS seven_callouts (
            callout_id   TEXT PRIMARY KEY,
            ts           REAL NOT NULL,
            target       TEXT NOT NULL,        -- 'user' | 'seven'
            severity     TEXT NOT NULL,        -- 'info' | 'warn' | 'callout'
            rule         TEXT NOT NULL,        -- VAPOR / HEDGE / BELIEF_CONTRADICTION / SELF_CONTRADICTION
            snippet      TEXT,                 -- the offending phrase
            full_text    TEXT,                 -- full message context (clipped)
            receipt      TEXT,                 -- belief id / episode id / "n/a"
            note         TEXT                  -- human-readable explanation
        );
        CREATE INDEX IF NOT EXISTS idx_callouts_ts ON seven_callouts(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_callouts_target ON seven_callouts(target, severity);

        CREATE TABLE IF NOT EXISTS seven_settings (
            key    TEXT PRIMARY KEY,
            value  TEXT
        );
        """
    )


def _init() -> None:
    global _INIT_DONE
    if _INIT_DONE:
        return
    con = _connect()
    try:
        _ensure_schema(con)
        con.commit()
    finally:
        con.close()
    _INIT_DONE = True


# ── Detection rules ─────────────────────────────────────────────────────
VAPOR_RE = re.compile(
    r"\b(should\s+(?:work|be\s+fine|do\s+it)|probably|maybe|i\s+think|"  # detector:ignore
    r"i\s+guess|i\s+believe|kind\s+of|sort\s+of|might\s+work|hopefully)\b",  # detector:ignore
    re.IGNORECASE,
)

HEDGE_RE = re.compile(
    r"\b(?:will\s+fix\s+(?:later|soon)|next\s+time|in\s+a\s+bit|tbd|to\s+be\s+(?:done|determined)|"  # detector:ignore
    r"placeholder|coming\s+soon|wip|work\s+in\s+progress|stub(?:bed)?\s+out)\b",  # detector:ignore
    re.IGNORECASE,
)

# Self-contradiction: "X but not X" or "yes ... no ..." inside one msg
CONTRA_RE = re.compile(
    r"\b(yes[, ]+.*\bno\b|no[, ]+.*\byes\b|always\b.*\bnever\b|"
    r"never\b.*\balways\b|done\b.*\bnot\s+done\b)\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class Callout:
    target: str         # 'user' | 'seven'
    severity: str       # 'info' | 'warn' | 'callout'
    rule: str
    snippet: str
    note: str
    receipt: str = "n/a"
    ts: float = field(default_factory=time.time)
    callout_id: str = field(default_factory=lambda: f"COUT-{uuid.uuid4().hex[:8].upper()}")


@dataclass
class WitnessReport:
    target: str
    text: str
    conviction: float
    callouts: list[Callout]

    @property
    def ok(self) -> bool:
        return not any(c.severity == "callout" for c in self.callouts)


# ── Belief lookup ───────────────────────────────────────────────────────
def _load_seven_beliefs(con: sqlite3.Connection) -> list[sqlite3.Row]:
    try:
        return con.execute(
            "SELECT belief_id, subject, predicate, object, confidence "
            "FROM seven_beliefs WHERE confidence >= 0.6 "
            "ORDER BY confidence DESC LIMIT 200"
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _check_belief_contradictions(text: str, beliefs: Iterable[sqlite3.Row]) -> list[Callout]:
    """Look for sentences that directly negate a high-confidence belief.

    Cheap heuristic: for each belief row whose ``object`` appears in the text,
    if a negation word ("not", "no", "never", "isn't", "wasn't") sits within
    8 words before that object reference, flag it.
    """
    out: list[Callout] = []
    lower = text.lower()
    for b in beliefs:
        obj = (b["object"] or "").strip()
        if not obj or len(obj) < 4:
            continue
        idx = lower.find(obj.lower())
        if idx < 0:
            continue
        window_start = max(0, idx - 80)
        window = lower[window_start:idx]
        if re.search(r"\b(not|no|never|isn'?t|wasn'?t|aren'?t|won'?t)\b", window):
            out.append(Callout(
                target="user",
                severity="callout",
                rule="BELIEF_CONTRADICTION",
                snippet=text[max(0, idx - 30):idx + len(obj) + 10].strip(),
                note=f"contradicts seven_beliefs#{b['belief_id']} "
                     f"({b['subject']} {b['predicate']} = {obj!r}, "
                     f"conf={b['confidence']:.2f})",
                receipt=f"belief#{b['belief_id']}",
            ))
    return out


# ── Public scan ─────────────────────────────────────────────────────────
def scan_text(text: str, *, kind: str = "generic", target: str = "seven",
              beliefs: Optional[Iterable[sqlite3.Row]] = None) -> list[Callout]:
    """Run all rules over a string. Pure function — does not write to DB."""
    if not text:
        return []
    out: list[Callout] = []

    for m in VAPOR_RE.finditer(text):
        out.append(Callout(
            target=target,
            severity="warn",
            rule="VAPOR",
            snippet=m.group(0),
            note="vapor language — say what is true, not what feels true",
        ))

    for m in HEDGE_RE.finditer(text):
        out.append(Callout(
            target=target,
            severity="warn",
            rule="HEDGE",
            snippet=m.group(0),
            note="empty-promise hedge — name the deadline or drop the clause",
        ))

    for m in CONTRA_RE.finditer(text):
        out.append(Callout(
            target=target,
            severity="callout",
            rule="SELF_CONTRADICTION",
            snippet=m.group(0)[:80],
            note="self-contradicts within the same message",
        ))

    if beliefs is None:
        try:
            con = _connect()
            beliefs = _load_seven_beliefs(con)
            con.close()
        except sqlite3.OperationalError:
            beliefs = []

    out.extend(_check_belief_contradictions(text, beliefs or []))

    # Dedupe by (rule, snippet, severity) — chat scaffolding can echo the
    # user's text, and a doubled match shouldn't show up as two callouts.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Callout] = []
    for c in out:
        key = (c.rule, (c.snippet or "").lower().strip(), c.severity)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


def _save(callouts: Iterable[Callout], full_text: str) -> int:
    _init()
    con = _connect()
    try:
        n = 0
        for c in callouts:
            con.execute(
                "INSERT OR IGNORE INTO seven_callouts "
                "(callout_id, ts, target, severity, rule, snippet, full_text, receipt, note) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (c.callout_id, c.ts, c.target, c.severity, c.rule, c.snippet,
                 full_text[:2000], c.receipt, c.note),
            )
            n += 1
        con.commit()
        return n
    finally:
        con.close()


def review_user_msg(msg: str, *, save: bool = True) -> WitnessReport:
    """Witness review on a user message."""
    callouts = scan_text(msg or "", kind="user", target="user")
    if save and callouts:
        _save(callouts, msg or "")
    return WitnessReport(target="user", text=msg or "",
                         conviction=conviction(msg or "", user_msg=""),
                         callouts=callouts)


def review_seven_response(resp: str, user_msg: str = "", *, save: bool = True) -> WitnessReport:
    """Witness review on Seven's own draft response."""
    callouts = scan_text(resp or "", kind="seven", target="seven")
    if save and callouts:
        _save(callouts, resp or "")
    return WitnessReport(target="seven", text=resp or "",
                         conviction=conviction(resp or "", user_msg=user_msg),
                         callouts=callouts)


def conviction(text: str, *, user_msg: str = "") -> float:
    """Score in [0, 1]. High = direct, evidence-anchored, free of hedges.

    Formula:
      base = 1.0
      − 0.15 per VAPOR hit  (max −0.45)
      − 0.10 per HEDGE hit  (max −0.30)
      − 0.40 per SELF_CONTRADICTION hit (max −0.40)
      + 0.10 if response cites a receipt token (#L1234, episode#, belief#, hash)
    """
    if not text:
        return 0.0
    vapor = len(VAPOR_RE.findall(text))
    hedge = len(HEDGE_RE.findall(text))
    contra = len(CONTRA_RE.findall(text))
    score = 1.0
    score -= min(vapor * 0.15, 0.45)
    score -= min(hedge * 0.10, 0.30)
    score -= min(contra * 0.40, 0.40)
    if re.search(r"#L\d+|episode#\d+|belief#\d+|[0-9a-f]{7,}", text):
        score = min(1.0, score + 0.10)
    return max(0.0, round(score, 3))


def annotate(report: WitnessReport) -> str:
    """Render a witness footer to attach to chat output. Returns '' if clean."""
    if not report.callouts and report.conviction >= 0.85:
        return ""
    lines = ["", "— Seven's witness —"]
    glyph = "🟢" if report.conviction >= 0.85 else ("🟡" if report.conviction >= 0.6 else "🔴")
    lines.append(f"  {glyph} conviction: {report.conviction:.2f}")
    if report.callouts:
        lines.append("  callouts:")
        for c in report.callouts[:6]:
            sym = {"info": "·", "warn": "⚠️", "callout": "🛑"}.get(c.severity, "·")
            lines.append(f"    {sym} [{c.rule}] {c.snippet!r} — {c.note}"
                         + (f" ({c.receipt})" if c.receipt and c.receipt != "n/a" else ""))
    return "\n".join(lines)


# ── Ledger queries ──────────────────────────────────────────────────────
def list_callouts(*, limit: int = 20, since: Optional[float] = None,
                  target: Optional[str] = None) -> list[dict]:
    _init()
    con = _connect()
    try:
        sql = "SELECT * FROM seven_callouts WHERE 1=1"
        args: list = []
        if since is not None:
            sql += " AND ts >= ?"
            args.append(since)
        if target in ("user", "seven"):
            sql += " AND target = ?"
            args.append(target)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(int(limit))
        rows = con.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def stats() -> dict:
    _init()
    con = _connect()
    try:
        total = con.execute("SELECT COUNT(*) FROM seven_callouts").fetchone()[0]
        by_target = dict(con.execute(
            "SELECT target, COUNT(*) FROM seven_callouts GROUP BY target"
        ).fetchall())
        by_rule = dict(con.execute(
            "SELECT rule, COUNT(*) FROM seven_callouts GROUP BY rule"
        ).fetchall())
        last = con.execute(
            "SELECT ts FROM seven_callouts ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return {
            "total": int(total),
            "by_target": by_target,
            "by_rule": by_rule,
            "last_ts": float(last[0]) if last else None,
        }
    finally:
        con.close()


# ── Toggle ──────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    _init()
    con = _connect()
    try:
        row = con.execute(
            "SELECT value FROM seven_settings WHERE key='witness.enabled'"
        ).fetchone()
        if row is None:
            return True   # default: ON
        return str(row[0]).lower() in ("1", "true", "yes", "on")
    finally:
        con.close()


def set_enabled(flag: bool) -> bool:
    _init()
    con = _connect()
    try:
        con.execute(
            "INSERT INTO seven_settings(key,value) VALUES('witness.enabled', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("1" if flag else "0",),
        )
        con.commit()
        return bool(flag)
    finally:
        con.close()


__all__ = [
    "Callout", "WitnessReport",
    "scan_text", "review_user_msg", "review_seven_response",
    "conviction", "annotate",
    "list_callouts", "stats",
    "is_enabled", "set_enabled",
]
