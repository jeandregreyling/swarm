"""
tests/test_telegram_trust.py — Dry-run trust model tests for Telegram bot

Tests classification logic, sender-context injection, and trust gate paths
without requiring a live Telegram connection.

Run: python3 tests/test_telegram_trust.py
Exit 0 = all pass, Exit 1 = failures found.
"""

import sys
import os
import sqlite3
import tempfile
import unittest

sys.path.insert(0, '/home/seven/swarm')
sys.path.insert(0, '/home/seven/swarm/utils')
sys.path.insert(0, '/home/seven/swarm/core/pipeline')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db(trusted=(), notification=()):
    """Create a scratch in-memory database with trusted_senders populated."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE trusted_senders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            added_by TEXT NOT NULL,
            added_at TEXT DEFAULT (datetime('now')),
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE notification_senders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            added_by TEXT NOT NULL,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE NOT NULL,
            sender_email TEXT NOT NULL,
            question TEXT NOT NULL,
            final_answer TEXT,
            status TEXT DEFAULT 'open',
            closed_at TEXT
        )
    """)
    for email in trusted:
        conn.execute("INSERT INTO trusted_senders (email, added_by) VALUES (?, 'test')", (email,))
    for email in notification:
        conn.execute("INSERT INTO notification_senders (email, added_by) VALUES (?, 'test')", (email,))
    conn.commit()
    return conn


# ── Unit: _telegram_key ───────────────────────────────────────────────────────

class TestTelegramKey(unittest.TestCase):

    def test_key_format(self):
        from fridays.telegram_bot import _telegram_key
        key = _telegram_key(8735763890)
        self.assertEqual(key, 'telegram:8735763890')

    def test_key_with_string_id(self):
        from fridays.telegram_bot import _telegram_key
        key = _telegram_key('12345')
        self.assertEqual(key, 'telegram:12345')


# ── Unit: _classify logic ─────────────────────────────────────────────────────

class TestClassifySenders(unittest.TestCase):
    """
    _classify reads get_all_email_lists() from DB.
    We patch get_all_email_lists to inject controlled data.
    """

    def _patch_and_classify(self, chat_id, trusted=(), notification=()):
        import fridays.telegram_bot as bot
        original = bot.get_all_email_lists

        trusted_set      = set(trusted)
        notification_set = set(notification)

        bot.get_all_email_lists = lambda: (trusted_set, set(), notification_set)
        try:
            result = bot._classify(chat_id)
        finally:
            bot.get_all_email_lists = original
        return result

    def test_trusted_user_classified_trusted(self):
        result = self._patch_and_classify(
            8735763890,
            trusted={'telegram:8735763890'},
        )
        self.assertEqual(result, 'trusted')

    def test_notification_user_classified_notification(self):
        result = self._patch_and_classify(
            999888777,
            notification={'telegram:999888777'},
        )
        self.assertEqual(result, 'notification')

    def test_unknown_user_classified_unknown(self):
        result = self._patch_and_classify(
            111222333,
            trusted={'telegram:8735763890'},
        )
        self.assertEqual(result, 'unknown')

    def test_ghost_telegram_id_is_trusted(self):
        """Ghost's known chat_id 8735763890 must always resolve to trusted."""
        result = self._patch_and_classify(
            8735763890,
            trusted={'telegram:8735763890', 'jeandre.greyling@gmail.com'},
        )
        self.assertEqual(result, 'trusted')

    def test_trusted_takes_priority_over_notification(self):
        """If email is in both lists, trusted wins."""
        result = self._patch_and_classify(
            555444333,
            trusted={'telegram:555444333'},
            notification={'telegram:555444333'},
        )
        self.assertEqual(result, 'trusted')


# ── Unit: _build_sender_context ───────────────────────────────────────────────

