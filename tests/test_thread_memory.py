import sqlite3

import pytest

from utils import thread_memory


@pytest.fixture
def memdb(tmp_path, monkeypatch):
    monkeypatch.setattr(thread_memory, "MIND_DB_PATH", str(tmp_path / "mind.db"))
    return thread_memory._conn


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
    # Seed notes always exist, so a brand new mind still carries the operator's principles.
    assert "honesty" in thread_memory.carry_over_block("duck", 1)

    def boom():
        raise sqlite3.OperationalError("down")

    monkeypatch.setattr(thread_memory, "_conn", boom)
    assert thread_memory.record_fact(1, "duck", "fs_readonly", "x", True, "") is False
    assert thread_memory.carry_over_block("duck", 1) == ""
    assert thread_memory.update_thread_state(1, "duck", "m", "r") is False
    assert thread_memory.record_exchange(1, "duck", "m", "r") is False


def test_facts_use_conversation_from_context_in_worker_threads(memdb):
    from concurrent.futures import ThreadPoolExecutor

    def work():
        return thread_memory.record_fact(None, "gemma", "fs_readonly", "lines a.py 1 2", True, "ok")

    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(thread_memory.run_in_conversation, 55, work).result() is True
    assert thread_memory.recent_facts(55)[0]["ref"] == "a.py"
    assert thread_memory.record_fact(None, "gemma", "fs_readonly", "x y", True, "") is False


def test_exchange_is_stored_uncut(memdb):
    long_reply = "x" * 5000
    assert thread_memory.record_exchange(8, "mistral", "hi", long_reply)
    row = memdb().execute("SELECT reply FROM exchanges WHERE conversation_id='8'").fetchone()
    assert len(row["reply"]) == 5000


def test_notes_load_by_relevance_and_principles_always(memdb):
    thread_memory.add_note("decision", "Quokka migration uses the zebra scheduler")
    block = thread_memory.carry_over_block("mistral", 1, "tell me about the zebra scheduler")
    assert "zebra" in block
    assert "honesty" in block
    other = thread_memory.carry_over_block("mistral", 1, "unrelated words here")
    assert len(other) < 2600


def test_overview_reports_counts(memdb):
    thread_memory.record_exchange(1, "gemma", "a", "b")
    text = thread_memory.mind_overview()
    assert "mind.db" in text and "1 exchanges" in text
