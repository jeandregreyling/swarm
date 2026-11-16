"""The chat JD is using (Practice 105, owner 16 Nov 2026).

HB's background lines (benchmark results, onboarding and exams, GPU guard, proposals, lessons, loop warnings) were written to chat 2834,
the old main chat JD no longer uses - he never saw that MiniCPM5 passed its benchmark or that Copilot passed its exam. Practices 93 and 102
fixed this one module at a time; this is the one place every module asks. The chat JD last typed in; 2834 only when he has typed nowhere.
"""
OLD_MAIN_CHAT = 2834


def owner_chat(conn):
    try:
        row = (conn.execute("SELECT conversation_id FROM messages WHERE from_agent='user' ORDER BY id DESC LIMIT 1").fetchone()
               if conn is not None else None)
        return int(row[0]) if row and row[0] is not None else OLD_MAIN_CHAT
    except Exception:
        return OLD_MAIN_CHAT