class TestBuildSenderContext(unittest.TestCase):

    def _make_context_fn(self, conn):
        """Return a version of _build_sender_context that uses our scratch DB."""
        import fridays.telegram_bot as bot
        original_get_connection = bot.get_connection

        bot.get_connection = lambda: conn
        try:
            fn = bot._build_sender_context
        finally:
            bot.get_connection = original_get_connection

        def wrapped(sender, question, limit=3):
            bot.get_connection = lambda: conn
            try:
                return bot._build_sender_context(sender, question, limit)
            finally:
                bot.get_connection = original_get_connection

        return wrapped

    def test_no_history_returns_raw_question(self):
        conn = _make_db(trusted=['telegram:111'])
        fn   = self._make_context_fn(conn)
        result = fn('telegram:111', 'What is the capital of France?')
        self.assertEqual(result, 'What is the capital of France?')

    def test_single_prior_ticket_injected(self):
        conn = _make_db(trusted=['telegram:111'])
        conn.execute("""
            INSERT INTO tickets (ticket_number, sender_email, question, final_answer, status, closed_at)
            VALUES ('TG-1', 'telegram:111', 'What is SAP?', 'SAP is an ERP platform.', 'closed', datetime('now'))
        """)
        conn.commit()
        fn = self._make_context_fn(conn)
        result = fn('telegram:111', 'Tell me more about it.')
        self.assertIn('=== Recent conversation context', result)
        self.assertIn('What is SAP?', result)
        self.assertIn('SAP is an ERP platform.', result)
        self.assertIn('Tell me more about it.', result)

    def test_current_question_always_last(self):
        conn = _make_db(trusted=['telegram:222'])
        conn.execute("""
            INSERT INTO tickets (ticket_number, sender_email, question, final_answer, status, closed_at)
            VALUES ('TG-2', 'telegram:222', 'Old question', 'Old answer', 'closed', datetime('now'))
        """)
        conn.commit()
        fn = self._make_context_fn(conn)
        result = fn('telegram:222', 'New question')
        # Current question must appear after history section
        context_pos  = result.index('=== Recent conversation context')
        current_pos  = result.index('=== Current question ===')
        new_q_pos    = result.index('New question')
        self.assertGreater(current_pos, context_pos)
        self.assertGreater(new_q_pos, current_pos)

    def test_open_tickets_excluded_from_history(self):
        conn = _make_db(trusted=['telegram:333'])
        conn.execute("""
            INSERT INTO tickets (ticket_number, sender_email, question, final_answer, status)
            VALUES ('TG-3', 'telegram:333', 'Open question', 'Some draft', 'open')
        """)
        conn.commit()
        fn = self._make_context_fn(conn)
        result = fn('telegram:333', 'Follow up question')
        # No history injected — open ticket excluded
        self.assertEqual(result, 'Follow up question')

    def test_limit_respected(self):
        conn = _make_db(trusted=['telegram:444'])
        for i in range(5):
            conn.execute("""
                INSERT INTO tickets (ticket_number, sender_email, question, final_answer, status, closed_at)
                VALUES (?, 'telegram:444', ?, ?, 'closed', datetime('now'))
            """, (f'TG-{i+10}', f'Question {i}', f'Answer {i}'))
        conn.commit()
        fn = self._make_context_fn(conn)
        result = fn('telegram:444', 'Latest question', limit=2)
        # Only 2 prior exchanges should appear (Questions 3 and 4)
        count = result.count('User asked:')
        self.assertEqual(count, 2)

    def test_different_sender_no_cross_contamination(self):
        conn = _make_db(trusted=['telegram:555', 'telegram:666'])
        conn.execute("""
            INSERT INTO tickets (ticket_number, sender_email, question, final_answer, status, closed_at)
            VALUES ('TG-20', 'telegram:555', 'Private question', 'Private answer', 'closed', datetime('now'))
        """)
        conn.commit()
        fn = self._make_context_fn(conn)
        # telegram:666 asks — must NOT see telegram:555's history
        result = fn('telegram:666', 'My question')
        self.assertNotIn('Private question', result)
        self.assertNotIn('Private answer', result)
        self.assertEqual(result, 'My question')

    def test_db_error_falls_back_to_raw_question(self):
        """If DB fails, _build_sender_context must return raw question safely."""
        import fridays.telegram_bot as bot
        original = bot.get_connection

        def bad_conn():
            raise RuntimeError('Simulated DB failure')

        bot.get_connection = bad_conn
        try:
            result = bot._build_sender_context('telegram:999', 'Safe question')
        finally:
            bot.get_connection = original

        self.assertEqual(result, 'Safe question')


