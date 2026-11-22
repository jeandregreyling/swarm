"""Carry Forward continuity, positive-first lean chat prompt, and focused <=10-tool subsetting for APEX."""
from __future__ import annotations

import time

EA_CHAT_TOOLS = (
    'knowledge_search', 'web_search', 'hb_media_download', 'hb_tasks',
    'hb_service', 'hb_restart', 'memory_search', 'memory_save',
    'reference_lookup', 'hb_custom_tool',
)
CODE_CHAT_TOOLS = (
    'grep_repo', 'read_file', 'propose_patch', 'propose_write_file',
    'run_tests', 'get_diff', 'knowledge_search', 'reference_lookup',
    'hb_service', 'hb_restart',
)


def ensure_schema(conn):
    conn.execute(
        'CREATE TABLE IF NOT EXISTS hb_carry_forward('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'conversation_id INTEGER NOT NULL, '
        'topic TEXT NOT NULL, '
        'outcome TEXT NOT NULL, '
        'confidence TEXT NOT NULL, '
        'tools_used TEXT NOT NULL, '
        'created_at REAL NOT NULL)'
    )


def select_chat_tools(message: str) -> list[str]:
    """Choose a tight <=10-tool subset matched to the message so 12B models stay fast and sharp."""
    blob = str(message or '').lower()
    if any(w in blob for w in ('.py', '.js', '.css', '.html', 'tests/', 'patch', 'fix ', 'refactor', 'theme', 'drawer', 'blueprint')):
        return list(CODE_CHAT_TOOLS)
    return list(EA_CHAT_TOOLS)


def confidence_for(receipts: list[dict] | None) -> str:
    """High when verified with passing receipts, Low when tools failed, Medium for pure conversation."""
    recs = list(receipts or [])
    if not recs:
        return 'Medium'
    if any(r.get('status') in ('failed', 'denied') for r in recs):
        return 'Low'
    if any(r.get('status') == 'succeeded' for r in recs):
        return 'High'
    return 'Medium'


def record(conn, conversation_id: int, user_message: str, answer: str, receipts: list[dict] | None = None) -> int:
    """Persist one compact Carry Forward entry for this conversation."""
    ensure_schema(conn)
    topic = ' '.join(str(user_message or '').split())[:140] or 'Conversation turn'
    outcome = ' '.join(str(answer or '').split())[:220] or 'Replied'
    tools = sorted({str(r.get('tool')) for r in (receipts or []) if r.get('tool') and r.get('status') == 'succeeded'})
    conf = confidence_for(receipts)
    cur = conn.execute(
        'INSERT INTO hb_carry_forward(conversation_id, topic, outcome, confidence, tools_used, created_at) '
        'VALUES (?,?,?,?,?,?)',
        (int(conversation_id), topic, outcome, conf, ','.join(tools), time.time()),
    )
    return int(cur.lastrowid)


def card(conn, conversation_id: int, limit: int = 4) -> str:
    """Render a compact Carry Forward continuity snapshot of recent talking points and decision weights."""
    ensure_schema(conn)
    rows = conn.execute(
        'SELECT topic, outcome, confidence, tools_used FROM hb_carry_forward '
        'WHERE conversation_id=? ORDER BY id DESC LIMIT ?',
        (int(conversation_id), int(limit)),
    ).fetchall()
    if not rows:
        return ''
    lines = ['CARRY FORWARD (recent talking points, outcomes & confidence weights):']
    for topic, outcome, conf, tools in reversed(rows):
        t_note = f' [tools: {tools}]' if tools else ''
        lines.append(f'- [{conf}] Topic: {topic} -> Outcome: {outcome}{t_note}')
    return '\n'.join(lines)


def _live_nectar_line() -> str:
    try:
        from contextlib import closing
        from utils.db._connection import get_connection
        from core import hb_nectar
        with closing(get_connection()) as conn:
            hb_nectar.backfill_from_merits(conn, 'APEX')
            conn.commit()
            return hb_nectar.summary_text(conn, 'APEX')
    except Exception:
        return ''


def lean_chat_prompt(model_name: str, carry_text: str = '', tools: list[str] | None = None, nectar_line: str | None = None) -> str:
    """Positive-first, lean (~550-token) prompt for direct main chat & Executive Assistant turns."""
    tool_list = ', '.join(tools or EA_CHAT_TOOLS)
    parts = [
        f"You are APEX ({model_name}), JD's upbeat, witty, creative all-round executive assistant and partner in Hummingbird (HB), "
        "running locally on JD's own private machine. "
        "JD is an Australian payroll/SAP consultant (PDS = Payday Super 1 July 2026, distinct from STP2 and MCB) with wide interests "
        "in music composition, poetry, math, science, gaming, and building HB. "
        "JD is witty, sarcastic, and uses colourful language casually — take sarcasm lightly, bring warm positive energy, and feel free "
        "to match a relaxed, sharp, occasionally colourful colleague tone.",
        "HOW YOU SHOULD RESPOND:",
        "- For casual chat, greetings, or banter: reply warmly, directly, and naturally in your own voice with ZERO tool calls.",
        "- For real requests, research, Melbourne finds, YouTube downloads, or HB changes: act first with your attached tools, then share the real verified result.",
        "- For substantive decisions, advice, or plans: briefly show Pragmatism & Logic (why this path), Creative Options (what else could work), "
        "Realism & Weights (High / Medium / Low confidence), and Carry Forward (what actually happened and what carries into the next turn).",
        "- Always write a short 1-2 sentence 'thought' first before 'tool_calls' or 'answer' so JD sees your live reasoning.",
        f"- Focused tools ready on demand this turn: {tool_list}.",
        'Return JSON matching the schema: {"thought":"...","tool_calls":[],"answer":"..."} for direct replies, or populate tool_calls with answer="".',
    ]
    wallet = _live_nectar_line() if nectar_line is None else nectar_line
    if wallet:
        parts.append(f'LIVE NECTAR WALLET (verified truth — never guess 0): {wallet}')
    base = '\n'.join(parts)
    if carry_text:
        base += '\n\n' + carry_text
    return base
