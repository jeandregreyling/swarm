"""Explicit, transactional promotion of an owner's recovery journal.

The journal remains untouched. Importing history never executes its contents or
restores old approvals. The caller owns authentication and the DB transaction.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time

from core.chat_continuity import strip_notice_prefix


def verify_storage(conn: sqlite3.Connection, seconds: float = 10.0) -> None:
    """Bounded full integrity check; readable conversations alone are insufficient."""
    deadline = time.monotonic() + seconds
    conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10_000)
    try:
        results = conn.execute("PRAGMA integrity_check(1)").fetchall()
        if len(results) != 1 or results[0][0] != "ok":
            raise sqlite3.DatabaseError("Primary storage integrity check failed")
    finally:
        conn.set_progress_handler(None, 0)


def import_journal(conn: sqlite3.Connection, thread: dict, owner: str) -> dict:
    if thread.get("owner") != owner:
        raise PermissionError("Recovery conversation belongs to another operator identity")
    if conn.in_transaction:
        raise RuntimeError("Recovery import requires its own transaction")
    verify_storage(conn)
    # Stable digest covers the entire journal, including messages after an earlier
    # import. A changed journal needs review rather than a silent incomplete import.
    digest = hashlib.sha256(json.dumps(thread, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS recovery_thread_imports (
            recovery_id INTEGER PRIMARY KEY, owner TEXT NOT NULL,
            source_sha256 TEXT NOT NULL, conversation_id INTEGER NOT NULL,
            message_count INTEGER NOT NULL, imported_at REAL NOT NULL)""")
        existing = conn.execute(
            "SELECT owner, source_sha256, conversation_id, message_count FROM recovery_thread_imports WHERE recovery_id=?",
            (thread["id"],),
        ).fetchone()
        if existing:
            if existing[0] != owner:
                raise PermissionError("Recovery import belongs to another operator identity")
            if existing[1] != digest:
                raise ValueError("Recovery journal changed after import; review its newer messages before resuming")
            if not conn.execute("SELECT 1 FROM conversations WHERE id=?", (existing[2],)).fetchone():
                raise ValueError("Previously imported conversation is missing; restore it before resuming")
            conn.commit()
            return {"conversation_id": existing[2], "imported_messages": existing[3], "already_imported": True}
        cid = conn.execute(
            "INSERT INTO conversations (title, source, sender) VALUES (?,?,?)",
            (thread["title"], "terminal-ui:recovery-resumed", owner),
        ).lastrowid
        for message in thread["messages"]:
            sender = message["sender"]
            content = message["content"]
            # Preserve the historical restriction notice as evidence, not an
            # instruction that tools must stay disabled in the resumed thread.
            if sender != "user":
                content = "[Historical recovery reply; tools were unavailable then.]\n\n" + strip_notice_prefix(content)
            conn.execute("""INSERT INTO messages
                (conversation_id, from_agent, to_agent, content, message_type, tokens_used, created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (cid, sender, message.get("to_agent"), content, message.get("message_type", "chat"),
                 message.get("tokens_used", 0), message["created_at"]),
            )
        conn.execute("INSERT INTO recovery_thread_imports VALUES (?,?,?,?,?,?)",
                     (thread["id"], owner, digest, cid, len(thread["messages"]), time.time()))
        conn.commit()
        return {"conversation_id": cid, "imported_messages": len(thread["messages"]), "already_imported": False}
    except BaseException:
        conn.rollback()
        raise
