import json
import sqlite3

import pytest

from core import apex_evidence
from core.apex_studio import _project_id
from core.apex_tools import TURN_FORMAT, run_apex_tools


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    path = tmp_path / "evidence #?.sqlite"
    monkeypatch.setenv("SWARM_DB", str(path))
    project = _project_id(7, "owner")
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE studio_evidence(id INTEGER PRIMARY KEY, conversation_id INTEGER, payload TEXT)")
        conn.executemany("INSERT INTO studio_evidence VALUES (?,?,?)", [
            (1, 7, json.dumps({"project_id": project, "receipt": "fixture-receipt"})),
            (2, 8, json.dumps({"project_id": project})),
            (3, 7, json.dumps({"project_id": "different"})),
            (4, 7, "{bad"),
            (5, 7, "[]"),
            (6, 7, json.dumps({"project_id": project, "value": "x" * 8000})),
            (7, 7, "x" * (apex_evidence.MAX_RECORD_BYTES + 1)),
        ])
    return path


def test_exact_lookup_is_read_only_scoped_and_returns_parsed_payload(evidence):
    before = evidence.read_bytes()
    result = apex_evidence.read_evidence(7, "owner", 1)
    assert result["status"] == "found"
    assert result["payload"]["receipt"] == "fixture-receipt"
    for owner, identity in [("other", 1), ("owner", 2), ("owner", 3), ("owner", 99)]:
        assert apex_evidence.read_evidence(7, owner, identity)["status"] == "not_found"
    assert evidence.read_bytes() == before


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5, None, 2**63])
def test_invalid_ids_rejected_before_storage(value, monkeypatch):
    monkeypatch.setattr(apex_evidence.sqlite3, "connect",
                        lambda *a, **k: pytest.fail("Invalid input must not open storage"))
    with pytest.raises(ValueError):
        apex_evidence.read_evidence(7, "owner", value)


def test_corrupt_and_truncated_results_are_not_success(evidence):
    for identity in (4, 5):
        assert apex_evidence.read_evidence(7, "owner", identity)["status"] == "corrupt"
    result = apex_evidence.read_evidence(7, "owner", 6)
    assert result["status"] == "truncated" and "payload" not in result
    assert len(json.dumps(result).encode()) <= 6000
    assert apex_evidence.read_evidence(7, "owner", 7)["status"] == "not_found"


def test_missing_database_is_not_created(tmp_path, monkeypatch):
    path = tmp_path / "absent.sqlite"
    monkeypatch.setenv("SWARM_DB", str(path))
    with pytest.raises(sqlite3.OperationalError):
        apex_evidence.read_evidence(7, "owner", 1)
    assert not path.exists()


def test_full_serialized_output_including_unicode_is_bounded(evidence):
    with sqlite3.connect(evidence) as conn:
        conn.execute("UPDATE studio_evidence SET payload=? WHERE id=1",
                     (json.dumps({"project_id": _project_id(7, "owner"),
                                  "value": "\u2603" * 1100}, ensure_ascii=False),))
    result = apex_evidence.read_evidence(7, "owner", 1)
    assert result["status"] == "truncated"
    assert len(json.dumps(result).encode()) <= 6000


def test_tool_schema_dispatch_and_denied_handler(evidence):
    schema = TURN_FORMAT["json_schema"]["schema"]["oneOf"][0]["properties"]["tool_calls"]["items"]["oneOf"]
    call = next(item for item in schema if item["properties"]["name"]["const"] == "studio_evidence_get")
    assert call["properties"]["arguments"]["required"] == ["evidence_id"]
    assert call["properties"]["arguments"]["additionalProperties"] is False
    for attached in (False, True):
        outputs = iter([
            json.dumps({"tool_calls": [{"name": "studio_evidence_get", "arguments": {"evidence_id": 1}}],
                        "answer": ""}),
            json.dumps({"tool_calls": [], "answer": "Checked actual receipt."}),
        ])
        handler = (lambda tool, args: apex_evidence.read_evidence(7, "owner", **args)) if attached else None
        _, _, receipts = run_apex_tools(
            lambda *_: (next(outputs), 1), [{"role": "user", "content": "Retrieve evidence"}],
            lambda: True, lambda _: None, studio_handler=handler)
        assert receipts[0]["status"] == ("succeeded" if attached else "denied")
