"""tests/test_curiosity.py — PACKET-10B unit tests for the Curiosity organ.

These tests use a temporary SQLite path (via ``SWARM_MEMORY_DB`` env override)
so they never touch the live swarm DB. The ``core.curiosity`` module reads the
env var at import time, but each test reloads the module after pointing it at
its own temp DB.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _seed_brain_tables(db_path: str) -> None:
    """Seven's brain tables are created elsewhere; recreate the minimal
    subset the curiosity module touches (episodes + beliefs)."""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS seven_episodes (
                episode_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            REAL    NOT NULL,
                source        TEXT    NOT NULL,
                kind          TEXT,
                record_id     TEXT,
                action        TEXT,
                actor         TEXT,
                salience      REAL    DEFAULT 0.5,
                payload_json  TEXT
            );
            CREATE TABLE IF NOT EXISTS seven_beliefs (
                belief_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                subject        TEXT NOT NULL,
                predicate      TEXT NOT NULL,
                object         TEXT,
                confidence     REAL NOT NULL,
                evidence_count INTEGER DEFAULT 1,
                first_seen     REAL,
                last_seen      REAL,
                UNIQUE(subject, predicate, object)
            );
            """
        )
        con.commit()
    finally:
        con.close()


class CuriosityTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["SWARM_MEMORY_DB"] = self._tmp.name
        _seed_brain_tables(self._tmp.name)
        from core import curiosity  # noqa: WPS433
        self.curiosity = curiosity
        # Force schema bootstrap on the new temp DB.
        con = sqlite3.connect(self._tmp.name)
        try:
            curiosity._ensure_schema(con)
        finally:
            con.close()

    def tearDown(self) -> None:
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass
        os.environ.pop("SWARM_MEMORY_DB", None)


class TestSchema(CuriosityTestBase):
    def test_schema_created_on_import(self):
        con = sqlite3.connect(self._tmp.name)
        try:
            row = con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='curiosity_questions'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            con.close()

    def test_stats_initial_state(self):
        s = self.curiosity.stats()
        self.assertEqual(s["open"], 0)
        self.assertEqual(s["answered"], 0)
        self.assertIsNone(s["latest_open_age_h"])


class TestAsk(CuriosityTestBase):
    def test_ask_inserts_question(self):
        qid = self.curiosity.ask(
            "seven", "What is the operator's preferred deployment region?",
            context_kind="unknown_term", salience=0.7,
        )
        self.assertIsInstance(qid, int)
        self.assertGreater(qid, 0)
        rows = self.curiosity.list_open()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asked_by"], "seven")
        self.assertAlmostEqual(rows[0]["salience"], 0.7, places=2)

    def test_ask_rejects_empty_inputs(self):
        self.assertIsNone(self.curiosity.ask("", "Hello?"))
        self.assertIsNone(self.curiosity.ask("seven", ""))
        self.assertIsNone(self.curiosity.ask("seven", "   "))

    def test_ask_dedup_within_window_returns_existing_id(self):
        q1 = self.curiosity.ask("seven", "Same question?", salience=0.3)
        q2 = self.curiosity.ask("seven", "Same question?", salience=0.6)
        self.assertEqual(q1, q2)
        rows = self.curiosity.list_open()
        self.assertEqual(len(rows), 1)
        # Salience should be promoted to the higher value.
        self.assertAlmostEqual(rows[0]["salience"], 0.6, places=2)

    def test_ask_no_dedup_across_agents(self):
        q1 = self.curiosity.ask("seven", "Who pays for storage?")
        q2 = self.curiosity.ask("librarian", "Who pays for storage?")
        self.assertNotEqual(q1, q2)
        self.assertEqual(len(self.curiosity.list_open()), 2)

    def test_ask_writes_episode(self):
        self.curiosity.ask("seven", "Episode probe?", salience=0.5)
        con = sqlite3.connect(self._tmp.name)
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM seven_episodes "
                "WHERE source='curiosity' AND action='asked'"
            ).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n, 1)


