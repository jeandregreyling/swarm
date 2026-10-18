import sqlite3

import pytest

from utils import thread_memory


@pytest.fixture
def memdb(tmp_path, monkeypatch):
    path = tmp_path / "t.db"

    def _conn():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    import utils.db as db

    monkeypatch.setattr(db, "get_connection", _conn)
    return _conn


def test_fact_ref_extracts_proposal_id_and_path(memdb):
    assert thread_memory.record_fact(7, "mistral", "fs_readonly", "lines README.md 1 20", True, "ok")
    assert thread_memory.record_fact(
        7, "mistral", "alm_create_proposal", '"T" "D"', True,
        "ALM proposal created: queue_id=9, proposal_id=INTERNAL-MISTRAL-9",
    )
    facts = thread_memory.recent_facts(7)
    assert [f["ref"] for f in facts] == ["README.md", "INTERNAL-MISTRAL-9"]


def test_no_conversation_means_no_fact(memdb):
    assert thread_memory.record_fact(None, "mistral", "fs_readonly", "x", True, "") is False


def test_summary_only_contains_verified_facts(memdb):
    thread_memory.record_fact(3, "gemma", "fs_readonly", "lines a.py 1 5", True, "ok")
    thread_memory.record_fact(3, "gemma", "alm_create_proposal", '"T" "D"', False, "FAILED no id")
    assert thread_memory.update_thread_state(3, "gemma", "read a.py and propose", "Done.")
    block = thread_memory.carry_over_block("gemma", 99)
    assert "read a.py" in block
    assert "created" not in block
    assert "thread 3" in block
    assert len(block) < 1400


def test_proposal_shows_as_open_task(memdb):
    thread_memory.record_fact(
        4, "mistral", "alm_create_proposal", '"T" "D"', True, "proposal_id=INTERNAL-MISTRAL-5"
    )
    thread_memory.update_thread_state(4, "mistral", "raise it", "Raised.")
    block = thread_memory.carry_over_block("mistral", 4)
    assert "INTERNAL-MISTRAL-5" in block
    assert "this thread" in block


def test_block_is_empty_without_state_and_failures_are_silent(memdb, monkeypatch):
    assert thread_memory.carry_over_block("duck", 1) == ""
    import utils.db as db

    def boom():
        raise sqlite3.OperationalError("down")

    monkeypatch.setattr(db, "get_connection", boom)
    assert thread_memory.record_fact(1, "duck", "fs_readonly", "x", True, "") is False
    assert thread_memory.carry_over_block("duck", 1) == ""
    assert thread_memory.update_thread_state(1, "duck", "m", "r") is False