# ── Integration: unknown user code path ──────────────────────────────────────

class TestUnknownUserPath(unittest.TestCase):
    """
    Verify that the else branch in handle_message does NOT call _run_pipeline.
    We patch _classify to return 'unknown' and verify _run_pipeline is not invoked.
    """

    def test_unknown_user_does_not_reach_pipeline(self):
        """
        Ensure the 'unknown' classification path never calls _run_pipeline.
        Instead it should call _notify_ghost.
        We verify by inspecting the source, not by running async code.
        """
        import inspect
        import fridays.telegram_bot as bot

        source = inspect.getsource(bot.handle_message)

        # The else branch must NOT contain a call to _run_pipeline
        # Extract the else block — find 'else:' and look at the content after it
        # Simple heuristic: after "unknown_sender_held", _run_pipeline must not appear
        # in the same logical block
        lines = source.splitlines()
        in_else = False
        else_lines = []
        for line in lines:
            if "log_activity('telegram', 'unknown_sender_held'" in line:
                in_else = True
            if in_else:
                else_lines.append(line)
                # Stop at next elif/else/end of function (dedent to base level)
                if line.strip().startswith('elif ') or line.strip().startswith('async def '):
                    break

        else_block = '\n'.join(else_lines)
        self.assertNotIn('_run_pipeline', else_block,
            'CRITICAL: unknown user path must not call _run_pipeline')

    def test_unknown_user_path_calls_notify_ghost(self):
        """Verify that _notify_ghost is called in the else (unknown) path."""
        import inspect
        import fridays.telegram_bot as bot

        source = inspect.getsource(bot.handle_message)

        # Find the else block by looking for the unknown_sender_held log
        lines = source.splitlines()
        in_else = False
        else_lines = []
        for line in lines:
            if "unknown_sender_held" in line or ("else:" in line and in_else):
                in_else = True
            if in_else:
                else_lines.append(line)

        else_block = '\n'.join(else_lines)
        self.assertIn('_notify_ghost', else_block,
            'Unknown user path must call _notify_ghost')


# ── DB state: Ghost telegram ID in trusted_senders ────────────────────────────

class TestGhostTelegramTrust(unittest.TestCase):
    """
    Ghost's live DB must have telegram:8735763890 in trusted_senders.
    Reads the real DB (read-only query).
    """
    GHOST_CHAT_ID = 8735763890
    DB_PATH       = '/home/seven/swarm/swarm_memory.db'

    def test_ghost_telegram_id_in_trusted_senders(self):
        if not os.path.exists(self.DB_PATH):
            self.skipTest('swarm_memory.db not found')
        conn = sqlite3.connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT email FROM trusted_senders WHERE email=?",
            (f'telegram:{self.GHOST_CHAT_ID}',)
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row,
            f'telegram:{self.GHOST_CHAT_ID} must be in trusted_senders')

    def test_moderator_table_has_ghost_email(self):
        if not os.path.exists(self.DB_PATH):
            self.skipTest('swarm_memory.db not found')
        conn = sqlite3.connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT email FROM moderators").fetchall()
        conn.close()
        emails = [r['email'] for r in rows]
        self.assertTrue(
            any('@' in e for e in emails),
            'moderators table must have at least one email address for Ghost notifications'
        )


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=2)
    result  = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