class TestAnswer(CuriosityTestBase):
    def test_answer_marks_status_and_promotes_belief(self):
        qid = self.curiosity.ask(
            "seven", "What is the canonical region?",
            context_ref="region::default", salience=0.5,
        )
        ok = self.curiosity.answer(qid, "uksouth", answered_by="user")
        self.assertTrue(ok)

        recent = self.curiosity.list_recent(status="answered")
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["answer"], "uksouth")
        self.assertEqual(recent[0]["answered_by"], "user")

        con = sqlite3.connect(self._tmp.name)
        try:
            beliefs = con.execute(
                "SELECT subject, predicate, object, confidence FROM seven_beliefs"
            ).fetchall()
        finally:
            con.close()
        self.assertEqual(len(beliefs), 1)
        self.assertEqual(beliefs[0][0], "region::default")
        self.assertEqual(beliefs[0][2], "uksouth")
        self.assertGreaterEqual(beliefs[0][3], 0.85)

    def test_answer_skip_belief_when_disabled(self):
        qid = self.curiosity.ask("seven", "Skip belief test?", context_ref="x")
        self.curiosity.answer(qid, "yes", promote_to_belief=False)
        con = sqlite3.connect(self._tmp.name)
        try:
            n = con.execute("SELECT COUNT(*) FROM seven_beliefs").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n, 0)

    def test_double_answer_rejected(self):
        qid = self.curiosity.ask("seven", "One-shot?")
        self.assertTrue(self.curiosity.answer(qid, "first"))
        self.assertFalse(self.curiosity.answer(qid, "second"))

    def test_answer_unknown_id_returns_false(self):
        self.assertFalse(self.curiosity.answer(9999, "nope"))


class TestListAndDismiss(CuriosityTestBase):
    def test_list_open_orders_by_salience(self):
        a = self.curiosity.ask("seven", "low priority?", salience=0.1)
        b = self.curiosity.ask("seven", "high priority?", salience=0.9)
        c = self.curiosity.ask("seven", "mid priority?", salience=0.5)
        rows = self.curiosity.list_open()
        ids = [r["id"] for r in rows]
        self.assertEqual(ids, [b, c, a])

    def test_list_open_min_salience_filter(self):
        self.curiosity.ask("seven", "skip me?", salience=0.1)
        self.curiosity.ask("seven", "keep me?", salience=0.8)
        rows = self.curiosity.list_open(min_salience=0.5)
        self.assertEqual(len(rows), 1)
        self.assertIn("keep me", rows[0]["question"])

    def test_dismiss_idempotent(self):
        qid = self.curiosity.ask("seven", "drop this?")
        self.assertTrue(self.curiosity.dismiss(qid, reason="not relevant"))
        # Second dismiss returns False (already closed).
        self.assertFalse(self.curiosity.dismiss(qid))
        self.assertEqual(self.curiosity.stats()["dismissed"], 1)


class TestPrune(CuriosityTestBase):
    def test_prune_marks_old_questions_expired(self):
        qid = self.curiosity.ask("seven", "ancient question?")
        # Backdate it 60 days.
        con = sqlite3.connect(self._tmp.name)
        try:
            con.execute(
                "UPDATE curiosity_questions SET asked_at = ? WHERE id = ?",
                (time.time() - 60 * 86400, qid),
            )
            con.commit()
        finally:
            con.close()
        n = self.curiosity.prune(max_age_days=30)
        self.assertEqual(n, 1)
        s = self.curiosity.stats()
        self.assertEqual(s["expired"], 1)
        self.assertEqual(s["open"], 0)


class TestHelpers(CuriosityTestBase):
    def test_from_llm_failure(self):
        try:
            raise RuntimeError("ollama down")
        except RuntimeError as e:
            qid = self.curiosity.from_llm_failure("seven", "what is X", e)
        self.assertIsInstance(qid, int)
        rows = self.curiosity.list_open()
        self.assertEqual(rows[0]["context_kind"], "llm_failure")

    def test_from_ambiguous_route(self):
        qid = self.curiosity.from_ambiguous_route(
            "duck", "build me a thing", ["gemma", "llama", "qwen"],
        )
        rows = self.curiosity.list_open()
        self.assertEqual(rows[0]["context_kind"], "ambiguous_route")
        self.assertEqual(rows[0]["options"], ["gemma", "llama", "qwen"])

    def test_from_unknown_term_skips_empty(self):
        self.assertIsNone(self.curiosity.from_unknown_term("seven", ""))


if __name__ == "__main__":
    unittest.main()
